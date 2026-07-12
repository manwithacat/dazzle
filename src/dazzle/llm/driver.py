"""LLM driver resolution — how Dazzle reaches a model for cognition.

Dazzle separates **who pays** from **which model family**:

Subscription drivers (development only — refused under ``DAZZLE_ENV=production``):

- ``claude-cli`` — Claude Code CLI (``claude --print``), Claude subscription.
- ``grok-cli`` — Grok Build CLI (``grok -p`` / ``--single``), Grok subscription.

Metered API drivers (deploy path):

- ``anthropic-api`` — Anthropic API via ``ANTHROPIC_API_KEY``.

Resolution order (first match wins):

1. Explicit value (CLI flag such as ``dazzle qa trial --llm-driver``)
2. ``DAZZLE_LLM_DRIVER`` environment variable
3. ``[llm] driver`` in dazzle.toml
4. ``auto``: ``anthropic-api`` if ``ANTHROPIC_API_KEY`` is set, else the first
   available subscription CLI (``claude-cli``, then ``grok-cli``), else an error
   that lays out all onboarding paths.

The dev → deploy path is documented in ``docs/reference/llm-drivers.md``;
``dazzle doctor`` reports the resolved driver and what deployment needs.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DRIVER_CLAUDE_CLI = "claude-cli"
DRIVER_GROK_CLI = "grok-cli"
DRIVER_ANTHROPIC_API = "anthropic-api"
DRIVER_AUTO = "auto"

# Subscription-billed CLIs — never production.
SUBSCRIPTION_DRIVERS: frozenset[str] = frozenset({DRIVER_CLAUDE_CLI, DRIVER_GROK_CLI})

# Metered HTTP APIs — required for deployed apps.
API_DRIVERS: frozenset[str] = frozenset({DRIVER_ANTHROPIC_API})

VALID_DRIVERS = (
    DRIVER_CLAUDE_CLI,
    DRIVER_GROK_CLI,
    DRIVER_ANTHROPIC_API,
    DRIVER_AUTO,
)

# Console URL for purchasing Anthropic API credit.
API_KEY_CONSOLE_URL = "https://console.anthropic.com/settings/keys"

# Preferred order when auto-picking a subscription CLI (first available wins).
_SUBSCRIPTION_CLI_PREFERENCE: tuple[str, ...] = (DRIVER_CLAUDE_CLI, DRIVER_GROK_CLI)

PRODUCTION_NEEDS_API_KEY_MSG = (
    "Subscription LLM drivers (claude-cli, grok-cli) bill a developer's "
    "personal subscription and are for development only — a deployed app "
    "must use a metered API key.\n"
    "To deploy:\n"
    f"  1. Create an Anthropic API key: {API_KEY_CONSOLE_URL}\n"
    "  2. Set ANTHROPIC_API_KEY in the deployment environment\n"
    '  3. Set [llm] driver = "anthropic-api" in dazzle.toml (or remove the '
    "[llm] section — 'auto' prefers the API key when set)\n"
    "See docs/reference/llm-drivers.md."
)


class LLMDriverError(RuntimeError):
    """No usable LLM driver could be resolved."""


def is_subscription_driver(driver: str) -> bool:
    """True if *driver* bills a personal subscription CLI (dev-only)."""
    return driver in SUBSCRIPTION_DRIVERS


def claude_cli_available() -> bool:
    """True if the Claude Code CLI is on PATH."""
    return shutil.which("claude") is not None


def grok_cli_available() -> bool:
    """True if the Grok Build CLI is on PATH."""
    return shutil.which("grok") is not None


def subscription_cli_available(driver: str) -> bool:
    """True if the given subscription driver has its CLI on PATH."""
    if driver == DRIVER_CLAUDE_CLI:
        return claude_cli_available()
    if driver == DRIVER_GROK_CLI:
        return grok_cli_available()
    return False


def pick_available_subscription_driver() -> str | None:
    """Return the first available subscription CLI driver, or None."""
    for driver in _SUBSCRIPTION_CLI_PREFERENCE:
        if subscription_cli_available(driver):
            return driver
    return None


def resolve_llm_driver(
    explicit: str | None = None,
    manifest_driver: str | None = None,
) -> str:
    """Resolve which LLM driver to use.

    Args:
        explicit: A driver named on the command line (highest priority).
        manifest_driver: The ``[llm] driver`` value from dazzle.toml.

    Returns:
        A concrete driver id (never ``"auto"``): ``claude-cli``, ``grok-cli``,
        or ``anthropic-api``.

    Raises:
        LLMDriverError: If the requested driver is unknown or unusable,
            or if ``auto`` finds neither an API key nor a subscription CLI.
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
                "or switch to a subscription driver for development: "
                '[llm] driver = "claude-cli" or "grok-cli" in dazzle.toml '
                "(requires the matching CLI on PATH)."
            )
        return DRIVER_ANTHROPIC_API

    if requested in SUBSCRIPTION_DRIVERS:
        _refuse_subscription_in_production()
        if not subscription_cli_available(requested):
            raise LLMDriverError(_subscription_missing_cli_msg(requested))
        return requested

    # auto
    if os.environ.get("ANTHROPIC_API_KEY"):
        return DRIVER_ANTHROPIC_API
    picked = pick_available_subscription_driver()
    if picked is not None:
        _refuse_subscription_in_production()
        return picked
    raise LLMDriverError(
        "No LLM driver available. Dazzle needs one of:\n"
        "  - Claude Code CLI (Claude subscription, no API key): "
        "https://claude.com/claude-code — then sign in once with `claude`\n"
        "  - Grok Build CLI (Grok subscription, no API key): install `grok` "
        "and sign in with `grok login`\n"
        f"  - Anthropic API key (metered; required for deployment): "
        f"{API_KEY_CONSOLE_URL} → export ANTHROPIC_API_KEY\n"
        'Set [llm] driver = "claude-cli" | "grok-cli" | "anthropic-api" | '
        '"auto" in dazzle.toml. See docs/reference/llm-drivers.md.'
    )


def _subscription_missing_cli_msg(driver: str) -> str:
    if driver == DRIVER_CLAUDE_CLI:
        return (
            "LLM driver 'claude-cli' requested but the Claude Code CLI is "
            "not on PATH. Install it (https://claude.com/claude-code) and "
            "sign in once with `claude`, or use another driver: "
            '[llm] driver = "grok-cli" (Grok Build CLI) or "anthropic-api" '
            f"(set ANTHROPIC_API_KEY — {API_KEY_CONSOLE_URL})."
        )
    if driver == DRIVER_GROK_CLI:
        return (
            "LLM driver 'grok-cli' requested but the Grok Build CLI is "
            "not on PATH. Install the `grok` CLI and sign in with "
            "`grok login`, or use another driver: "
            '[llm] driver = "claude-cli" or "anthropic-api" '
            f"(set ANTHROPIC_API_KEY — {API_KEY_CONSOLE_URL})."
        )
    return f"LLM driver {driver!r} is not available."


def _refuse_subscription_in_production() -> None:
    """Raise if subscription-billed cognition is attempted in production.

    This sits on every path to a personal CLI — a deployed app must run
    on an API key, never on a developer's personal subscription.
    """
    if os.environ.get("DAZZLE_ENV") == "production":
        raise LLMDriverError(PRODUCTION_NEEDS_API_KEY_MSG)


def call_subscription_cli(
    driver: str,
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    timeout: int = 300,
    max_turns: int = 4,
) -> tuple[str, int]:
    """Run one completion through a subscription CLI driver.

    Dispatches to :func:`call_claude_cli` or :func:`call_grok_cli`.
    Returns ``(response_text, total_tokens)``.
    """
    if driver == DRIVER_CLAUDE_CLI:
        return call_claude_cli(
            prompt,
            system_prompt=system_prompt,
            model=model,
            timeout=timeout,
            max_turns=max_turns,
        )
    if driver == DRIVER_GROK_CLI:
        return call_grok_cli(
            prompt,
            system_prompt=system_prompt,
            model=model,
            timeout=timeout,
            max_turns=max_turns,
        )
    raise LLMDriverError(
        f"call_subscription_cli: {driver!r} is not a subscription CLI driver "
        f"(expected one of {sorted(SUBSCRIPTION_DRIVERS)})."
    )


def call_claude_cli(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    timeout: int = 300,
    max_turns: int = 4,
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
    _refuse_subscription_in_production()
    # This is a pure text completion: a model that can see any tools
    # (built-ins OR MCP servers from the cwd's .mcp.json) will eventually
    # emit a tool_use turn instead of text — which then dies as
    # error_max_turns (observed on trial step 4 of the first live run).
    # Three layers: --tools "" drops the built-ins; --strict-mcp-config
    # with no --mcp-config loads zero MCP servers; --disallowedTools "*"
    # denies anything that still slips through (e.g. LSP, which sits
    # outside the --tools set), and the max_turns default leaves room to
    # recover from a denied attempt with a text reply.
    cmd = [
        "claude",
        "--print",
        "--output-format",
        "json",
        "--tools",
        "",
        "--strict-mcp-config",
        "--disallowedTools",
        "*",
        "--max-turns",
        str(max_turns),
    ]
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
        raise LLMDriverError(f"Claude Code CLI timed out after {timeout} seconds") from None

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise LLMDriverError(
            f"Claude Code CLI failed (exit {result.returncode}): {stderr[:500]}\n"
            "Is the CLI signed in? Run `claude` interactively once to authenticate."
        )

    return _parse_cli_json_output(result.stdout, cli_label="Claude Code CLI")


def call_grok_cli(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    timeout: int = 300,
    max_turns: int = 4,
) -> tuple[str, int]:
    """Run one completion through the Grok Build CLI (subscription-billed).

    Uses ``grok -p`` / headless single-turn mode with ``--output-format json``.
    Scaffold mirrors :func:`call_claude_cli` billing guarantees: strip metered
    API keys from the subprocess environment so the CLI bills the Grok
    subscription.

    Long prompts are written to a temp file and passed via ``--prompt-file``
    to avoid argv size limits.
    """
    _refuse_subscription_in_production()
    if not grok_cli_available():
        raise LLMDriverError(_subscription_missing_cli_msg(DRIVER_GROK_CLI))

    # Prefer prompt-file for any non-trivial body (agent history, trials).
    use_file = len(prompt) > 2000 or "\n" in prompt
    prompt_path: Path | None = None
    try:
        cmd = [
            "grok",
            "--output-format",
            "json",
            "--max-turns",
            str(max_turns),
            "--no-subagents",
            "--no-plan",
            "--disable-web-search",
            # Deny tools so this stays a pure text completion (same contract
            # as claude-cli --disallowedTools "*").
            "--disallowed-tools",
            "*",
        ]
        if system_prompt:
            cmd.extend(["--system-prompt-override", system_prompt])
        if model:
            cmd.extend(["--model", model])

        if use_file:
            fd, name = tempfile.mkstemp(prefix="dazzle-grok-prompt-", suffix=".txt")
            prompt_path = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(prompt)
            cmd.extend(["--prompt-file", str(prompt_path)])
        else:
            cmd.extend(["--single", prompt])

        # Strip metered keys so Grok subscription is billed, not API.
        strip_keys = {
            "ANTHROPIC_API_KEY",
            "XAI_API_KEY",
            "GROK_API_KEY",
            "OPENAI_API_KEY",
        }
        env = {k: v for k, v in os.environ.items() if k not in strip_keys}
        logger.debug("Calling Grok Build CLI (subscription) model=%s", model or "default")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            raise LLMDriverError(f"Grok Build CLI timed out after {timeout} seconds") from None

        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise LLMDriverError(
                f"Grok Build CLI failed (exit {result.returncode}): {stderr[:500]}\n"
                "Is the CLI signed in? Run `grok login` once to authenticate."
            )

        return _parse_cli_json_output(result.stdout, cli_label="Grok Build CLI")
    finally:
        if prompt_path is not None:
            try:
                prompt_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("could not remove grok prompt temp file", exc_info=True)


def _parse_cli_json_output(stdout: str, *, cli_label: str = "CLI") -> tuple[str, int]:
    """Extract (text, tokens) from a headless CLI ``--output-format json`` body.

    Supports Claude-shaped ``{"result": "...", "usage": {...}}`` and a few
    Grok-shaped alternatives (``response`` / ``text`` / ``content`` / nested
    ``message``). Non-JSON stdout falls back to plain text.
    """
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), 0

    if isinstance(envelope, dict):
        text = _extract_text_from_envelope(envelope)
        if isinstance(text, str):
            tokens = _extract_tokens_from_envelope(envelope)
            return text.strip(), tokens

    raise LLMDriverError(
        f"{cli_label} returned JSON in an unexpected shape (no string "
        f"response field): {stdout[:200]!r}. This usually means a CLI "
        "version drift — check `claude --version` / `grok --version`."
    )


def _extract_text_from_envelope(envelope: dict) -> str | None:
    for key in ("result", "response", "text", "content", "output"):
        val = envelope.get(key)
        if isinstance(val, str):
            return val
    msg = envelope.get("message")
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            if parts:
                return "".join(parts)
    return None


def _extract_tokens_from_envelope(envelope: dict) -> int:
    usage = envelope.get("usage") or {}
    if not isinstance(usage, dict):
        return 0
    total = usage.get("total_tokens")
    if total is not None:
        try:
            return int(total)
        except (TypeError, ValueError):
            pass
    try:
        return int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        return 0
