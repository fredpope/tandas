from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .base import AIProvider, GenerationProviderError, TestContext


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def generate_test(self, context: TestContext) -> str:
        prompt = self.build_prompt(context)
        model = self.config.model or "gemini-pro"

        if not self.config.api_key:
            return self._missing_key_message(prompt)

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        url = f"{endpoint}?{urllib.parse.urlencode({'key': self.config.api_key})}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # pragma: no cover
            detail = exc.read().decode() if exc.fp else str(exc)
            raise GenerationProviderError(f"Gemini API error: {detail}")
        except urllib.error.URLError as exc:  # pragma: no cover
            raise GenerationProviderError(f"Gemini network error: {exc}")

        candidates = data.get("candidates") or []
        if not candidates:
            raise GenerationProviderError("Gemini returned empty candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
        if not text_parts:
            text_parts = [json.dumps(data)]
        return "\n".join(text_parts)

    @staticmethod
    def _missing_key_message(prompt: str) -> str:
        return "\n".join([
            "# Gemini provider not configured",
            "# Set GEMINI_API_KEY or edit .tandas/config.yaml to enable live generation.",
            "",
            prompt,
        ])
