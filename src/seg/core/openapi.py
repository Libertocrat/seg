"""OpenAPI schema construction helpers for runtime-generated SEG contracts."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

import seg.core.errors as errors
from seg.actions.models.core import ActionSpec, ParamType
from seg.actions.registry import ActionRegistry
from seg.core.errors import PUBLIC_HTTP_ERRORS, ErrorDef
from seg.core.schemas.envelope import ErrorInfo, ResponseEnvelope
from seg.routes.actions.schemas import ExecuteActionData, ExecuteRequest

# Define explicit response contract overrides for endpoints that cannot be correctly
# inferred from FastAPI's default schema generation
RESPONSE_CONTRACT_OVERRIDES = {
    "/metrics": {
        "method": "get",
        "responses": {
            "200": {
                "description": "Prometheus metrics snapshot",
                "content": {
                    "text/plain": {
                        "schema": {
                            "type": "string",
                            "example": (
                                "# HELP http_requests_total ...\n"
                                "# TYPE http_requests_total counter\n"
                                "http_requests_total 42\n"
                                "# HELP ...\n"
                            ),
                        }
                    }
                },
            }
        },
    },
    "/health": {
        "method": "get",
        "responses": {
            "200": {
                "description": "Health success response",
                "content": {
                    "application/json": {
                        "schema": {
                            "example": {
                                "success": True,
                                "error": None,
                                "data": {"status": "ok"},
                            },
                        }
                    }
                },
            }
        },
    },
}

# Defines the set of SEG error conditions that may be returned by
# global middleware layers (e.g. authentication, rate limiting, timeout).
#
# These errors are not tied to specific route handlers and must be
# injected into all protected operations in the OpenAPI schema.
#
# IMPORTANT:
# - Do not include handler-specific errors here.
# - Errors listed here should originate exclusively from middleware.
# - Public endpoints (e.g. `/health`, `/metrics`) are excluded at runtime.
MIDDLEWARE_ERROR_MAP = [
    errors.UNAUTHORIZED,
    errors.RATE_LIMITED,
    errors.TIMEOUT,
    errors.FILE_TOO_LARGE,
    errors.INVALID_REQUEST,
]


def build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Build the SEG OpenAPI document with runtime-aware patches.

    This function generates the base OpenAPI schema from FastAPI routes
    and then enriches it with SEG-specific runtime constraints derived
    from middleware behavior and the dynamic action registry.

    The function is fully self-contained and depends only on the `app`
    instance passed as argument. It does not rely on any global state.

    Args:
        app: FastAPI (or SEGApp) instance.

    Returns:
        Cached OpenAPI schema dictionary.
    """

    # If already generated and cached, reuse it
    if app.openapi_schema:
        return app.openapi_schema

    # Generate base schema from FastAPI's route inspection
    schema: dict[str, Any] = get_openapi(
        title=app.title,
        version=app.version,
        description=getattr(app, "description", None),
        routes=app.routes,
    )

    info = schema.setdefault("info", {})
    info["contact"] = getattr(app, "contact", None)
    info["license"] = getattr(app, "license_info", None)

    schema["tags"] = [
        {
            "name": "Execution",
            "description": "Execute sandboxed actions via dispatcher.",
        },
        {
            "name": "Files",
            "description": "Upload and manage persisted files.",
        },
        {
            "name": "Observability",
            "description": "System health checks and Prometheus metrics endpoints.",
            "externalDocs": {
                "description": "Prometheus official documentation",
                "url": "https://prometheus.io/docs/",
            },
        },
    ]

    schema["externalDocs"] = {
        "description": "Project repository and architectural documentation",
        "url": "https://github.com/Libertocrat/seg",
    }

    # Apply SEG-specific patches in stable order.
    # Order matters: security first, then endpoint-level patches,
    # then response header enrichment.
    _patch_custom_schemas(schema)
    _inject_security(schema)
    _patch_public_endpoints(schema)
    _patch_execute_contract(schema, app)
    _patch_files_contract(schema)
    _inject_middleware_errors(schema, MIDDLEWARE_ERROR_MAP)
    _replace_default_422(schema)
    _inject_response_headers(schema)
    _prune_internal_schemas(schema)
    _apply_response_contract_overrides(schema, RESPONSE_CONTRACT_OVERRIDES)

    # Cache on the same app instance (no globals involved)
    app.openapi_schema = schema
    return schema


def _register_model(
    model: type[BaseModel],
    schemas: dict[str, Any],
    nested: bool = False,
) -> None:
    """Register a Pydantic model and optionally register nested schemas.

    Args:
        model: Pydantic model to register under components.schemas.
        schemas: Components schema registry dictionary.
        nested: Set to True to recurse through `$defs`.
    """

    name = model.__name__

    if name in schemas:
        return

    model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    nested_defs = model_schema.pop("$defs", {})

    schemas[name] = model_schema

    if not nested or not nested_defs:
        return

    def _register_defs(defs: dict[str, Any]) -> None:
        """Recursively register nested `$defs` under components schemas."""

        for nested_name, nested_schema in defs.items():
            if nested_name in schemas:
                continue

            schemas[nested_name] = nested_schema
            child_defs = nested_schema.get("$defs", {})
            if child_defs:
                _register_defs(child_defs)

    _register_defs(nested_defs)


# ---------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------


def _inject_security(schema: dict[str, Any]) -> None:
    """Inject global bearer-auth requirements into the OpenAPI schema.

    Args:
        schema: Mutable OpenAPI schema document.
    """

    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})

    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "Opaque token",
        "description": "Send Authorization: Bearer <SEG_API_TOKEN>",
    }

    # Set secure-by-default contract once, then carve out explicit public
    # endpoints in `_patch_public_endpoints` to match middleware behavior.
    schema["security"] = [{"BearerAuth": []}]


def _patch_public_endpoints(schema: dict[str, Any]) -> None:
    """Mark public endpoints as unauthenticated in OpenAPI.

    Args:
        schema: Mutable OpenAPI schema document.
    """

    paths = schema.get("paths", {})
    for path, methods in paths.items():
        if path.startswith("/health") or path.startswith("/metrics"):
            for op in methods.values():
                op["security"] = []
                op["tags"] = ["Observability"]

        if path.startswith("/metrics"):
            op["externalDocs"] = {
                "description": "Prometheus scraping documentation",
                "url": (
                    "https://prometheus.io/docs/prometheus/latest/"
                    "configuration/configuration/#scrape_config"
                ),
            }


# ---------------------------------------------------------------------
# Response headers
# ---------------------------------------------------------------------


def _inject_response_headers(schema: dict[str, Any]) -> None:
    """Inject standard SEG response headers into every HTTP operation.

    Args:
        schema: Mutable OpenAPI schema document.
    """

    for path_item in schema.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            responses = operation.setdefault("responses", {})

            for code, response in responses.items():
                headers = response.setdefault("headers", {})

                headers["X-Request-Id"] = {
                    "description": "Request correlation identifier.",
                    "schema": {"type": "string", "format": "uuid"},
                }

                if code == "429":
                    headers["Retry-After"] = {
                        "description": "Seconds to wait before retrying.",
                        "schema": {"type": "string", "pattern": "^[0-9]+$"},
                    }


# ---------------------------------------------------------------------
# /v1/files contracts
# ---------------------------------------------------------------------


def _patch_files_contract(schema: dict[str, Any]) -> None:
    """Apply SEG OpenAPI contract overrides for `/v1/files` endpoints.

    This function defines and injects the OpenAPI response contract for
    file-related operations under the `/v1/files` path. It encapsulates
    all domain-specific knowledge for this endpoint, including:

    - The set of SEG error conditions that may be raised by the handler
      (`ingest_uploaded_file`)
    - A canonical success response example aligned with the
      `ResponseEnvelope[FileMetadata]` structure

    The function delegates the actual schema mutation to
    `_patch_operation_contract`, ensuring consistent behavior across
    all endpoints while keeping domain configuration localized.

    Notes:
        - Only handler-level errors are included here. Middleware-derived
          errors (e.g. authentication, rate limiting) are injected separately
          via `_inject_middleware_errors(...)`.
        - The success example overrides FastAPI-generated examples to provide
          deterministic and meaningful documentation.
        - This function is designed to scale as additional methods
          (GET, DELETE, etc.) are added to `/v1/files`.

    Args:
        schema: Mutable OpenAPI schema document to be patched in-place.

    Returns:
        None.
    """

    FILES_POST_ERRORS = [
        errors.INVALID_REQUEST,
        errors.INVALID_ALGORITHM,
        errors.FILE_EXTENSION_MISSING,
        errors.MIME_MAPPING_NOT_DEFINED,
        errors.FILE_TOO_LARGE,
        errors.UNSUPPORTED_MEDIA_TYPE,
        errors.INTERNAL_ERROR,
    ]

    FILES_POST_SUCCESS_EXAMPLE = {
        "success": True,
        "error": None,
        "data": {
            "file": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "original_filename": "document.pdf",
                "stored_filename": "file_<uuid>.bin",
                "mime_type": "application/pdf",
                "extension": ".pdf",
                "size_bytes": 1024,
                "sha256": "abc123...",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "status": "ready",
            }
        },
    }

    _patch_operation_contract(
        schema,
        path="/v1/files",
        method="post",
        errors=FILES_POST_ERRORS,
        success_example=FILES_POST_SUCCESS_EXAMPLE,
    )

    FILES_LIST_ERRORS = [
        errors.INVALID_REQUEST,
        errors.INTERNAL_ERROR,
    ]

    FILES_LIST_SUCCESS_EXAMPLE = {
        "success": True,
        "error": None,
        "data": {
            "files": [],
            "pagination": {
                "count": 0,
                "next_cursor": None,
            },
        },
    }

    _patch_operation_contract(
        schema,
        path="/v1/files",
        method="get",
        errors=FILES_LIST_ERRORS,
        success_example=FILES_LIST_SUCCESS_EXAMPLE,
    )

    FILES_GET_ERRORS = [
        errors.FILE_NOT_FOUND,
        errors.INVALID_REQUEST,
        errors.INTERNAL_ERROR,
    ]

    FILES_GET_SUCCESS_EXAMPLE = {
        "success": True,
        "error": None,
        "data": {
            "file": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "original_filename": "example.txt",
                "stored_filename": "file_<uuid>.bin",
                "mime_type": "text/plain",
                "extension": ".txt",
                "size_bytes": 123,
                "sha256": (
                    "8e9aa02fb68dfb526d787f6b66adda7b651dd3f9f3b4a03e266d466161f4c39e"
                ),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "status": "ready",
            }
        },
    }

    _patch_operation_contract(
        schema,
        path="/v1/files/{id}",
        method="get",
        errors=FILES_GET_ERRORS,
        success_example=FILES_GET_SUCCESS_EXAMPLE,
    )

    FILES_DELETE_ERRORS = [
        errors.FILE_NOT_FOUND,
        errors.INVALID_REQUEST,
        errors.INTERNAL_ERROR,
    ]

    FILES_DELETE_SUCCESS_EXAMPLE = {
        "success": True,
        "error": None,
        "data": {
            "file": {
                "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "deleted": True,
            }
        },
    }

    _patch_operation_contract(
        schema,
        path="/v1/files/{id}",
        method="delete",
        errors=FILES_DELETE_ERRORS,
        success_example=FILES_DELETE_SUCCESS_EXAMPLE,
    )

    FILES_CONTENT_GET_ERRORS = [
        errors.FILE_NOT_FOUND,
        errors.INVALID_REQUEST,
        errors.INTERNAL_ERROR,
    ]

    _patch_operation_contract(
        schema,
        path="/v1/files/{id}/content",
        method="get",
        errors=FILES_CONTENT_GET_ERRORS,
    )

    files_content_operation = (
        schema.get("paths", {}).get("/v1/files/{id}/content", {}).get("get")
    )
    if files_content_operation:
        files_content_responses = files_content_operation.setdefault("responses", {})
        files_content_responses["200"] = {
            "description": "Streamed file content.",
            "content": {
                "application/octet-stream": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        }


# ---------------------------------------------------------------------
# /v1/execute dynamic contract
# ---------------------------------------------------------------------


def _build_execute_action_markdown(spec: ActionSpec) -> str:
    """Build a rich markdown description block for one action example.

    Args:
        spec: Runtime action specification.

    Returns:
        Markdown description including description, args, and flags.
    """

    description = spec.description or spec.summary or "No description provided."

    lines = [
        "",
        description,
        "",
        "#### Args",
        "",
    ]

    if spec.arg_defs:
        for arg_name, arg_def in spec.arg_defs.items():
            arg_line = f"- `{arg_name}` (`{arg_def.type.value}`): "
            details: list[str] = []

            if arg_def.description:
                details.append(arg_def.description)

            if arg_def.required:
                details.append("**\\*required**")
            else:
                default_value = spec.defaults.get(arg_name, arg_def.default)
                details.append(
                    "default: " f"`{_format_openapi_markdown_value(default_value)}`"
                )

            arg_line += "; ".join(details) if details else "No details."
            lines.append(arg_line)
    else:
        lines.append("- _No args_")

    lines.extend(["", "#### Flags", ""])
    if spec.flag_defs:
        for flag_name, flag_def in spec.flag_defs.items():
            flag_line = (
                f"- `{flag_name}`: {flag_def.description}; "
                "default: "
                f"`{_format_openapi_markdown_value(flag_def.default)}`"
            )
            lines.append(flag_line)
    else:
        lines.append("- _No flags_")

    if spec.deprecated:
        lines.extend(["", "⚠️ Deprecated action."])

    return "\n".join(lines)


def _build_execute_params_example(spec: ActionSpec) -> dict[str, Any]:
    """Build request `params` examples for one runtime action.

    Args:
        spec: Runtime action specification.

    Returns:
        Dictionary compatible with the action's `params_model`.
    """

    if spec.params_example is not None:
        return spec.params_example.model_dump(exclude_none=False)

    params_example: dict[str, Any] = {}

    for arg_name, arg_def in spec.arg_defs.items():
        if arg_def.required:
            params_example[arg_name] = _build_required_arg_example_value(
                arg_name,
                arg_def.type,
            )
            continue

        if arg_name in spec.defaults:
            params_example[arg_name] = spec.defaults[arg_name]

    for flag_name, flag_def in spec.flag_defs.items():
        params_example[flag_name] = flag_def.default

    return params_example


def _build_required_arg_example_value(arg_name: str, param_type: ParamType) -> Any:
    """Build a deterministic example value for a required action argument.

    Args:
        arg_name: Action argument name.
        param_type: Argument logical type.

    Returns:
        Example value aligned with the declared param type.
    """

    if param_type == ParamType.INT:
        return 1

    if param_type == ParamType.FLOAT:
        return 1.0

    if param_type == ParamType.STRING:
        return f"{arg_name}_value"

    if param_type == ParamType.BOOL:
        return True

    if param_type == ParamType.FILE_ID:
        return "3fa85f64-5717-4562-b3fc-2c963f66afa6"

    return None


def _format_openapi_markdown_value(value: Any) -> str:
    """Format a value as markdown-friendly literal text.

    Args:
        value: Runtime value to serialize for docs.

    Returns:
        String representation suitable for markdown inline code.
    """

    if value is None:
        return "null"

    if isinstance(value, bool):
        return "true" if value else "false"

    return str(value)


def _patch_execute_contract(schema: dict[str, Any], app: FastAPI) -> None:
    """Patch `/v1/execute` to reflect action-driven runtime contracts.

    This function dynamically enriches the `/v1/execute` operation using
    the action registry by generating request/response variants, providing
    rich examples, and annotating middleware-driven behavior.

    Args:
        schema: Mutable OpenAPI schema document.
        app: FastAPI application used to derive runtime metadata.
    """

    paths = schema.get("paths", {})
    execute = paths.get("/v1/execute")
    if not execute:
        return

    post = execute.get("post")
    if not post:
        return

    post["tags"] = ["Execution"]
    registry = getattr(app.state, "action_registry", None)
    if not isinstance(registry, ActionRegistry):
        return

    components = schema.setdefault("components", {})
    schemas_section = components.setdefault("schemas", {})

    # ------------------------------------------------------------------
    # 1. Ensure all action models are registered in components.schemas
    # ------------------------------------------------------------------
    _register_model(ExecuteRequest, schemas_section, nested=True)
    _register_model(ExecuteActionData, schemas_section, nested=True)
    for name in registry.list_names():
        spec = registry.get(name)
        _register_model(spec.params_model, schemas_section, nested=True)

    # ------------------------------------------------------------------
    # 2. Build request oneOf variants + discriminator
    # ------------------------------------------------------------------

    request_variants = []
    request_examples = {}

    for name in registry.list_names():
        spec = registry.get(name)
        action_markdown = _build_execute_action_markdown(spec)
        action_summary = spec.summary or spec.description or "Execute action"

        variant: dict[str, Any] = {
            "type": "object",
            "description": action_markdown,
            "properties": {
                "action": {"type": "string", "const": name},
                "params": {
                    "$ref": f"#/components/schemas/{spec.params_model.__name__}"
                },
            },
            "required": ["action", "params"],
        }

        if spec.deprecated:
            variant["deprecated"] = True

        request_variants.append(variant)

        params_example = _build_execute_params_example(spec)

        # Build request example
        request_examples[name] = {
            "summary": f"{name}: {action_summary}",
            "description": action_markdown,
            "value": {
                "action": name,
                "params": params_example,
            },
        }

    request_body = post.setdefault("requestBody", {})
    content = request_body.setdefault("content", {})
    app_json = content.setdefault("application/json", {})

    app_json["schema"] = {
        "oneOf": request_variants,
        "discriminator": {
            "propertyName": "action",
        },
    }

    request_body["description"] = (
        "Request body with a required `action` selector and "
        "action-specific `params`.\n\n"
        "Select an example below to inspect the exact parameter contract for"
        " each action."
    )

    app_json["examples"] = request_examples

    # ------------------------------------------------------------------
    # 3. Build response 200 with dynamic result oneOf
    # ------------------------------------------------------------------

    response_examples = {}

    for name in registry.list_names():
        response_examples[name] = {
            "summary": f"Response for action: {name}",
            "value": {
                "success": True,
                "error": None,
                "data": {
                    "exit_code": 0,
                    "stdout": "",
                    "stdout_encoding": "utf-8",
                    "stderr": "",
                    "stderr_encoding": "utf-8",
                    "exec_time": 0.01,
                    "pid": 12345,
                    "truncated": False,
                    "redacted": False,
                },
            },
        }

    responses = post.setdefault("responses", {})
    response_200 = responses.setdefault("200", {})
    response_200_content = response_200.setdefault("content", {})
    response_200_json = response_200_content.setdefault("application/json", {})

    response_200_json["examples"] = response_examples

    # ------------------------------------------------------------------
    # 4. Explicit error responses
    # ------------------------------------------------------------------

    errors_by_status: dict[int, list[ErrorDef]] = defaultdict(list)

    # Dynamically build error responses from centralized error definitions.
    for err in PUBLIC_HTTP_ERRORS:
        errors_by_status[err.http_status].append(err)

    for status, error_defs in errors_by_status.items():
        response = responses.setdefault(str(status), {"description": f"{status} error"})

        content = response.setdefault("content", {})
        json_content = content.setdefault("application/json", {})

        error_examples = {}

        for err in error_defs:
            error_examples[err.code] = {
                "summary": err.code,
                "value": {
                    "success": False,
                    "error": {
                        "code": err.code,
                        "message": err.default_message,
                    },
                    "data": None,
                },
            }

        json_content["examples"] = error_examples

    # ------------------------------------------------------------------
    # 5. Inject dynamic description listing actions
    # ------------------------------------------------------------------

    action_lines = []
    for name in registry.list_names():
        spec = registry.get(name)
        label = f"- `{name}`"
        if spec.summary:
            label += f": {spec.summary}"
        if spec.deprecated:
            label += " _(deprecated)_"
        action_lines.append(label)

    dynamic_description = (
        "Executes a registered SEG action within the secure sandbox environment.\n\n"
        "### Supported Actions\n\n" + "\n".join(action_lines)
    )

    post["description"] = dynamic_description

    # ------------------------------------------------------------------
    # 6. Middleware metadata (vendor extension)
    # ------------------------------------------------------------------

    post["x-seg-integrity"] = {
        "content_type_required": "application/json",
        "body_limit_bytes": getattr(app.state.settings, "seg_max_file_bytes", None),
        "enforced_by": "RequestIntegrityMiddleware",
    }


def _patch_operation_contract(
    schema: dict[str, Any],
    *,
    path: str,
    method: str,
    errors: list[ErrorDef] | None = None,
    success_example: dict[str, Any] | None = None,
) -> None:
    """Apply SEG OpenAPI contract overrides to a single operation.

    An operation is defined as a combination of path + HTTP method.

    This function:
    - Injects SEG error examples grouped by HTTP status
    - Removes FastAPI-generated schemas when necessary
    - Optionally overrides the success response example

    Args:
        schema: Mutable OpenAPI schema document.
        path: API path (e.g. `/v1/files`).
        method: HTTP method (e.g. `post`, `get`).
        errors: Optional list of ErrorDef objects to expose.
        success_example: Optional success response example payload.
    """

    paths = schema.get("paths", {})
    path_item = paths.get(path)
    if not path_item:
        return

    operation = path_item.get(method)
    if not operation:
        return

    responses = operation.setdefault("responses", {})

    # ------------------------------------------------------------------
    # 1. Patch error responses
    # ------------------------------------------------------------------

    if errors:
        grouped: dict[int, list[ErrorDef]] = {}
        for err in errors:
            grouped.setdefault(err.http_status, []).append(err)

        for status, errs in grouped.items():
            response = responses.setdefault(
                str(status),
                {"description": f"{status} error"},
            )

            content = response.setdefault("content", {})
            json_content = content.setdefault("application/json", {})

            json_content["examples"] = {
                err.code: {
                    "summary": err.code,
                    "value": {
                        "success": False,
                        "error": {
                            "code": err.code,
                            "message": err.default_message,
                        },
                        "data": None,
                    },
                }
                for err in errs
            }

            json_content.pop("schema", None)

    # ------------------------------------------------------------------
    # 2. Patch success example
    # ------------------------------------------------------------------

    if success_example:
        for code in ("200", "201"):
            if code in responses:
                content = responses[code].setdefault("content", {})
                json_content = content.setdefault("application/json", {})
                json_content["example"] = success_example
                break


def _build_422_examples() -> dict[str, Any]:
    """Build standardized 422 error examples from public SEG error definitions.

    This helper constructs OpenAPI-compatible example payloads for all
    public errors with HTTP status 422 (Unprocessable Entity). Each example
    follows the canonical SEG response envelope format, ensuring consistency
    across all endpoints.

    The generated examples are used to replace FastAPI's default validation
    error schema, which does not align with SEG's error contract.

    Returns:
        Dictionary mapping error codes to OpenAPI example objects, where each
        example includes a summary and a fully structured response payload.
    """

    return {
        err.code: {
            "summary": err.code,
            "value": {
                "success": False,
                "error": {
                    "code": err.code,
                    "message": err.default_message,
                },
                "data": None,
            },
        }
        for err in PUBLIC_HTTP_ERRORS
        if err.http_status == 422
    }


def _replace_default_422(schema: dict[str, Any]) -> None:
    """Replace all default FastAPI 422 responses with SEG error contract.

    This function iterates over all registered API operations and replaces
    any existing HTTP 422 response definitions with a standardized SEG
    error contract. The replacement removes references to FastAPI's internal
    validation schemas (e.g. HTTPValidationError) and injects consistent
    example-based responses derived from centralized error definitions.

    This ensures:
    - Full alignment with SEG's ResponseEnvelope structure
    - Elimination of framework-specific validation artifacts
    - A deterministic and stable OpenAPI contract across all endpoints

    Args:
        schema: Mutable OpenAPI schema document to be patched in-place.
    """
    paths = schema.get("paths", {})

    for _path, path_item in paths.items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            responses = operation.get("responses", {})
            if "422" not in responses:
                continue

            responses["422"] = {
                "description": "422 error",
                "content": {"application/json": {"examples": _build_422_examples()}},
            }


def _inject_middleware_errors(
    schema: dict[str, Any],
    middleware_error_map: list[ErrorDef],
) -> None:
    """Inject middleware-level error responses into protected endpoints.

    This function adds standardized SEG error responses that originate from
    global middleware layers, such as authentication, rate limiting, and
    timeout enforcement. The injected responses are applied to all protected
    operations and skipped for explicitly public endpoints.

    The function expects a list of `ErrorDef` values representing middleware
    failures that may be returned before a request reaches the route handler.

    Notes:
        - Public operations are identified by `security=[]`.
        - Any existing framework-generated JSON schema for the injected
          status code is removed to avoid leaking FastAPI-specific contracts.
        - Response headers such as `Retry-After` for HTTP 429 are expected
          to be added later by `_inject_response_headers(...)`.

    Args:
        schema: Mutable OpenAPI schema document to patch in-place.
        middleware_error_map: List of SEG public error definitions that may
            be returned by middleware.

    Returns:
        None.
    """

    paths = schema.get("paths", {})

    errors_by_status: dict[int, list[ErrorDef]] = {}
    for err in middleware_error_map:
        errors_by_status.setdefault(err.http_status, []).append(err)

    for path_item in paths.values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            # Public endpoints are explicitly marked with empty security.
            if operation.get("security") == []:
                continue

            responses = operation.setdefault("responses", {})

            for status, error_defs in errors_by_status.items():
                response = responses.setdefault(
                    str(status),
                    {"description": f"{status} error"},
                )

                content = response.setdefault("content", {})
                json_content = content.setdefault("application/json", {})

                json_content["examples"] = {
                    err.code: {
                        "summary": err.code,
                        "value": {
                            "success": False,
                            "error": {
                                "code": err.code,
                                "message": err.default_message,
                            },
                            "data": None,
                        },
                    }
                    for err in error_defs
                }

                json_content.pop("schema", None)


def _patch_custom_schemas(schema: dict[str, Any]) -> None:
    """Ensure SEG-specific models and metadata appear in components.

    Args:
        schema: Mutable OpenAPI schema document.
    """
    # Register models that are reused by multiple patches and define the
    # `ErrorInfo.code` enum based on centralized public errors.
    components = schema.get("components", {})
    schemas = components.get("schemas", {})

    _register_model(ResponseEnvelope, schemas, nested=True)
    _register_model(ErrorInfo, schemas, nested=True)

    # Define enum for ErrorInfo.code based on PUBLIC_HTTP_ERRORS
    error_codes = [err.code for err in PUBLIC_HTTP_ERRORS]
    if "ErrorInfo" in schemas:
        error_info_schema = schemas["ErrorInfo"]
        properties = error_info_schema.setdefault("properties", {})
        code_prop = properties.setdefault("code", {})
        code_prop["enum"] = error_codes


def _prune_internal_schemas(schema: dict[str, Any]) -> None:
    """Remove internal-only schema definitions from the OpenAPI document.

    Args:
        schema: Mutable OpenAPI schema document.
    """
    components = schema.get("components", {})
    schemas = components.get("schemas", {})

    # Delete internal-only schemas that should not be exposed
    # in the public OpenAPI document.
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)
    schemas.pop("HealthResult", None)
    schemas.pop("ResponseEnvelope_HealthResult_", None)
    schemas.pop("ResponseEnvelope_Any_", None)


def _apply_response_contract_overrides(
    schema: dict[str, Any],
    response_contract_overrides: dict[str, dict[str, Any]],
) -> None:
    """Apply explicit response contract overrides to selected operations.

    This function allows declarative replacement of automatically generated
    OpenAPI response contracts. It is intended for endpoints whose runtime
    behavior (e.g., non-JSON media types, streaming responses, binary output)
    cannot be correctly inferred from FastAPI's default schema generation.

    The overrides dictionary must follow this structure:

        {
            "/path": {
                "method": "get" | "post" | ...,
                "responses": {
                    "200": {
                        "description": "...",
                        "content": {
                            "<media-type>": {
                                "schema": {...},
                                "example": ...
                            }
                        }
                    },
                    ...
                }
            }
        }

    Existing response definitions for the specified path + method
    will be replaced with the provided structure.

    Args:
        schema: Mutable OpenAPI schema document.
        response_contract_overrides: Declarative response definitions
            that override the auto-generated contracts.
    """

    paths = schema.get("paths", {})

    for path, override in response_contract_overrides.items():
        method = override.get("method")
        responses_override = override.get("responses")

        if not method or not responses_override:
            continue

        operation = paths.get(path, {}).get(method.lower())
        if not operation:
            continue

        # Replace entire responses section for determinism
        operation["responses"] = responses_override
