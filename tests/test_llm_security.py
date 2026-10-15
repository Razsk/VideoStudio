import json
from pathlib import Path

import httpx
import pytest

from videostudio.llm import (
    DEFAULT_MODELS,
    LLMConfig,
    LLMGateway,
    SecureCredentialStore,
    SecurityError,
    redact_secrets,
    validate_provider_endpoint,
)
from videostudio.orchestrator import DurableMacroOrchestrator
from videostudio.server import create_app
from videostudio.storage import StudioStorage
from fastapi.testclient import TestClient


def test_secret_store_masks_keys_and_never_serializes_plaintext(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENROUTER_API_KEY=sk-or-v1-99887766554433221100abcdef\n"
        "GEMINI_API_KEY=AIzaSyDummyKeyForTesting123456789\n",
        encoding="utf-8",
    )

    store = SecureCredentialStore(dotenv_paths=[env_file])
    status = store.get_provider_status()

    assert status["openrouter"]["configured"] is True
    # Ensure full secret is NEVER present in status output
    status_json = json.dumps(status)
    assert "99887766554433221100abcdef" not in status_json
    assert "AIzaSyDummyKeyForTesting123456789" not in status_json
    assert status["openrouter"]["masked_key"].startswith("sk-or-")
    assert status["openrouter"]["masked_key"].endswith("cdef")

    cfg = LLMConfig(provider="openrouter", model="anthropic/claude-3.7-sonnet")
    dumped = json.dumps(cfg.model_dump())
    assert "99887766554433221100abcdef" not in dumped


def test_secret_redaction_scrubs_leaked_tokens_from_errors():
    raw_err = (
        "HTTP Error with Authorization: Bearer sk-or-v1-secret1234567890abcdef "
        "and key AIzaSySecretKey9876543210 or sk-proj-9988776655443322"
    )
    scrubbed = redact_secrets(raw_err)
    assert "sk-or-v1-secret1234567890abcdef" not in scrubbed
    assert "AIzaSySecretKey9876543210" not in scrubbed
    assert "sk-proj-9988776655443322" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_ssrf_and_insecure_transport_protection():
    # Valid HTTPS OpenRouter endpoint
    validate_provider_endpoint("openrouter", "https://openrouter.ai/api/v1/chat/completions")

    # Reject HTTP (non-TLS) for cloud providers
    with pytest.raises(SecurityError, match="HTTPS is required"):
        validate_provider_endpoint("openrouter", "http://openrouter.ai/api/v1/chat/completions")

    # Reject untrusted host (SSRF protection)
    with pytest.raises(SecurityError, match="Untrusted endpoint host"):
        validate_provider_endpoint("openrouter", "https://evil.example.com/api/v1/chat/completions")

    # Reject non-loopback host for local Ollama
    with pytest.raises(SecurityError, match="Ollama endpoint must be loopback"):
        validate_provider_endpoint("ollama", "http://192.168.1.50:11434/api/chat")


def test_openrouter_gateway_structured_json_call_with_mock_transport(tmp_path: Path):
    captured_headers = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "episode_id": "S01E01",
                                    "story_seed": "Beacon 9 signal",
                                    "premise": "OpenRouter synthesized premise for Beacon 9.",
                                    "tone": "Neo-noir hard sci-fi",
                                    "target_conflicts": ["Signal decryption vs. lockdown"],
                                    "immutable_facts": ["Elena commands Helios Dome"],
                                    "lore_entities_referenced": ["CHAR_ELENA_VANCE"],
                                    "tonal_precedents": ["Chiaroscuro tension"],
                                    "setting_adherence_score": 0.97,
                                }
                            )
                        }
                    }
                ]
            },
        )

    store = SecureCredentialStore(dotenv_paths=[])
    store.set_session_key("openrouter", "sk-or-v1-testkey1234567890abcdef")

    gateway = LLMGateway(
        credential_store=store,
        http_transport=httpx.MockTransport(mock_handler),
    )
    cfg = LLMConfig(provider="openrouter", model="anthropic/claude-3.7-sonnet")

    from videostudio.schemas import ThematicDossier

    dossier = gateway.generate_structured(
        config=cfg,
        system_prompt="You are the Research and Lore Agent.",
        user_prompt="Synthesize dossier for Beacon 9.",
        response_model=ThematicDossier,
    )
    assert dossier.premise == "OpenRouter synthesized premise for Beacon 9."
    assert dossier.setting_adherence_score == 0.97
    assert captured_headers.get("authorization") == "Bearer sk-or-v1-testkey1234567890abcdef"
    assert captured_headers.get("x-title") == "VideoStudio"


def test_server_llm_endpoints_never_leak_keys_in_checkpoints_or_responses(tmp_path: Path):
    app = create_app(root_dir=tmp_path)
    client = TestClient(app)

    # Set an OpenRouter key via secure session endpoint
    secret_val = "sk-or-v1-supersecret9999888877776666"
    res_set = client.post(
        "/api/llm/credentials",
        json={"provider": "openrouter", "api_key": secret_val},
    )
    assert res_set.status_code == 200
    assert secret_val not in res_set.text
    assert res_set.json()["configured"] is True

    # Verify provider catalog endpoint masks the key
    res_list = client.get("/api/llm/providers")
    assert res_list.status_code == 200
    assert secret_val not in res_list.text
    assert res_list.json()["providers"]["openrouter"]["configured"] is True
    assert "openrouter" in DEFAULT_MODELS
