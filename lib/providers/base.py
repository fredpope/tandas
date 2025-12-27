from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, List, Optional


@dataclass
class ProviderConfig:
    name: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    extra: Optional[Dict[str, str]] = None


@dataclass
class TestContext:
    tanda: Dict
    app_url: Optional[str] = None
    existing_tests: Optional[List[str]] = None
    coverage_tags: Optional[List[str]] = None


class GenerationProviderError(Exception):
    pass


class AIProvider:
    """Abstract base for AI providers."""

    provider_name = "base"

    def __init__(self, config: ProviderConfig):
        self.config = config

    def generate_test(self, context: TestContext) -> str:
        raise NotImplementedError("Implement in subclass")

    @staticmethod
    def build_prompt(context: TestContext) -> str:
        tanda = context.tanda
        title = tanda.get("title", "Unnamed Tandas entry")
        coverage = ", ".join(context.coverage_tags or tanda.get("covers", [])) or "(not specified)"
        file_hint = tanda.get("file") or "tests/generated/<slug>.spec.ts"
        deps = ", ".join(tanda.get("depends_on", [])) or "none"
        return dedent(
            f"""
            Generate a Playwright test for "{title}".

            Requirements:
            - File path hint: {file_hint}
            - Coverage tags: {coverage}
            - Depends on: {deps}
            - Application URL: {context.app_url or 'unknown'}
            - Reference existing tests: {', '.join(context.existing_tests or []) or 'none'}

            Respond with runnable TypeScript Playwright test code and a short comment header summarizing intent.
            """
        ).strip()
