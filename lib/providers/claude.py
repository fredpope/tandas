from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import AIProvider, GenerationProviderError, ProviderConfig, TestContext


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class ClaudeProvider(AIProvider):
    provider_name = "claude"

    def generate_test(self, context: TestContext) -> str:
        prompt = self.build_prompt(context)
        model = self.config.model or "claude-3-5-sonnet-20240620"

        if not self.config.api_key:
            return self._missing_key_message(prompt)

        payload = {
            "model": model,
            "max_tokens": 1200,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            detail = exc.read().decode() if exc.fp else str(exc)
            raise GenerationProviderError(f"Claude API error: {detail}")
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise GenerationProviderError(f"Claude network error: {exc}")

        content = data.get("content") or []
        if not content:
            raise GenerationProviderError("Claude returned empty response")

        segment = content[0]
        text = segment.get("text") if isinstance(segment, dict) else None
        if not text:
            text = json.dumps(data)
        return text

    @staticmethod
    def _missing_key_message(prompt: str) -> str:
        return "\n".join([
            "# Claude provider not configured",
            "# Set ANTHROPIC_API_KEY or edit .tandas/config.yaml to enable live generation.",
            "",
            prompt,
        ])
