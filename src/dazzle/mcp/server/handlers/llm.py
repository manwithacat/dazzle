"""MCP handlers for LLM intent inspection.

Read-only operations that expose LLM configuration from the parsed DSL
via the MCP ``llm`` tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..handlers.common import load_project_appspec, wrap_handler_errors


@wrap_handler_errors
def list_intents_handler(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """List all declared LLM intents."""
    appspec = load_project_appspec(project_root)
    intents = [
        {
            "name": i.name,
            "title": i.title,
            "description": i.description,
            "model_ref": i.model_ref,
            "timeout_seconds": i.timeout_seconds,
            "has_retry": i.retry is not None,
            "has_pii_policy": i.pii is not None and i.pii.scan,
        }
        for i in appspec.llm_intents
    ]
    return json.dumps({"intents": intents, "count": len(intents)}, indent=2)


@wrap_handler_errors
def list_models_handler(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """List all declared LLM models."""
    appspec = load_project_appspec(project_root)
    models = [
        {
            "name": m.name,
            "title": m.title,
            "provider": m.provider.value,
            "model_id": m.model_id,
            "tier": m.tier.value,
            "max_tokens": m.max_tokens,
        }
        for m in appspec.llm_models
    ]
    return json.dumps({"models": models, "count": len(models)}, indent=2)


@wrap_handler_errors
def inspect_intent_handler(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """Inspect a single LLM intent in detail."""
    name = (args or {}).get("name")
    if not name:
        return json.dumps({"error": "Missing required parameter: name"})

    appspec = load_project_appspec(project_root)
    intent = appspec.get_llm_intent(name)
    if not intent:
        return json.dumps({"error": f"Intent not found: {name}"})

    # Resolve model for display
    resolved_model = None
    if intent.model_ref:
        model = appspec.get_llm_model(intent.model_ref)
        if model:
            resolved_model = {
                "name": model.name,
                "provider": model.provider.value,
                "model_id": model.model_id,
                "tier": model.tier.value,
                "max_tokens": model.max_tokens,
            }
    elif appspec.llm_config and appspec.llm_config.default_model:
        model = appspec.get_llm_model(appspec.llm_config.default_model)
        if model:
            resolved_model = {
                "name": model.name,
                "provider": model.provider.value,
                "model_id": model.model_id,
                "tier": model.tier.value,
                "max_tokens": model.max_tokens,
                "_source": "default_model",
            }

    detail: dict[str, Any] = {
        "name": intent.name,
        "title": intent.title,
        "description": intent.description,
        "model_ref": intent.model_ref,
        "prompt_template": intent.prompt_template,
        "output_schema": intent.output_schema,
        "timeout_seconds": intent.timeout_seconds,
        "vision": intent.vision,
        "resolved_model": resolved_model,
    }

    if intent.retry:
        detail["retry"] = {
            "max_attempts": intent.retry.max_attempts,
            "backoff": intent.retry.backoff.value,
            "initial_delay_ms": intent.retry.initial_delay_ms,
            "max_delay_ms": intent.retry.max_delay_ms,
        }

    if intent.pii:
        detail["pii"] = {
            "scan": intent.pii.scan,
            "action": intent.pii.action.value,
            "patterns": intent.pii.patterns,
        }

    return json.dumps(detail, indent=2)


@wrap_handler_errors
def get_config_handler(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """Return the LLM configuration block."""
    appspec = load_project_appspec(project_root)
    if not appspec.llm_config:
        return json.dumps({"error": "No llm_config defined in this project"})

    cfg = appspec.llm_config
    result: dict[str, Any] = {
        "default_model": cfg.default_model,
        "default_provider": cfg.default_provider.value if cfg.default_provider else None,
        "budget_alert_usd": str(cfg.budget_alert_usd) if cfg.budget_alert_usd else None,
        "artifact_store": cfg.artifact_store.value,
        "logging": {
            "log_prompts": cfg.logging.log_prompts,
            "log_completions": cfg.logging.log_completions,
            "redact_pii": cfg.logging.redact_pii,
        },
        "rate_limits": cfg.rate_limits,
    }
    return json.dumps(result, indent=2)
