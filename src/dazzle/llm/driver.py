"""LLM driver resolution — how Dazzle reaches a model for cognition.

Dazzle has two ways to call a Claude model:

- ``claude-cli`` — shells out to the Claude Code CLI (``claude -p``),
  billed to the developer's Claude **subscription**. No API key needed;
  the developer signs in once with ``claude``. This is the default for
  new projects (``dazzle init``) so trying Dazzle never requires buying
  API credit. Development-time only.
- ``anthropic-api`` — the metered Anthropic API via ``ANTHROPIC_API_KEY``.
  This is the deployment path: a deployed app's ``llm_intent`` cognition
  must run on an API key, never on a developer subscription.

Resolution order (first match wins):

1. Explicit value (CLI flag such as ``dazzle qa trial --llm-driver``)
2. ``DAZZLE_LLM_DRIVER`` environment variable
3. ``[llm] driver`` in dazzle.toml
4. ``auto``: ``anthropic-api`` if ``ANTHROPIC_API_KEY`` is set, else
   ``claude-cli`` if the CLI is installed, else an error that lays out
   both onboarding paths.

The dev → deploy path is documented in ``docs/reference/llm-drivers.md``;
``dazzle doctor`` reports the resolved driver and what deployment needs.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

DRIVER_CLAUDE_CLI = "claude-cli"
DRIVER_ANTHROPIC_API = "anthropic-api"
DRIVER_AUTO = "auto"

VALID_DRIVERS = (DRIVER_CLAUDE_CLI, DRIVER_ANTHROPIC_API, DRIVER_AUTO)

# Console URL for purchasing API credit — the single place this lives so
# every "ready to deploy" message points at the same frictionless path.
API_KEY_CONSOLE_URL = "https://console.anthropic.com/settings/keys"

PRODUCTION_NEEDS_API_KEY_MSG = (
    "The 'claude-cli' LLM driver bills a developer's Claude subscription and "
    "is for development only — a deployed app must use the Anthropic API.\n"
    "To deploy:\n"
    f"  1. Create an API key: {API_KEY_CONSOLE_URL}\n"
    "  2. Set ANTHROPIC_API_KEY in the deployment environment\n"
    '  3. Set [llm] driver = "anthropic-api" in dazzle.toml (or remove the '
    "[llm] section — 'auto' prefers the API key when set)\n"
    "See docs/reference/llm-drivers.md."
)


class LLMDriverError(RuntimeError):
    """No usable LLM driver could be resolved."""


def claude_cli_available() -> bool:
    """True if the Claude Code CLI is on PATH."""
    return shutil.which("claude") is not None


def resolve_llm_driver(
    explicit: str | None = None,
    manifest_driver: str | None = None,
) -> str:
    """Resolve which LLM driver to use.

    Args:
        explicit: A driver named on the command line (highest priority).
        manifest_driver: The ``[llm] driver`` value from dazzle.toml.

    Returns:
        ``"claude-cli"`` or ``"anthropic-api"`` (never ``"auto"``).

    Raises:
        LLMDriverError: If the requested driver is unknown or unusable,
            or if ``auto`` finds neither an API key nor the CLI.
    """
    requested = explicit or os.environ.get("DAZZLE_LLM_DRIVER") or manifest_driver or DRIVER_AUTO
    requested = requested.strip().lower()

    if requested not in VALID_DRIVERS:
        raise LLMDriverError(
            f"Unknown LLM driver {requested!r}. Valid values: {', '.join(VALID_DRIVERS)}."
        )

    if requested == DRIVER_ANTHROPIC_API:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMDriverError(
                "LLM driver 'anthropic-api' requested but ANTHROPIC_API_KEY is "
                f"not set. Create a key at {API_KEY_CONSOLE_URL} and export it, "
                "or switch to the subscription driver for development: "
                '[llm] driver = "claude-cli" in dazzle.toml '
                "(requires the Claude Code CLI — https://claude.com/claude-code)."
            )
        return DRIVER_ANTHROPIC_API

    if requested == DRIVER_CLAUDE_CLI:
        _refuse_cli_in_production()
        if not claude_cli_available():
            raise LLMDriverError(
                "LLM driver 'claude-cli' requested but the Claude Code CLI is "
                "not on PATH. Install it (https://claude.com/claude-code) and "
                "sign in once with `claude`, or use the metered API instead: "
                f"set ANTHROPIC_API_KEY ({API_KEY_CONSOLE_URL}) and "
                '[llm] driver = "anthropic-api".'
            )
        return DRIVER_CLAUDE_CLI

    # auto
    if os.environ.get("ANTHROPIC_API_KEY"):
        return DRIVER_ANTHROPIC_API
    if claude_cli_available():
        _refuse_cli_in_production()
        return DRIVER_CLAUDE_CLI
    raise LLMDriverError(
        "No LLM driver available. Dazzle needs one of:\n"
        "  - Claude Code CLI (uses your Claude subscription, no API key — "
        "recommended for development): https://claude.com/claude-code, then "
        "sign in once with `claude`\n"
        f"  - Anthropic API key (metered; required for deployment): create one "
        f"at {API_KEY_CONSOLE_URL} and export ANTHROPIC_API_KEY\n"
        "See docs/reference/llm-drivers.md."
    )


def _refuse_cli_in_production() -> None:
    """Raise if subscription-billed cognition is attempted in production.

    This sits on every path to ``claude -p`` — a deployed app must run
    on an API key, never on a developer's personal subscription.
    """
    if os.environ.get("DAZZLE_ENV") == "production":
        raise LLMDriverError(PRODUCTION_NEEDS_API_KEY_MSG)


def call_claude_cli(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    timeout: int = 300,
    max_turns: int = 1,
) -> tuple[str, int]:
    """Run one completion through the Claude Code CLI (subscription-billed).

    Returns ``(response_text, total_tokens)``. Token counts come from the
    CLI's ``--output-format json`` envelope; 0 if unavailable.

    The prompt travels over **stdin**, not argv — flattened agent
    history can exceed the per-argument kernel limit (256 KB on macOS).
    The argument list is exec'd directly (no shell), so prompt and
    system-prompt content cannot split into extra arguments or reach a
    shell interpreter.

    The subprocess environment strips:

    - ``CLAUDECODE`` — so the CLI doesn't refuse to start when invoked
      from inside a Claude Code session, and
    - ``ANTHROPIC_API_KEY`` — so the CLI bills the subscription, never
      silently falls through to the metered API key. That billing
      guarantee is the entire point of this driver.
    """
    _refuse_cli_in_production()
    cmd = ["claude", "--print", "--output-format", "json", "--max-turns", str(max_turns)]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    if model:
        cmd.extend(["--model", model])

    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}
    logger.debug("Calling Claude Code CLI (subscription) model=%s", model or "default")
    try:
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        raise LLMDriverError(f"Claude Code CLI timed out after {timeout} seconds")

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise LLMDriverError(
            f"Claude Code CLI failed (exit {result.returncode}): {stderr[:500]}\n"
            "Is the CLI signed in? Run `claude` interactively once to authenticate."
        )

    return _parse_cli_json_output(result.stdout)


def _parse_cli_json_output(stdout: str) -> tuple[str, int]:
    """Extract (text, tokens) from ``claude --output-format json`` output.

    Non-JSON stdout falls back to plain text (an older CLI ignoring
    ``--output-format`` still yields a usable response). But stdout that
    *is* JSON with an unexpected shape raises loudly — silently handing
    a structured envelope to callers as "response text" produces
    confusing failures far from the cause.
    """
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), 0

    if isinstance(envelope, dict):
        text = envelope.get("result")
        if isinstance(text, str):
            usage = envelope.get("usage") or {}
            tokens = 0
            if isinstance(usage, dict):
                tokens = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
            return text.strip(), tokens

    raise LLMDriverError(
        "Claude Code CLI returned JSON in an unexpected shape (no string "
        f"'result' field): {stdout[:200]!r}. This usually means a CLI "
        "version drift — check `claude --version`."
    )
