from __future__ import annotations

import hashlib
import json
from typing import Any

_STABLE_MODEL_FIELDS = (
    "type",
    "publisher",
    "key",
    "display_name",
    "architecture",
    "quantization",
    "size_bytes",
    "params_string",
    "max_context_length",
    "format",
    "capabilities",
    "variants",
    "selected_variant",
)


class LMStudioModelMetadataError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_model_metadata(model: dict[str, Any]) -> dict[str, Any]:
    return {
        field: model[field]
        for field in _STABLE_MODEL_FIELDS
        if field in model
    }


def model_fingerprint(model: dict[str, Any]) -> str:
    metadata = stable_model_metadata(model)
    key = metadata.get("key")
    if not isinstance(key, str) or not key.strip():
        raise LMStudioModelMetadataError("LM Studio model metadata has no stable key")
    raw = _canonical_json(metadata)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aliases(model: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for field in ("key", "display_name", "selected_variant"):
        value = model.get(field)
        if isinstance(value, str) and value:
            aliases.add(value)
    variants = model.get("variants")
    if isinstance(variants, list):
        aliases.update(
            item for item in variants if isinstance(item, str) and item
        )
    loaded_instances = model.get("loaded_instances")
    if isinstance(loaded_instances, list):
        for item in loaded_instances:
            if not isinstance(item, dict):
                continue
            value = item.get("id")
            if isinstance(value, str) and value:
                aliases.add(value)
    return aliases


def resolve_model(
    payload: Any,
    *,
    configured_model: str,
    expected_type: str,
) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise LMStudioModelMetadataError("LM Studio model list is invalid")
    models = payload.get("models")
    if not isinstance(models, list):
        raise LMStudioModelMetadataError("LM Studio model list is invalid")

    match: dict[str, Any] | None = None
    for item in models:
        if not isinstance(item, dict):
            continue
        if configured_model in _aliases(item):
            match = item
            break
    if match is None:
        raise LMStudioModelMetadataError(
            f"LM Studio model {configured_model!r} is not available"
        )

    model_type = match.get("type")
    if model_type != expected_type:
        raise LMStudioModelMetadataError(
            f"LM Studio model {configured_model!r} is not a {expected_type} model"
        )

    return configured_model, model_fingerprint(match)
