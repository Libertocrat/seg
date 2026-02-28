from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from seg.actions.registry import get_registry_snapshot
from seg.core.errors import PUBLIC_HTTP_ERRORS, ErrorDef
from seg.core.schemas.envelope import ErrorInfo, ResponseEnvelope
from seg.core.schemas.execute import ExecuteRequest

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
        "url": "https://github.com/Libertocrat/secure-execution-gateway",
    }

    # Apply SEG-specific patches in stable order.
    # Order matters: security first, then endpoint-level patches,
    # then response header enrichment.
    _patch_custom_schemas(schema)
    _inject_security(schema)
    _patch_public_endpoints(schema)
    _patch_execute_contract(schema, app)
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
# /v1/execute dynamic contract
# ---------------------------------------------------------------------


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
    registry = get_registry_snapshot()
    components = schema.setdefault("components", {})
    schemas_section = components.setdefault("schemas", {})

    # ------------------------------------------------------------------
    # 1. Ensure all action models are registered in components.schemas
    # ------------------------------------------------------------------
    _register_model(ExecuteRequest, schemas_section, nested=True)
    for spec in registry.values():
        _register_model(spec.params_model, schemas_section, nested=True)
        if spec.result_model:
            _register_model(spec.result_model, schemas_section, nested=True)

    # ------------------------------------------------------------------
    # 2. Build request oneOf variants + discriminator
    # ------------------------------------------------------------------

    request_variants = []
    request_examples = {}

    for name, spec in registry.items():
        variant: dict[str, Any] = {
            "type": "object",
            "description": spec.description or spec.summary,
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

        if spec.params_example is not None:
            params_example = spec.params_example.model_dump(exclude_none=False)
        else:
            params_example = {}

        # Build request example
        request_examples[name] = {
            "summary": f"{name}: {spec.summary}",
            "description": spec.description,
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

    app_json["examples"] = request_examples

    # ------------------------------------------------------------------
    # 3. Build response 200 with dynamic result oneOf
    # ------------------------------------------------------------------

    result_refs = []
    response_examples = {}

    for name, spec in registry.items():
        if spec.result_model:
            result_refs.append(
                {"$ref": f"#/components/schemas/{spec.result_model.__name__}"}
            )

            if spec.result_model and spec.result_example is not None:
                data_example = spec.result_example.model_dump(exclude_none=False)
            else:
                data_example = {}

            response_examples[name] = {
                "summary": f"Response for action: {name}",
                "value": {
                    "success": True,
                    "error": None,
                    "data": data_example,
                },
            }

    responses = post.setdefault("responses", {})
    response_200 = responses.setdefault("200", {})
    response_200_content = response_200.setdefault("content", {})
    response_200_json = response_200_content.setdefault("application/json", {})

    if result_refs:
        response_200_json["schema"] = {
            "allOf": [
                {"$ref": "#/components/schemas/ResponseEnvelope"},
                {"properties": {"data": {"oneOf": result_refs}}},
            ]
        }

    response_200_json["examples"] = response_examples

    # ------------------------------------------------------------------
    # 4. Explicit error responses
    # ------------------------------------------------------------------

    errors_by_status: dict[int, list[ErrorDef]] = defaultdict(list)

    # Remove generic FastAPI 422 response if present to be replaced by
    # our more specific validation error definitions.
    if "422" in responses:
        responses.pop("422")

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
    for name, spec in registry.items():
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
        "body_limit_bytes": getattr(app.state.settings, "seg_max_bytes", None),
        "enforced_by": "RequestIntegrityMiddleware",
    }


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
