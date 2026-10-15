from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, SecretStr

T = TypeVar("T", bound=BaseModel)

LLMProviderType = Literal[
    "deterministic",
    "openrouter",
    "gemini",
    "openai",
    "anthropic",
    "ollama",
]

PROVIDER_ENV_VARS: Dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

ALLOWED_PROVIDER_HOSTS: Dict[str, set[str]] = {
    "openrouter": {"openrouter.ai"},
    "gemini": {"generativelanguage.googleapis.com"},
    "openai": {"api.openai.com"},
    "anthropic": {"api.anthropic.com"},
    "ollama": {"127.0.0.1", "localhost", "::1"},
}

DEFAULT_ENDPOINTS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "ollama": "http://127.0.0.1:11434/api/chat",
}

DEFAULT_MODELS: Dict[str, str] = {
    "deterministic": "local-deterministic-v1",
    "openrouter": "anthropic/claude-3.7-sonnet",
    "gemini": "gemini-2.5-pro",
    "openai": "gpt-4o",
    "anthropic": "claude-3-7-sonnet-latest",
    "ollama": "qwen2.5:14b",
}

SUGGESTED_MODELS: Dict[str, List[str]] = {
    "deterministic": ["local-deterministic-v1"],
    "openrouter": [
        "anthropic/claude-3.7-sonnet",
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash",
        "openai/gpt-4o",
        "deepseek/deepseek-r1",
        "meta-llama/llama-3.3-70b-instruct",
        "qwen/qwen-2.5-72b-instruct",
    ],
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
    "openai": [
        "gpt-4o",
        "o3-mini",
    ],
    "anthropic": [
        "claude-3-7-sonnet-latest",
        "claude-3-5-haiku-latest",
    ],
    "ollama": [
        "qwen2.5:14b",
        "llama3.3:70b",
        "deepseek-r1:14b",
    ],
}


class SecurityError(ValueError):
    """Raised when an LLM endpoint or credential operation violates security policy."""


_SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{12,}\b"),
]


def redact_secrets(text: str) -> str:
    """Scrub API keys and Bearer tokens from logs, exceptions, and diagnostic strings."""
    scrubbed = text
    for pat in _SECRET_PATTERNS:
        scrubbed = pat.sub("[REDACTED]", scrubbed)
    return scrubbed


def mask_key_preview(raw_key: str) -> str:
    """Return a safe masked preview (e.g. 'sk-or-...cdef') without exposing the secret."""
    cleaned = raw_key.strip()
    if len(cleaned) <= 10:
        return "****"
    return f"{cleaned[:6]}...{cleaned[-4:]}"


def validate_provider_endpoint(provider: str, url: str) -> None:
    """
    SSRF & Transport Security Gate:
    - Cloud providers (openrouter, gemini, openai, anthropic) MUST use HTTPS and match
      the strict host allowlist.
    - Local Ollama MUST target a loopback address (127.0.0.1, localhost, ::1).
    """
    if provider == "deterministic":
        return

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed_hosts = ALLOWED_PROVIDER_HOSTS.get(provider, set())

    if provider == "ollama":
        if host not in allowed_hosts:
            raise SecurityError(
                f"Ollama endpoint must be loopback (127.0.0.1 or localhost), got '{host}'"
            )
        return

    if parsed.scheme.lower() != "https":
        raise SecurityError(
            f"HTTPS is required for cloud provider '{provider}', got scheme '{parsed.scheme}'"
        )
    if host not in allowed_hosts:
        raise SecurityError(
            f"Untrusted endpoint host '{host}' for provider '{provider}'. "
            f"Allowed hosts: {sorted(allowed_hosts)}"
        )


class LLMConfig(BaseModel):
    """
    Serializable LLM configuration.
    Intentionally stores NO raw API keys so checkpoints and logs remain 100% secret-free.
    """

    provider: LLMProviderType = "deterministic"
    model: str = "local-deterministic-v1"
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    max_tokens: int = Field(default=4096, ge=256, le=16384)
    fallback_to_deterministic: bool = True


class SecureCredentialStore:
    """
    Holds API credentials in memory wrapped in Pydantic SecretStr, loading from
    environment variables or local .env files without echoing or persisting secrets to checkpoints.
    """

    def __init__(self, dotenv_paths: Optional[List[Path]] = None) -> None:
        self._secrets: Dict[str, SecretStr] = {}
        if dotenv_paths is None:
            dotenv_paths = [Path(".env"), Path.home() / ".env"]
        self._load_from_dotenv_files(dotenv_paths)
        self._load_from_environ()

    def _load_from_dotenv_files(self, paths: List[Path]) -> None:
        env_to_provider = {v: k for k, v in PROVIDER_ENV_VARS.items()}
        for p in paths:
            if not p.is_file():
                continue
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    key, val = stripped.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key in env_to_provider and val:
                        self._secrets[env_to_provider[key]] = SecretStr(val)
            except OSError:
                continue

    def _load_from_environ(self) -> None:
        for provider, env_var in PROVIDER_ENV_VARS.items():
            val = os.environ.get(env_var, "").strip()
            if val:
                self._secrets[provider] = SecretStr(val)

    def set_session_key(self, provider: str, api_key: str) -> None:
        """Store an API key in memory for the current process session only."""
        provider_clean = provider.lower().strip()
        if provider_clean not in PROVIDER_ENV_VARS:
            raise ValueError(f"Unsupported credential provider: {provider}")
        cleaned_key = api_key.strip()
        if not cleaned_key:
            self._secrets.pop(provider_clean, None)
        else:
            self._secrets[provider_clean] = SecretStr(cleaned_key)

    def get_secret(self, provider: str) -> Optional[SecretStr]:
        return self._secrets.get(provider.lower().strip())

    def has_key(self, provider: str) -> bool:
        if provider in ("deterministic", "ollama"):
            return True
        return provider in self._secrets

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        status: Dict[str, Dict[str, Any]] = {}
        for prov in ("deterministic", "openrouter", "gemini", "openai", "anthropic", "ollama"):
            secret = self._secrets.get(prov)
            env_var = PROVIDER_ENV_VARS.get(prov)
            configured = True if prov in ("deterministic", "ollama") else (secret is not None)
            masked = (
                "not-required"
                if prov in ("deterministic", "ollama")
                else (mask_key_preview(secret.get_secret_value()) if secret else None)
            )
            status[prov] = {
                "provider": prov,
                "configured": configured,
                "env_var": env_var,
                "masked_key": masked,
                "default_model": DEFAULT_MODELS[prov],
                "suggested_models": SUGGESTED_MODELS[prov],
            }
        return status


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


class LLMGateway:
    """
    Secure, schema-enforcing LLM client supporting OpenRouter, Google Gemini,
    OpenAI, Anthropic Claude, and local Ollama.
    """

    def __init__(
        self,
        credential_store: Optional[SecureCredentialStore] = None,
        http_transport: Optional[httpx.BaseTransport] = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.credential_store = credential_store or SecureCredentialStore()
        self._transport = http_transport
        self.timeout_seconds = timeout_seconds

    def generate_structured(
        self,
        config: LLMConfig,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
    ) -> T:
        provider = config.provider
        if provider == "deterministic":
            raise RuntimeError("Deterministic mode does not invoke remote LLMGateway")

        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            "CRITICAL: Respond ONLY with a valid JSON object matching this exact JSON Schema:\n"
            f"{schema_json}"
        )

        endpoint_template = DEFAULT_ENDPOINTS[provider]
        endpoint = endpoint_template.format(model=config.model)
        validate_provider_endpoint(provider, endpoint)

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        body: Dict[str, Any] = {}

        if provider in ("openrouter", "openai"):
            secret = self.credential_store.get_secret(provider)
            if not secret:
                raise SecurityError(
                    f"Missing API key for provider '{provider}'. "
                    f"Set {PROVIDER_ENV_VARS[provider]} in ~/.env or via the session credential store."
                )
            headers["Authorization"] = f"Bearer {secret.get_secret_value()}"
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/Razsk/VideoStudio"
                headers["X-Title"] = "VideoStudio"
            body = {
                "model": config.model,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt},
                ],
            }

        elif provider == "gemini":
            secret = self.credential_store.get_secret("gemini")
            if not secret:
                raise SecurityError(
                    "Missing API key for provider 'gemini'. Set GEMINI_API_KEY in ~/.env."
                )
            # Send API key in header (never in URL query string!)
            headers["x-goog-api-key"] = secret.get_secret_value()
            body = {
                "systemInstruction": {"parts": [{"text": full_system}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": config.temperature,
                    "maxOutputTokens": config.max_tokens,
                    "responseMimeType": "application/json",
                },
            }

        elif provider == "anthropic":
            secret = self.credential_store.get_secret("anthropic")
            if not secret:
                raise SecurityError(
                    "Missing API key for provider 'anthropic'. Set ANTHROPIC_API_KEY in ~/.env."
                )
            headers["x-api-key"] = secret.get_secret_value()
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": config.model,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "system": full_system,
                "messages": [{"role": "user", "content": user_prompt}],
            }

        elif provider == "ollama":
            body = {
                "model": config.model,
                "format": "json",
                "stream": False,
                "messages": [
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt},
                ],
            }

        try:
            with httpx.Client(
                transport=self._transport, timeout=self.timeout_seconds
            ) as client:
                resp = client.post(endpoint, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            safe_msg = redact_secrets(str(exc))
            raise RuntimeError(f"LLM call to {provider} ({config.model}) failed: {safe_msg}") from None

        raw_content = self._extract_content_by_provider(provider, data)
        parsed_dict = _extract_json_object(raw_content)
        return response_model.model_validate(parsed_dict)

    @staticmethod
    def _extract_content_by_provider(provider: str, data: Dict[str, Any]) -> str:
        if provider in ("openrouter", "openai"):
            return str(data["choices"][0]["message"]["content"])
        if provider == "gemini":
            return str(data["candidates"][0]["content"]["parts"][0]["text"])
        if provider == "anthropic":
            return str(data["content"][0]["text"])
        if provider == "ollama":
            return str(data["message"]["content"])
        raise ValueError(f"Unknown provider response format: {provider}")
