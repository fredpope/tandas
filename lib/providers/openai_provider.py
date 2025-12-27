from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import AIProvider, GenerationProviderError, TestContext


OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(AIProvider):
    provider_name = "openai"

    def generate_test(self, context: TestContext) -> str:
        prompt = self.build_prompt(context)
        model = self.config.model or "gpt-4o-mini"

        if not self.config.api_key:
            return self._missing_key_message(prompt)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You generate Playwright tests."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }

        req = urllib.request.Request(
            OPENAI_URL,
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # pragma: no cover
            detail = exc.read().decode() if exc.fp else str(exc)
            raise GenerationProviderError(f"OpenAI API error: {detail}")
        except urllib.error.URLError as exc:  # pragma: no cover
            raise GenerationProviderError(f"OpenAI network error: {exc}")

        choices = data.get("choices") or []
        if not choices:
            raise GenerationProviderError("OpenAI returned empty choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not content:
            content = json.dumps(data)
        return content

    @staticmethod
    def _missing_key_message(prompt: str) -> str:
        return "\n".join([
            "# OpenAI provider not configured",
            "# Set OPENAI_API_KEY or edit .tandas/config.yaml to enable live generation.",
            "",
            prompt,
        ])
