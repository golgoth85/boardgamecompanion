"""Bounded, stateless cloud generation. Provider errors never include credentials/data."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import httpx

ENDPOINTS = {
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
}
DEFAULT_MODELS = {"deepseek": "deepseek-flash", "groq": "openai/gpt-oss-120b"}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CloudAIError(RuntimeError):
    pass


class CloudAIClient:
    def __init__(self, *, provider: str, api_key: str | None, model: str,
                 timeout_seconds: float = 120, client: httpx.Client | None = None,
                 rate_limiter=None):
        if provider not in ENDPOINTS:
            raise ValueError("Provider cloud non supportato")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}", model):
            raise ValueError("Modello cloud non valido")
        self.provider, self.model = provider, model
        self.api_key = (api_key or "").strip()
        self.base_url = ENDPOINTS[provider]
        self.timeout_seconds = timeout_seconds
        self.client, self.rate_limiter = client, rate_limiter

    def request(self, method: str, path: str, payload=None) -> dict:
        if not self.api_key:
            raise CloudAIError(f"Configura la chiave API {self.provider} nelle impostazioni AI")
        if self.rate_limiter:
            self.rate_limiter(f"{self.provider}:api", 0.5)
        def send(client):
            with client.stream(method, f"{self.base_url}/{path.lstrip('/')}",
                               headers={"Authorization": f"Bearer {self.api_key}"},
                               json=payload, timeout=self.timeout_seconds,
                               follow_redirects=False) as response:
                if response.status_code != 200:
                    descriptions = {401: "chiave non valida", 402: "credito esaurito",
                                    403: "accesso negato", 429: "limite di richieste raggiunto"}
                    reason = descriptions.get(response.status_code, "servizio non disponibile")
                    raise CloudAIError(f"{self.provider}: {reason} (HTTP {response.status_code})")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise CloudAIError(f"{self.provider}: risposta troppo grande")
                try:
                    result = json.loads(data)
                except (ValueError, RecursionError) as exc:
                    raise CloudAIError(f"{self.provider}: risposta JSON non valida") from exc
                if not isinstance(result, dict):
                    raise CloudAIError(f"{self.provider}: risposta non valida")
                return result
        try:
            if self.client is not None:
                return send(self.client)
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                return send(client)
        except httpx.HTTPError:
            raise CloudAIError(f"{self.provider}: connessione non riuscita o timeout") from None

    def models(self) -> list[dict[str, str]]:
        items = self.request("GET", "models").get("data")
        if not isinstance(items, list):
            raise CloudAIError(f"{self.provider}: elenco modelli non valido")
        models = [{"id": item["id"], "name": str(item.get("name") or item["id"])[:200]}
                for item in items[:200] if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}", item["id"])
                and not item["id"].startswith(("whisper", "canopylabs/", "meta-llama/llama-prompt-guard"))]
        if not models:
            raise CloudAIError(f"{self.provider}: nessun modello testuale disponibile")
        return models

    def describe(self) -> tuple[str, str]:
        models = self.models()
        match = next((item for item in models if item["id"] == self.model), None)
        if match is None:
            raise CloudAIError(f"{self.provider}: il modello selezionato non è disponibile")
        digest = hashlib.sha256(json.dumps(match, sort_keys=True).encode()).hexdigest()
        return self.model, digest

    def text(self, system: str, prompt: str, *, schema: dict | None = None,
             json_output: bool = False, max_tokens: int = 4096) -> str:
        if schema is not None:
            system += "\nReturn only JSON conforming to this schema:\n" + json.dumps(schema)
            json_output = True
        elif json_output:
            system += "\nReturn only a JSON object."
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "stream": False, "max_tokens": max_tokens,
        }
        if self.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        elif "gpt-oss" in self.model:
            payload["reasoning_effort"] = "low"
            payload["reasoning_format"] = "hidden"
        elif self.provider == "groq" and "qwen" in self.model.casefold():
            payload["reasoning_format"] = "hidden"
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        result = self.request("POST", "chat/completions", payload)
        try:
            choice = result["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError
            if choice.get("finish_reason") != "stop":
                raise CloudAIError(f"{self.provider}: risposta incompleta o rifiutata")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise CloudAIError(f"{self.provider}: risposta senza testo valido") from None
        return content

    def structured(self, system: str, payload: Any, *, schema: dict | None = None) -> dict:
        text = self.text(system, json.dumps(payload, ensure_ascii=False),
                         schema=schema, json_output=True)
        try:
            result = json.loads(text)
        except (ValueError, RecursionError):
            raise CloudAIError(f"{self.provider}: contenuto JSON non valido") from None
        if not isinstance(result, dict):
            raise CloudAIError(f"{self.provider}: oggetto JSON mancante")
        return result


def cloud_client(rag, provider: str | None = None, *, api_key: str | None = None,
                 model: str | None = None, rate_limiter=None) -> CloudAIClient:
    from boardgamecompanion.settings import settings
    provider = provider or rag.generation_provider
    return CloudAIClient(provider=provider,
                         api_key=api_key or getattr(rag, f"{provider}_api_key"),
                         model=model or getattr(rag, f"{provider}_generation_model"),
                         timeout_seconds=settings.cloud_generation_timeout_seconds,
                         rate_limiter=rate_limiter)
