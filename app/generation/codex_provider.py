"""ChatGPT-plan adapter using the official, already authenticated Codex CLI.

Only the generation provider changes. Ingestion, vector search, BM25, RRF,
reranking, citations, and evaluation remain the upstream implementation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

import certifi

from app.core.config import settings
from app.generation.providers import BaseLLM, LLMResponse


class CodexLLM(BaseLLM):
    name = "codex"

    def __init__(self) -> None:
        self.model = settings.codex_model or "account-default"
        self.runtime = Path(__file__).resolve().parents[2] / ".private" / "codex"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.scratch = self.runtime / "scratch"
        self.scratch.mkdir(parents=True, exist_ok=True)

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Explicitly keep this provider on the existing ChatGPT login.
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)
        env.setdefault("CODEX_CA_CERTIFICATE", certifi.where())
        env["CODEX_SQLITE_HOME"] = str(self.runtime / "sqlite")
        Path(env["CODEX_SQLITE_HOME"]).mkdir(parents=True, exist_ok=True)
        return env

    def health(self) -> bool:
        try:
            checked = subprocess.run(
                [settings.codex_binary, "login", "status"],
                env=self._env(), capture_output=True, timeout=15,
            )
            status = (checked.stdout + checked.stderr).decode("utf-8", errors="replace").lower()
            return checked.returncode == 0 and "logged in using chatgpt" in status
        except (OSError, subprocess.TimeoutExpired):
            return False

    def complete(self, prompt: str, system: str | None = None,
                 max_tokens: int = 1024, temperature: float = 0.1,
                 json_mode: bool = False) -> LLMResponse:
        # CLI generation does not expose the upstream sampling/token parameters.
        # JSON is parsed here; this adapter does not claim native JSON Mode.
        instructions = system or "Answer the supplied question."
        if json_mode:
            instructions += "\nReturn one valid JSON object only, without Markdown fences."
        message = ("You are the text-generation component of a document assistant. "
                   "Use only the supplied reference material. Do not inspect files or run tools.\n\n"
                   + instructions + "\n\n--- User request and reference material ---\n" + prompt)
        args = [settings.codex_binary, "exec", "--ignore-user-config", "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--json"]
        for config in [
            "features.shell_tool=false", "features.apps=false", "features.plugins=false",
            "features.hooks=false", "features.multi_agent=false", "features.memories=false",
            "features.goals=false", 'web_search="disabled"', 'approval_policy="never"',
            'model_reasoning_effort="low"',
            'forced_login_method="chatgpt"',
            "log_dir=" + json.dumps(str(self.runtime / "logs").replace("\\", "/")),
        ]:
            args.extend(["-c", config])
        if settings.codex_model:
            args.extend(["--model", settings.codex_model])
        args.append("-")
        started = time.perf_counter()
        try:
            result = subprocess.run(
                args, input=message, text=True, encoding="utf-8", errors="replace",
                capture_output=True, cwd=self.scratch, env=self._env(),
                timeout=settings.codex_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ChatGPT subscription response timed out; retry after checking the connection.") from exc
        except OSError as exc:
            raise RuntimeError("Could not start Codex CLI; check CODEX_BINARY and the local installation.") from exc
        texts, usage, completed = [], None, False
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                texts.append(item.get("text", ""))
            if event.get("type") == "turn.completed":
                completed, usage = True, event.get("usage")
        if result.returncode != 0 or not completed or not texts:
            # Do not expose raw CLI diagnostics, account details, or documents in API errors.
            raise RuntimeError("ChatGPT subscription generation did not complete. Check CLI login, connection and plan limits.")
        answer = texts[-1].strip()
        if json_mode:
            try:
                parsed = json.loads(answer)
                if not isinstance(parsed, dict):
                    raise ValueError("JSON object required")
            except ValueError as exc:
                raise RuntimeError("The subscription response was not a valid JSON object; structured output was not accepted.") from exc
        return LLMResponse(
            text=answer, provider=self.name, model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000,
            raw={"usage": usage, "transport": "official-codex-cli",
                 "sampling": "provider-default", "max_tokens_enforced": False},
        )
