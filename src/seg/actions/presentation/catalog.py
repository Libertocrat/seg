"""Catalog builders for SEG public action/module discovery views."""

from __future__ import annotations

import csv
from typing import Iterable, Mapping

from seg.actions.models.core import ActionSpec
from seg.actions.models.presentation import ModuleSummary
from seg.actions.presentation.serializers import to_action_summary
from seg.actions.schemas.module import ModuleSpec


def _build_module_id(namespace: tuple[str, ...], module: str) -> str:
    """Build the fully qualified module identifier.

    Args:
        namespace: Module namespace segments.
        module: Bare module name.

    Returns:
        Dot-separated module identifier.
    """

    return ".".join((*namespace, module))


def _normalize(text: str) -> str:
    """Normalize free text used by catalog filters.

    Args:
        text: Input text to normalize.

    Returns:
        Lowercased and trimmed representation.
    """

    return text.lower().strip()


def _matches_query(text: str | None, query: str) -> bool:
    """Return whether a text value contains the normalized query.

    Args:
        text: Optional text field to evaluate.
        query: Normalized query term.

    Returns:
        True when query appears in the normalized text.
    """

    if not text:
        return False
    return query in _normalize(text)


def _parse_tags(tags_csv: str | None) -> tuple[str, ...]:
    """Normalize module tags CSV text into a deduplicated tuple.

    Args:
        tags_csv: Raw CSV tags string from module metadata.

    Returns:
        Deduplicated and lowercased tag tuple preserving first appearance.
    """

    if tags_csv is None:
        return ()

    rows = list(csv.reader([tags_csv]))
    if not rows:
        return ()

    tags: list[str] = []
    seen: set[str] = set()

    for token in rows[0]:
        normalized = token.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            tags.append(normalized)

    return tuple(tags)


def _collect_module_actions(
    action_specs: Iterable[ActionSpec],
    *,
    module_name: str,
    namespace: tuple[str, ...],
) -> list[ActionSpec]:
    """Collect action specs that belong to one module identity.

    Args:
        action_specs: Action specs available in the runtime registry.
        module_name: Bare module name.
        namespace: Namespace tuple for module identity.

    Returns:
        Action specs associated to the given module identity.
    """

    return [
        spec
        for spec in action_specs
        if spec.module == module_name and spec.namespace == namespace
    ]


def build_module_summaries(
    modules: list[ModuleSpec],
    actions: Mapping[str, ActionSpec],
) -> list[ModuleSummary]:
    """Build deterministic module summaries from module and action collections.

    Args:
        modules: Loaded ModuleSpec objects (ordered).
        actions: Mapping of runtime action name -> ActionSpec.

    Returns:
        Sorted list of public module summary models.
    """

    actions_by_name = actions

    results: list[ModuleSummary] = []

    for module in modules:
        namespace = module.namespace
        module_name = module.module
        module_id = _build_module_id(namespace, module_name)

        module_actions = _collect_module_actions(
            actions_by_name.values(),
            module_name=module_name,
            namespace=namespace,
        )

        summaries = [to_action_summary(action_spec) for action_spec in module_actions]

        results.append(
            ModuleSummary(
                module=module_name,
                module_id=module_id,
                namespace=".".join(namespace),
                namespace_path=namespace,
                description=module.description,
                tags=_parse_tags(module.tags),
                authors=tuple(module.authors) if module.authors else None,
                actions=sorted(summaries, key=lambda action: action.action),
            )
        )

    return sorted(results, key=lambda module_summary: module_summary.module_id)


def filter_modules(
    modules: list[ModuleSummary],
    *,
    q: str | None = None,
    tag: str | None = None,
) -> list[ModuleSummary]:
    """Apply optional query and tag filters to module summaries.

    Args:
        modules: Source module summaries.
        q: Optional free-text query.
        tag: Optional module tag filter.

    Returns:
        Filtered module summaries. For query matches at action level, only the
        matching actions are kept in each module summary.
    """

    if not q and not tag:
        return modules

    query = _normalize(q) if q else None
    tag_norm = _normalize(tag) if tag else None

    filtered: list[ModuleSummary] = []

    for module in modules:
        if tag_norm and tag_norm not in {tag_item.lower() for tag_item in module.tags}:
            continue

        if not query:
            filtered.append(module)
            continue

        matched_actions = [
            action
            for action in module.actions
            if (
                _matches_query(action.action, query)
                or _matches_query(action.summary, query)
                or _matches_query(action.description, query)
            )
        ]

        if matched_actions:
            filtered.append(
                ModuleSummary(
                    module=module.module,
                    module_id=module.module_id,
                    namespace=module.namespace,
                    namespace_path=module.namespace_path,
                    description=module.description,
                    tags=module.tags,
                    authors=module.authors,
                    actions=matched_actions,
                )
            )
            continue

    return filtered


def get_action(actions: Mapping[str, ActionSpec], action_name: str) -> ActionSpec:
    """Return one action spec by fully qualified action name from mapping.

    Args:
        actions: Mapping of runtime action name -> ActionSpec.
        action_name: Fully qualified runtime action name.

    Returns:
        Runtime action specification.
    """

    return actions[action_name]
