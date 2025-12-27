from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Type

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

from .providers.base import AIProvider, ProviderConfig, TestContext
from .providers.claude import ClaudeProvider
from .providers.openai_provider import OpenAIProvider
from .providers.gemini import GeminiProvider

PROVIDERS: Dict[str, Type[AIProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


class GenerationConfigError(Exception):
    pass


@dataclass
class AIConfig:
    default_provider: str
    providers: Dict[str, ProviderConfig]


def _resolve_env(value: Optional[str]) -> Optional[str]:
    if not value or not value.startswith("${"):
        return value
    env_var = value.strip()[2:-1]
    return os.environ.get(env_var)


def load_ai_config(config_path: Path) -> AIConfig:
    if config_path.exists():
        if yaml is None:
            raise GenerationConfigError("PyYAML is required to parse config.yaml. Install with 'pip install pyyaml'.")
        with config_path.open() as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = {}

    ai_block = data.get("ai", {}) if isinstance(data, dict) else {}
    default_provider = ai_block.get("default_provider", "claude")
    provider_settings = ai_block.get("providers", {})

    providers: Dict[str, ProviderConfig] = {}
    for name, settings in provider_settings.items():
        if not isinstance(settings, dict):
            continue
        api_key = _resolve_env(settings.get("api_key"))
        model = settings.get("model")
        extra = {k: v for k, v in settings.items() if k not in {"api_key", "model"}}
        providers[name] = ProviderConfig(name=name, api_key=api_key, model=model, extra=extra or None)

    if default_provider not in providers:
        providers.setdefault(default_provider, ProviderConfig(name=default_provider))

    return AIConfig(default_provider=default_provider, providers=providers)


def get_provider(name: str, config: AIConfig) -> AIProvider:
    provider_cls = PROVIDERS.get(name)
    if not provider_cls:
        known = ", ".join(PROVIDERS.keys()) or "none"
        raise GenerationConfigError(f"Unknown provider '{name}'. Known providers: {known}")

    provider_config = config.providers.get(name)
    if not provider_config:
        provider_config = ProviderConfig(name=name)
    return provider_cls(provider_config)


def build_context(tanda: Dict, repo_root: Path) -> TestContext:
    app_url = None
    config_file = repo_root / "tanda.json"
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text())
            app_url = data.get("app_url")
        except json.JSONDecodeError:
            pass

    test_files = []
    tests_dir = repo_root / "tests"
    if tests_dir.exists():
        for file in tests_dir.glob("**/*.spec.*"):
            test_files.append(str(file.relative_to(repo_root)))

    coverage = tanda.get("covers", [])
    return TestContext(tanda=tanda, app_url=app_url, existing_tests=test_files, coverage_tags=coverage)
