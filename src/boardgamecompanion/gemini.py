from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_STABLE_MODEL_FIELDS = (
    "name",
    "baseModelId",
    "version",
    "displayName",
    "inputTokenLimit",
    "outputTokenLimit",
    "supportedGenerationMethods",
)


class GeminiModelMetadataError(RuntimeError):
    pass


def validate_model_id(model: str) -> str:
    value = model.strip()
    if not value or not MODEL_ID_RE.fullmatch(value):
        raise GeminiModelMetadataError("Gemini model identifier is invalid")
    return value


def stable_model_metadata(model: dict[str, Any]) -> dict[str, Any]:
    return {
        field: model[field]
        for field in _STABLE_MODEL_FIELDS
        if field in model
    }


def resolve_model(
    payload: Any,
    *,
    configured_model: str,
    required_method: str,
) -> tuple[str, str]:
    model_id = validate_model_id(configured_model)
    if not isinstance(payload, dict):
        raise GeminiModelMetadataError("Gemini model metadata is invalid")
    name = payload.get("name")
    if name != f"models/{model_id}":
        raise GeminiModelMetadataError("Gemini model metadata does not match configured model")
    methods = payload.get("supportedGenerationMethods")
    if not isinstance(methods, list) or required_method not in methods:
        raise GeminiModelMetadataError(
            f"Gemini model {model_id!r} does not support {required_method}"
        )
    metadata = stable_model_metadata(payload)
    if not metadata.get("version"):
        raise GeminiModelMetadataError("Gemini model metadata has no version")
    raw = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return model_id, hashlib.sha256(raw.encode("utf-8")).hexdigest()
