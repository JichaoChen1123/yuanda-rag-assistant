"""Subscription transport regressions; no network or real model calls."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from app.generation.codex_provider import CodexLLM
from app.generation.providers import MultiProviderLLM


def reply(*texts, completed=True, code=0):
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": text}} for text in texts]
    if completed:
        events.append({"type": "turn.completed", "usage": {"output_tokens": 10}})
    return SimpleNamespace(returncode=code, stdout="\n".join(map(json.dumps, events)), stderr="private diagnostic")


def test_disabled_provider_override_cannot_bypass_subscription_only(monkeypatch):
    provider = MultiProviderLLM(order=["codex"])
    monkeypatch.setattr(provider, "_get", lambda name: pytest.fail("Disabled provider was instantiated"))
    with pytest.raises(ValueError, match="not enabled"):
        provider.complete("question", preferred="openai")


def test_final_json_ignores_preceding_commentary_and_clears_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("CODEX_API_KEY", "test-only-placeholder")
    def run(args, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "CODEX_API_KEY" not in kwargs["env"]
        assert 'forced_login_method="chatgpt"' in args
        assert args[-1] == "-"
        assert "question" not in args
        assert "question" in kwargs["input"]
        return reply("I will answer using the document.", '{"items": []}')
    monkeypatch.setattr(subprocess, "run", run)
    result = CodexLLM().complete("question", json_mode=True)
    assert json.loads(result.text) == {"items": []}
    assert result.provider == "codex"


@pytest.mark.parametrize("answer", ["42", "[]", "not JSON"])
def test_structured_response_requires_json_object(monkeypatch, answer):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: reply(answer))
    with pytest.raises(RuntimeError, match="not a valid JSON object"):
        CodexLLM().complete("question", json_mode=True)


def test_partial_response_is_not_accepted(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: reply("partial answer", completed=False))
    with pytest.raises(RuntimeError, match="did not complete"):
        CodexLLM().complete("question")


def test_cli_failure_does_not_expose_diagnostics(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: reply("", completed=False, code=1))
    with pytest.raises(RuntimeError) as error:
        CodexLLM().complete("question")
    assert "private diagnostic" not in str(error.value)


def test_timeout_does_not_expose_prompt_or_diagnostics(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private command", 1, output="private prompt")
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timed out") as error:
        CodexLLM().complete("question")
    assert "private prompt" not in str(error.value)


@pytest.mark.parametrize("status,expected", [(b"Logged in using ChatGPT", True), (b"Logged in using an API key", False)])
def test_health_requires_chatgpt_login(monkeypatch, status, expected):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"", stderr=status))
    assert CodexLLM().health() is expected
