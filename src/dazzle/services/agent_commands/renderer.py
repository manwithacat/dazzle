"""Maturity gate evaluator, template renderer, and project sync for agent commands.

Post-#1049 (v0.67.87+): the 9 markdown templates are rendered via
inline Python composition in `template_strings.py` rather than Jinja2.
The migration drops one of the last `jinja2` users blocking #1042.
"""

import configparser
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.ir.identity import spec_display_id
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

from .loader import load_all_commands
from .models import CommandDefinition, CommandStatus, MaturityGate, SyncManifest
from .template_strings import (
    AGENTS_SYNC_BEGIN,
    AGENTS_SYNC_END,
)
from .template_strings import (
    render_agents_md as _render_agents_md_impl,
)
from .template_strings import (
    render_agents_sync_block as _render_agents_sync_block_impl,
)
from .template_strings import (
    render_claude_md_section as _render_claude_md_section_impl,
)
from .template_strings import (
    render_command_shim as _render_command_shim_impl,
)
from .template_strings import (
    render_skill as _render_skill_impl,
)
from .template_strings import (
    render_skill_document as _render_skill_document_impl,
)

logger = logging.getLogger(__name__)


def evaluate_maturity(gate: MaturityGate, ctx: dict[str, Any]) -> tuple[bool, str | None]:
    """Check whether a project meets a command's maturity prerequisites.

    Returns (available, reason). reason is None when available is True.
    """
    if gate.min_entities > 0 and ctx.get("entity_count", 0) < gate.min_entities:
        return False, (
            f"Requires {gate.min_entities}+ entities (project has {ctx.get('entity_count', 0)})"
        )

    if gate.min_surfaces > 0 and ctx.get("surface_count", 0) < gate.min_surfaces:
        return False, (
            f"Requires {gate.min_surfaces}+ surfaces (project has {ctx.get('surface_count', 0)})"
        )

    if gate.min_stories > 0 and ctx.get("story_count", 0) < gate.min_stories:
        return False, (
            f"Requires {gate.min_stories}+ stories (project has {ctx.get('story_count', 0)})"
        )

    if gate.requires_spec_md and not ctx.get("has_spec_md", False):
        return False, "Requires SPEC.md in project root"

    if gate.requires_github_remote and not ctx.get("has_github_remote", False):
        return False, "Requires a GitHub remote configured"

    if gate.requires_running_app and not ctx.get("app_running", False):
        return False, "Requires a running app (dazzle serve)"

    if "validate" in gate.requires and not ctx.get("validate_passes", False):
        return False, "Requires dazzle validate to pass"

    return True, None


_APP_HEALTH_PORTS: tuple[int, ...] = (3000, 8000)


def _probe_running_app(project_root: Path) -> bool:
    """Detect a locally-running Dazzle app (#788).

    Checks, in order:
      1. ``.dazzle/runtime.json`` or ``.dazzle/*.lock`` marker files in
         the project (written by ``dazzle serve``).
      2. TCP socket probes against common local ports. We only care
         whether something is listening — not what it serves — so a
         successful ``connect()`` is enough.

    Returns ``True`` as soon as any probe succeeds. Socket failures are
    swallowed — ``False`` just means "no running app detected," not
    "the probe crashed."
    """
    dazzle_dir = project_root / ".dazzle"
    if dazzle_dir.is_dir():
        if (dazzle_dir / "runtime.json").is_file():
            return True
        for lock in dazzle_dir.glob("*.lock"):
            if lock.is_file():
                return True

    import socket

    for port in _APP_HEALTH_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            continue
    return False


def _has_github_remote(git_config_path: Path) -> bool:
    """Return True if any remote in ``.git/config`` points at github.com.

    Parses the file with ``configparser`` and inspects each remote's
    ``url`` value via ``urlparse``, comparing the hostname exactly
    (``github.com`` or any ``*.github.com`` subdomain). This avoids the
    substring-containment bypass that the previous naive check was
    vulnerable to — an adversarial ``.git/config`` with a URL like
    ``https://evil.example/?github.com`` would have matched before.
    """
    if not git_config_path.is_file():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read(str(git_config_path), encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return False
    for section in parser.sections():
        if not section.startswith("remote "):
            continue
        url = parser.get(section, "url", fallback=None)
        if not url:
            continue
        # Git supports both `https://github.com/...` and scp-like
        # `git@github.com:owner/repo.git` URLs. Normalise both.
        host: str | None = None
        if "://" in url:
            host = urlparse(url).hostname
        elif "@" in url and ":" in url.split("@", 1)[1]:
            host = url.split("@", 1)[1].split(":", 1)[0]
        if host and (host == "github.com" or host.endswith(".github.com")):
            return True
    return False


def build_project_context(project_root: Path) -> dict[str, Any]:
    """Introspect a Dazzle project directory and return context for rendering."""
    ctx: dict[str, Any] = {
        "entity_count": 0,
        "surface_count": 0,
        "story_count": 0,
        "has_spec_md": False,
        "has_github_remote": False,
        "validate_passes": True,
        "app_running": False,
        "entity_names": [],
        "persona_names": [],
        "surface_names": [],
        "project_name": project_root.name,
    }

    # Check for SPEC.md
    ctx["has_spec_md"] = (project_root / "SPEC.md").exists() or (project_root / "spec.md").exists()

    # Check for a GitHub remote by parsing `.git/config` as an INI file
    # and inspecting the hostname of each remote's `url = ...` entry.
    # Previously used a naive `"github.com" in content` substring check
    # (CodeQL py/incomplete-url-substring-sanitization, alert #62) —
    # low-risk (the flag is informational only) but worth doing right.
    ctx["has_github_remote"] = _has_github_remote(project_root / ".git" / "config")

    # Probe for a running app — populates requires_running_app gates (#788)
    ctx["app_running"] = _probe_running_app(project_root)

    # Try to parse AppSpec for counts
    try:
        manifest_path = project_root / "dazzle.toml"
        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
            dsl_files = discover_dsl_files(project_root, manifest)
            if dsl_files:
                modules = parse_modules(dsl_files)
                appspec = build_appspec(modules, manifest.project_root)

                ctx["entity_count"] = len(appspec.domain.entities)
                ctx["surface_count"] = len(appspec.surfaces)
                ctx["story_count"] = len(appspec.stories)
                ctx["entity_names"] = [e.name for e in appspec.domain.entities]
                ctx["surface_names"] = [s.name for s in appspec.surfaces]
                ctx["persona_names"] = [spec_display_id(p) for p in appspec.personas]
    except Exception:
        ctx["validate_passes"] = False

    return ctx


def render_skill(cmd: CommandDefinition, ctx: dict[str, Any]) -> str:
    """Render a command's markdown template via the Python port."""
    return _render_skill_impl(cmd, ctx)


def render_agents_md(
    commands: list[tuple[CommandDefinition, bool, str | None]], ctx: dict[str, Any]
) -> str:
    """Render canonical AGENTS.md from all commands via the Python port."""
    return _render_agents_md_impl(commands, ctx)


def render_claude_md_section(
    commands: list[tuple[CommandDefinition, bool, str | None]], ctx: dict[str, Any]
) -> str:
    """Render the managed section of the thin CLAUDE.md adapter."""
    return _render_claude_md_section_impl(commands, ctx)


_DAZZLE_AGENT_MARKER = "<!-- dazzle-agent-commands -->"
_CLAUDE_ADAPTER_INTRO = (
    "@../AGENTS.md\n"
    "\n"
    "# CLAUDE.md — adapter\n"
    "\n"
    "Canonical project policy is AGENTS.md (imported above). This file carries\n"
    "only Claude-Code-runtime specifics; project facts belong in AGENTS.md.\n"
)


def _write_agents_md(
    agents_path: Path,
    evaluated: list[tuple[CommandDefinition, bool, str | None]],
    ctx: dict[str, Any],
) -> None:
    """Write or refresh AGENTS.md without clobbering non-generated policy."""
    block = _render_agents_sync_block_impl(evaluated, ctx)
    if not agents_path.exists():
        agents_path.write_text(render_agents_md(evaluated, ctx), encoding="utf-8")
        return

    existing = agents_path.read_text(encoding="utf-8")
    if AGENTS_SYNC_BEGIN in existing and AGENTS_SYNC_END in existing:
        pattern = re.compile(
            re.escape(AGENTS_SYNC_BEGIN) + r".*?" + re.escape(AGENTS_SYNC_END),
            re.DOTALL,
        )
        updated = pattern.sub(block.rstrip("\n"), existing, count=1)
        agents_path.write_text(
            updated if updated.endswith("\n") else updated + "\n", encoding="utf-8"
        )
        return

    agents_path.write_text(existing.rstrip() + "\n\n" + block + "\n", encoding="utf-8")


def _write_claude_md_adapter(claude_md_path: Path, section: str) -> None:
    """Ensure `.claude/CLAUDE.md` is a thin adapter that imports AGENTS.md.

    Preserves any pre-existing user content above the dazzle-managed marker,
    but always keeps `@../AGENTS.md` as the first content line and refreshes
    the managed section on every sync.
    """
    marker = _DAZZLE_AGENT_MARKER
    claude_md_path.parent.mkdir(parents=True, exist_ok=True)

    if not claude_md_path.exists():
        claude_md_path.write_text(
            _CLAUDE_ADAPTER_INTRO + "\n" + marker + "\n" + section,
            encoding="utf-8",
        )
        return

    existing = claude_md_path.read_text(encoding="utf-8")
    if marker in existing:
        before = existing.split(marker, 1)[0]
    else:
        before = existing

    # Keep user content, but guarantee the AGENTS.md import is first.
    lines = before.splitlines()
    content_idx = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if content_idx is None:
        before = _CLAUDE_ADAPTER_INTRO
    else:
        first = lines[content_idx].strip()
        if not re.fullmatch(r"@(\.\./)?AGENTS\.md", first):
            remainder = "\n".join(lines).lstrip()
            before = _CLAUDE_ADAPTER_INTRO + "\n" + remainder
        else:
            # Normalise to @../AGENTS.md (same form as the in-repo adapter).
            lines[content_idx] = "@../AGENTS.md"
            before = "\n".join(lines)

    claude_md_path.write_text(
        before.rstrip() + "\n\n" + marker + "\n" + section,
        encoding="utf-8",
    )


def sync_to_project(project_root: Path) -> SyncManifest:
    """Sync agent commands to a Dazzle project directory.

    Layout (harness-neutral, mirrors the framework repo):

    1. Build project context and evaluate maturity gates
    2. Write portable skill bodies to ``.agents/skills/<name>/SKILL.md``
    3. Write discovery shims to ``.claude/commands/<name>.md``
    4. Seed ``agent/`` backlog/log files for loop commands
    5. Write canonical ``AGENTS.md`` (workflows index + command catalogue)
    6. Ensure thin ``.claude/CLAUDE.md`` adapter importing AGENTS.md
    7. Write ``.claude/commands/.manifest.json``
    """
    from dazzle import __version__ as dazzle_version

    ctx = build_project_context(project_root)
    all_commands = load_all_commands()

    # Evaluate maturity for each command
    evaluated: list[tuple[CommandDefinition, bool, str | None]] = []
    statuses: dict[str, CommandStatus] = {}
    for cmd in all_commands:
        available, reason = evaluate_maturity(cmd.maturity, ctx)
        evaluated.append((cmd, available, reason))
        statuses[cmd.name] = CommandStatus(version=cmd.version, available=available, reason=reason)

    # Portable skills home + Claude discovery shims
    skills_root = project_root / ".agents" / "skills"
    commands_dir = project_root / ".claude" / "commands"
    skills_root.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)

    for cmd, available, _reason in evaluated:
        if not available:
            continue
        skill_dir = skills_root / cmd.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            _render_skill_document_impl(cmd, ctx),
            encoding="utf-8",
        )
        (commands_dir / f"{cmd.name}.md").write_text(
            _render_command_shim_impl(cmd),
            encoding="utf-8",
        )

    # Seed empty backlog/log files for loop commands (don't overwrite)
    agent_dir = project_root / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    for cmd, _available, _reason in evaluated:
        if cmd.loop is None:
            continue
        for file_attr in ("backlog_file", "log_file"):
            rel_path = getattr(cmd.loop, file_attr, "")
            if not rel_path:
                continue
            full_path = project_root / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if not full_path.exists():
                full_path.write_text(
                    f"# {cmd.title} — {file_attr.replace('_', ' ').title()}\n",
                    encoding="utf-8",
                )

    # Canonical AGENTS.md — preserve blank-template / user policy outside the
    # managed sync block so init-time guidance is not wiped on first sync.
    _write_agents_md(project_root / "AGENTS.md", evaluated, ctx)

    # Thin CLAUDE.md adapter
    section = render_claude_md_section(evaluated, ctx)
    _write_claude_md_adapter(project_root / ".claude" / "CLAUDE.md", section)

    # Manifest next to Claude discovery shims (stable path for tooling)
    synced_at = datetime.now(UTC).isoformat()
    manifest_data = {
        "dazzle_version": dazzle_version,
        "commands_version": "1.0.0",
        "synced_at": synced_at,
        "layout": "agents-skills-v1",
        "commands": {
            name: {
                "version": cs.version,
                "available": cs.available,
                "reason": cs.reason,
            }
            for name, cs in statuses.items()
        },
    }
    manifest_path = commands_dir / ".manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    return SyncManifest(
        dazzle_version=dazzle_version,
        commands_version="1.0.0",
        synced_at=synced_at,
        commands=statuses,
    )
