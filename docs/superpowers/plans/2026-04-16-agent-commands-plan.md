# Agent-First Development Commands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship six autonomous agent commands (`/improve`, `/qa`, `/spec-sync`, `/ship`, `/polish`, `/issues`) that Dazzle's frontier users can deploy to their projects via `dazzle agent sync`.

**Architecture:** TOML command definitions + Jinja2 skill templates in the Dazzle package → MCP `agent_commands` tool (read-only: list/get/check_updates) → `dazzle agent sync` CLI writes `.claude/commands/*.md` + `AGENTS.md` + `agent/` backlogs into the user's project.

**Tech Stack:** Python 3.12, tomllib (stdlib), Jinja2, Typer (CLI), MCP handler pattern, Pydantic-free dataclasses.

---

## File Structure

### New files (in `src/dazzle/`)

| File | Responsibility |
|------|---------------|
| `cli/agent_commands/__init__.py` | `dazzle agent` Typer subgroup + `sync` command |
| `cli/agent_commands/models.py` | `CommandDefinition`, `MaturityGate`, `LoopConfig`, `ToolsConfig`, `CommandStatus`, `SyncManifest` dataclasses |
| `cli/agent_commands/loader.py` | Parse TOML → `CommandDefinition` objects |
| `cli/agent_commands/renderer.py` | Evaluate maturity gates, render Jinja2 templates, write project files |
| `cli/agent_commands/definitions/improve.toml` | `/improve` command metadata |
| `cli/agent_commands/definitions/qa.toml` | `/qa` command metadata |
| `cli/agent_commands/definitions/spec_sync.toml` | `/spec-sync` command metadata |
| `cli/agent_commands/definitions/ship.toml` | `/ship` command metadata |
| `cli/agent_commands/definitions/polish.toml` | `/polish` command metadata |
| `cli/agent_commands/definitions/issues.toml` | `/issues` command metadata |
| `cli/agent_commands/templates/improve.md.j2` | `/improve` Claude Code skill |
| `cli/agent_commands/templates/qa.md.j2` | `/qa` Claude Code skill |
| `cli/agent_commands/templates/spec_sync.md.j2` | `/spec-sync` Claude Code skill |
| `cli/agent_commands/templates/ship.md.j2` | `/ship` Claude Code skill |
| `cli/agent_commands/templates/polish.md.j2` | `/polish` Claude Code skill |
| `cli/agent_commands/templates/issues.md.j2` | `/issues` Claude Code skill |
| `cli/agent_commands/templates/agents_md.j2` | `AGENTS.md` template |
| `cli/agent_commands/templates/claude_md_section.j2` | Section appended to `.claude/CLAUDE.md` |
| `mcp/server/handlers/agent_commands.py` | MCP handler: list, get, check_updates |

### New test files

| File | Tests |
|------|-------|
| `tests/unit/test_agent_command_models.py` | Dataclass construction, TOML parsing, maturity gate evaluation |
| `tests/unit/test_agent_commands_handler.py` | MCP handler operations |
| `tests/unit/test_agent_sync.py` | CLI sync file output |

### Modified files

| File | Change |
|------|--------|
| `src/dazzle/cli/__init__.py:~267` | Add `app.add_typer(agent_app, name="agent")` |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add `agent_commands` tool definition |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Add `agent_commands` handler registration |
| `src/dazzle/mcp/server/handlers/bootstrap.py` | Add agent command nudge to mission briefing |

---

### Task 1: Data Models

**Files:**
- Create: `src/dazzle/cli/agent_commands/models.py`
- Test: `tests/unit/test_agent_command_models.py`

- [ ] **Step 1: Write failing tests for dataclass construction**

```python
# tests/unit/test_agent_command_models.py
"""Tests for agent command data models."""

from dazzle.cli.agent_commands.models import (
    CommandDefinition,
    CommandStatus,
    LoopConfig,
    MaturityGate,
    SyncManifest,
    ToolsConfig,
)


def test_maturity_gate_defaults():
    gate = MaturityGate()
    assert gate.min_entities == 0
    assert gate.min_surfaces == 0
    assert gate.min_stories == 0
    assert gate.requires_running_app is False
    assert gate.requires_github_remote is False
    assert gate.requires_spec_md is False
    assert gate.requires == []


def test_loop_config_fields():
    lc = LoopConfig(
        backlog_file="agent/test-backlog.md",
        log_file="agent/test-log.md",
        lock_file=".dazzle/test.lock",
        max_cycles=20,
        stale_lock_minutes=15,
    )
    assert lc.backlog_file == "agent/test-backlog.md"
    assert lc.max_cycles == 20


def test_command_definition_full():
    cmd = CommandDefinition(
        name="improve",
        version="1.0.0",
        title="Autonomous Improvement Loop",
        description="Discovers quality gaps.",
        pattern="loop",
        maturity=MaturityGate(min_entities=1),
        loop=LoopConfig(backlog_file="agent/improve-backlog.md", log_file="agent/improve-log.md"),
        tools=ToolsConfig(mcp=["dsl.lint"], cli=["dazzle validate"]),
        template_file="improve.md.j2",
    )
    assert cmd.name == "improve"
    assert cmd.pattern == "loop"
    assert cmd.maturity.min_entities == 1
    assert cmd.loop is not None
    assert cmd.loop.backlog_file == "agent/improve-backlog.md"


def test_command_definition_one_shot():
    cmd = CommandDefinition(
        name="ship",
        version="1.0.0",
        title="Ship",
        description="Validate and push.",
        pattern="one-shot",
        template_file="ship.md.j2",
    )
    assert cmd.loop is None
    assert cmd.pattern == "one-shot"


def test_sync_manifest():
    manifest = SyncManifest(
        dazzle_version="0.56.0",
        commands_version="1.0.0",
        synced_at="2026-04-16T14:30:00Z",
        commands={
            "improve": CommandStatus(version="1.0.0", available=True),
            "polish": CommandStatus(version="1.0.0", available=False, reason="Requires 3+ surfaces"),
        },
    )
    assert manifest.commands["improve"].available is True
    assert manifest.commands["polish"].reason == "Requires 3+ surfaces"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_command_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.cli.agent_commands'`

- [ ] **Step 3: Create the package and models**

```python
# src/dazzle/cli/agent_commands/__init__.py
"""Agent-first development commands for Dazzle projects."""
```

```python
# src/dazzle/cli/agent_commands/models.py
"""Data models for agent command definitions."""

from dataclasses import dataclass, field


@dataclass
class MaturityGate:
    """Prerequisites a project must meet for a command to be available."""

    min_entities: int = 0
    min_surfaces: int = 0
    min_stories: int = 0
    requires_running_app: bool = False
    requires_github_remote: bool = False
    requires_spec_md: bool = False
    requires: list[str] = field(default_factory=list)


@dataclass
class LoopConfig:
    """Configuration for loop-pattern commands."""

    backlog_file: str = ""
    log_file: str = ""
    lock_file: str = ""
    max_cycles: int = 50
    stale_lock_minutes: int = 30


@dataclass
class ToolsConfig:
    """MCP tools and CLI commands a command uses."""

    mcp: list[str] = field(default_factory=list)
    cli: list[str] = field(default_factory=list)


@dataclass
class CommandDefinition:
    """A canonical agent command definition parsed from TOML."""

    name: str
    version: str
    title: str
    description: str
    pattern: str  # "loop" | "one-shot"
    maturity: MaturityGate = field(default_factory=MaturityGate)
    loop: LoopConfig | None = None
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    template_file: str = ""


@dataclass
class CommandStatus:
    """Status of a single command in the sync manifest."""

    version: str
    available: bool
    reason: str | None = None


@dataclass
class SyncManifest:
    """Tracks what has been synced to the project."""

    dazzle_version: str
    commands_version: str
    synced_at: str
    commands: dict[str, CommandStatus] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_command_models.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/agent_commands/__init__.py src/dazzle/cli/agent_commands/models.py tests/unit/test_agent_command_models.py
git commit -m "feat(agent-commands): add data models for command definitions"
```

---

### Task 2: TOML Loader

**Files:**
- Create: `src/dazzle/cli/agent_commands/loader.py`
- Create: `src/dazzle/cli/agent_commands/definitions/improve.toml` (first definition, for testing)
- Test: `tests/unit/test_agent_command_models.py` (extend)

- [ ] **Step 1: Write failing tests for TOML loading**

Append to `tests/unit/test_agent_command_models.py`:

```python
from pathlib import Path

from dazzle.cli.agent_commands.loader import load_command, load_all_commands, DEFINITIONS_DIR


def test_load_command_from_toml(tmp_path):
    toml_content = """\
[command]
name = "test_cmd"
version = "1.0.0"
title = "Test Command"
description = "A test command."
pattern = "loop"

[maturity]
min_entities = 2

[loop]
backlog_file = "agent/test-backlog.md"
log_file = "agent/test-log.md"
lock_file = ".dazzle/test.lock"
max_cycles = 10
stale_lock_minutes = 15

[tools]
mcp = ["dsl.lint", "dsl.validate"]
cli = ["dazzle validate"]

[skill_template]
file = "test.md.j2"
"""
    toml_file = tmp_path / "test_cmd.toml"
    toml_file.write_text(toml_content)
    cmd = load_command(toml_file)
    assert cmd.name == "test_cmd"
    assert cmd.version == "1.0.0"
    assert cmd.pattern == "loop"
    assert cmd.maturity.min_entities == 2
    assert cmd.loop is not None
    assert cmd.loop.max_cycles == 10
    assert cmd.tools.mcp == ["dsl.lint", "dsl.validate"]
    assert cmd.template_file == "test.md.j2"


def test_load_command_one_shot_no_loop(tmp_path):
    toml_content = """\
[command]
name = "ship"
version = "1.0.0"
title = "Ship"
description = "Push."
pattern = "one-shot"

[skill_template]
file = "ship.md.j2"
"""
    toml_file = tmp_path / "ship.toml"
    toml_file.write_text(toml_content)
    cmd = load_command(toml_file)
    assert cmd.pattern == "one-shot"
    assert cmd.loop is None


def test_definitions_dir_exists():
    assert DEFINITIONS_DIR.is_dir()


def test_load_all_commands_finds_definitions():
    commands = load_all_commands()
    assert len(commands) >= 1  # At least improve.toml exists
    names = [c.name for c in commands]
    assert "improve" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_command_models.py::test_load_command_from_toml -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.cli.agent_commands.loader'`

- [ ] **Step 3: Create the loader and first TOML definition**

```python
# src/dazzle/cli/agent_commands/loader.py
"""Load agent command definitions from TOML files."""

import tomllib
from pathlib import Path

from .models import CommandDefinition, LoopConfig, MaturityGate, ToolsConfig

DEFINITIONS_DIR = Path(__file__).parent / "definitions"


def load_command(path: Path) -> CommandDefinition:
    """Parse a single TOML file into a CommandDefinition."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    cmd = data.get("command", {})
    mat = data.get("maturity", {})
    loop_data = data.get("loop", None)
    tools_data = data.get("tools", {})
    tmpl = data.get("skill_template", {})

    maturity = MaturityGate(
        min_entities=mat.get("min_entities", 0),
        min_surfaces=mat.get("min_surfaces", 0),
        min_stories=mat.get("min_stories", 0),
        requires_running_app=mat.get("requires_running_app", False),
        requires_github_remote=mat.get("requires_github_remote", False),
        requires_spec_md=mat.get("requires_spec_md", False),
        requires=mat.get("requires", []),
    )

    loop = None
    if loop_data is not None:
        loop = LoopConfig(
            backlog_file=loop_data.get("backlog_file", ""),
            log_file=loop_data.get("log_file", ""),
            lock_file=loop_data.get("lock_file", ""),
            max_cycles=loop_data.get("max_cycles", 50),
            stale_lock_minutes=loop_data.get("stale_lock_minutes", 30),
        )

    tools = ToolsConfig(
        mcp=tools_data.get("mcp", []),
        cli=tools_data.get("cli", []),
    )

    return CommandDefinition(
        name=cmd.get("name", path.stem),
        version=cmd.get("version", "0.0.0"),
        title=cmd.get("title", ""),
        description=cmd.get("description", ""),
        pattern=cmd.get("pattern", "one-shot"),
        maturity=maturity,
        loop=loop,
        tools=tools,
        template_file=tmpl.get("file", ""),
    )


def load_all_commands() -> list[CommandDefinition]:
    """Load all command definitions from the definitions directory."""
    commands = []
    for path in sorted(DEFINITIONS_DIR.glob("*.toml")):
        commands.append(load_command(path))
    return commands
```

```toml
# src/dazzle/cli/agent_commands/definitions/improve.toml
[command]
name = "improve"
version = "1.0.0"
title = "Autonomous Improvement Loop"
description = "Discovers quality gaps in the project (DSL lint, missing stories, conformance drift, test coverage) and fixes one per cycle."
pattern = "loop"

[maturity]
min_entities = 1
requires_running_app = false
requires = ["validate"]

[loop]
backlog_file = "agent/improve-backlog.md"
log_file = "agent/improve-log.md"
lock_file = ".dazzle/improve.lock"
max_cycles = 50
stale_lock_minutes = 30

[tools]
mcp = ["dsl.lint", "dsl.validate", "conformance.gaps", "test_intelligence.coverage", "story.coverage"]
cli = ["dazzle validate", "dazzle lint", "dazzle test run"]

[skill_template]
file = "improve.md.j2"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_command_models.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/agent_commands/loader.py src/dazzle/cli/agent_commands/definitions/improve.toml tests/unit/test_agent_command_models.py
git commit -m "feat(agent-commands): add TOML loader and first command definition"
```

---

### Task 3: Remaining TOML Definitions

**Files:**
- Create: `src/dazzle/cli/agent_commands/definitions/qa.toml`
- Create: `src/dazzle/cli/agent_commands/definitions/spec_sync.toml`
- Create: `src/dazzle/cli/agent_commands/definitions/ship.toml`
- Create: `src/dazzle/cli/agent_commands/definitions/polish.toml`
- Create: `src/dazzle/cli/agent_commands/definitions/issues.toml`
- Test: `tests/unit/test_agent_command_models.py` (extend)

- [ ] **Step 1: Write failing test for all six definitions**

Append to `tests/unit/test_agent_command_models.py`:

```python
def test_load_all_commands_finds_six():
    commands = load_all_commands()
    names = sorted(c.name for c in commands)
    assert names == ["improve", "issues", "polish", "qa", "ship", "spec-sync"]


def test_all_definitions_have_valid_versions():
    import re
    commands = load_all_commands()
    for cmd in commands:
        assert re.match(r"^\d+\.\d+\.\d+$", cmd.version), f"{cmd.name} has invalid version: {cmd.version}"


def test_all_loop_commands_have_backlog_files():
    commands = load_all_commands()
    for cmd in commands:
        if cmd.pattern == "loop":
            assert cmd.loop is not None, f"{cmd.name} is loop but has no loop config"
            assert cmd.loop.backlog_file.startswith("agent/"), f"{cmd.name} backlog not in agent/"
            assert cmd.loop.log_file.startswith("agent/"), f"{cmd.name} log not in agent/"


def test_all_commands_have_template_files():
    commands = load_all_commands()
    for cmd in commands:
        assert cmd.template_file.endswith(".md.j2"), f"{cmd.name} has no template_file"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_command_models.py::test_load_all_commands_finds_six -v`
Expected: FAIL — only 1 definition found (improve)

- [ ] **Step 3: Create the five remaining TOML definitions**

```toml
# src/dazzle/cli/agent_commands/definitions/qa.toml
[command]
name = "qa"
version = "1.0.0"
title = "Quality Assurance Cycle"
description = "Runs quality verification against the running app: story coverage, conformance checks, and test generation."
pattern = "loop"

[maturity]
min_stories = 1
requires_running_app = true

[loop]
backlog_file = "agent/qa-backlog.md"
log_file = "agent/qa-log.md"
lock_file = ".dazzle/qa.lock"
max_cycles = 30
stale_lock_minutes = 30

[tools]
mcp = ["story.coverage", "conformance.gaps", "conformance.summary", "test_intelligence.coverage"]
cli = ["dazzle test generate", "dazzle test run", "dazzle serve"]

[skill_template]
file = "qa.md.j2"
```

```toml
# src/dazzle/cli/agent_commands/definitions/spec_sync.toml
[command]
name = "spec-sync"
version = "1.0.0"
title = "Spec ↔ DSL Sync"
description = "Detects drift between SPEC.md and DSL, proposes patches to either side."
pattern = "one-shot"

[maturity]
requires_spec_md = true

[tools]
mcp = ["dsl.validate", "spec_analyze.discover_entities", "spec_analyze.extract_personas"]
cli = ["dazzle validate"]

[skill_template]
file = "spec_sync.md.j2"
```

```toml
# src/dazzle/cli/agent_commands/definitions/ship.toml
[command]
name = "ship"
version = "1.0.0"
title = "Validate and Ship"
description = "Project-level commit + validate + push discipline with pre-flight quality gates."
pattern = "one-shot"

[maturity]
min_entities = 1
requires = ["validate"]

[tools]
mcp = ["dsl.validate", "dsl.lint"]
cli = ["dazzle validate", "dazzle lint"]

[skill_template]
file = "ship.md.j2"
```

```toml
# src/dazzle/cli/agent_commands/definitions/polish.toml
[command]
name = "polish"
version = "1.0.0"
title = "UX Polish Cycle"
description = "Audits UX quality per surface and persona, fixes the worst-scoring area per cycle."
pattern = "loop"

[maturity]
min_surfaces = 3
requires_running_app = true

[loop]
backlog_file = "agent/polish-backlog.md"
log_file = "agent/polish-log.md"
lock_file = ".dazzle/polish.lock"
max_cycles = 30
stale_lock_minutes = 30

[tools]
mcp = ["composition.audit", "discovery.coherence", "dsl.fidelity"]
cli = ["dazzle serve", "dazzle ux verify"]

[skill_template]
file = "polish.md.j2"
```

```toml
# src/dazzle/cli/agent_commands/definitions/issues.toml
[command]
name = "issues"
version = "1.0.0"
title = "GitHub Issue Resolver"
description = "Triages open GitHub issues, implements fixes, ships and closes them in a loop."
pattern = "loop"

[maturity]
requires_github_remote = true

[loop]
backlog_file = "agent/issues-log.md"
log_file = "agent/issues-log.md"
lock_file = ".dazzle/issues.lock"
max_cycles = 20
stale_lock_minutes = 45

[tools]
mcp = ["dsl.validate", "dsl.lint"]
cli = ["dazzle validate", "dazzle lint", "dazzle test run"]

[skill_template]
file = "issues.md.j2"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_command_models.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/agent_commands/definitions/
git commit -m "feat(agent-commands): add all six command TOML definitions"
```

---

### Task 4: Maturity Gate Evaluator and Template Renderer

**Files:**
- Create: `src/dazzle/cli/agent_commands/renderer.py`
- Test: `tests/unit/test_agent_command_models.py` (extend)

- [ ] **Step 1: Write failing tests for maturity evaluation**

Append to `tests/unit/test_agent_command_models.py`:

```python
from dazzle.cli.agent_commands.renderer import evaluate_maturity


def _make_project_context(
    *,
    entity_count: int = 0,
    surface_count: int = 0,
    story_count: int = 0,
    has_spec_md: bool = False,
    has_github_remote: bool = False,
    validate_passes: bool = True,
) -> dict:
    return {
        "entity_count": entity_count,
        "surface_count": surface_count,
        "story_count": story_count,
        "has_spec_md": has_spec_md,
        "has_github_remote": has_github_remote,
        "validate_passes": validate_passes,
    }


def test_evaluate_maturity_all_met():
    gate = MaturityGate(min_entities=1)
    ctx = _make_project_context(entity_count=3)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is True
    assert reason is None


def test_evaluate_maturity_entities_unmet():
    gate = MaturityGate(min_entities=2)
    ctx = _make_project_context(entity_count=1)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert "entities" in reason.lower()


def test_evaluate_maturity_surfaces_unmet():
    gate = MaturityGate(min_surfaces=3)
    ctx = _make_project_context(surface_count=1)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert "surfaces" in reason.lower()


def test_evaluate_maturity_spec_md_required():
    gate = MaturityGate(requires_spec_md=True)
    ctx = _make_project_context(has_spec_md=False)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert "SPEC.md" in reason


def test_evaluate_maturity_github_remote_required():
    gate = MaturityGate(requires_github_remote=True)
    ctx = _make_project_context(has_github_remote=False)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert "GitHub" in reason


def test_evaluate_maturity_validate_required():
    gate = MaturityGate(requires=["validate"])
    ctx = _make_project_context(validate_passes=False)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert "validate" in reason.lower()


def test_evaluate_maturity_empty_gate_always_available():
    gate = MaturityGate()
    ctx = _make_project_context()
    available, reason = evaluate_maturity(gate, ctx)
    assert available is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_command_models.py::test_evaluate_maturity_all_met -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate_maturity'`

- [ ] **Step 3: Implement the renderer module**

```python
# src/dazzle/cli/agent_commands/renderer.py
"""Evaluate maturity gates and render agent command templates."""

import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .loader import load_all_commands
from .models import CommandDefinition, CommandStatus, MaturityGate, SyncManifest

TEMPLATES_DIR = Path(__file__).parent / "templates"


def evaluate_maturity(
    gate: MaturityGate, ctx: dict
) -> tuple[bool, str | None]:
    """Check whether a project meets a command's maturity prerequisites.

    Returns (available, reason). reason is None when available is True.
    """
    if gate.min_entities > 0 and ctx.get("entity_count", 0) < gate.min_entities:
        return False, f"Requires {gate.min_entities}+ entities (project has {ctx.get('entity_count', 0)})"

    if gate.min_surfaces > 0 and ctx.get("surface_count", 0) < gate.min_surfaces:
        return False, f"Requires {gate.min_surfaces}+ surfaces (project has {ctx.get('surface_count', 0)})"

    if gate.min_stories > 0 and ctx.get("story_count", 0) < gate.min_stories:
        return False, f"Requires {gate.min_stories}+ stories (project has {ctx.get('story_count', 0)})"

    if gate.requires_spec_md and not ctx.get("has_spec_md", False):
        return False, "Requires SPEC.md in project root"

    if gate.requires_github_remote and not ctx.get("has_github_remote", False):
        return False, "Requires a GitHub remote configured"

    if gate.requires_running_app and not ctx.get("app_running", False):
        return False, "Requires a running app (dazzle serve)"

    if "validate" in gate.requires and not ctx.get("validate_passes", True):
        return False, "Requires dazzle validate to pass"

    return True, None


def build_project_context(project_root: Path) -> dict:
    """Introspect a Dazzle project to build the maturity context dict."""
    ctx: dict = {
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
    for name in ("SPEC.md", "spec.md"):
        if (project_root / name).exists():
            ctx["has_spec_md"] = True
            break

    # Check for GitHub remote
    git_config = project_root / ".git" / "config"
    if git_config.exists():
        content = git_config.read_text(encoding="utf-8", errors="replace")
        ctx["has_github_remote"] = "github.com" in content

    # Try to parse AppSpec for counts
    try:
        from dazzle.core.manifest import load_manifest

        manifest = load_manifest(project_root / "dazzle.toml")
        from dazzle.core.parser import parse_project

        appspec = parse_project(project_root, manifest)
        ctx["entity_count"] = len(appspec.entities)
        ctx["surface_count"] = len(appspec.surfaces)
        ctx["story_count"] = len(getattr(appspec, "stories", []))
        ctx["entity_names"] = [e.name for e in appspec.entities]
        ctx["persona_names"] = [p.id for p in getattr(appspec, "personas", [])]
        ctx["surface_names"] = [s.name for s in appspec.surfaces]
        ctx["validate_passes"] = True
    except Exception:
        ctx["validate_passes"] = False

    return ctx


def render_skill(cmd: CommandDefinition, ctx: dict) -> str:
    """Render a command's Jinja2 skill template with project context."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(cmd.template_file)
    return template.render(cmd=cmd, ctx=ctx)


def render_agents_md(commands: list[tuple[CommandDefinition, bool, str | None]], ctx: dict) -> str:
    """Render the AGENTS.md file from all commands."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("agents_md.j2")
    return template.render(commands=commands, ctx=ctx)


def render_claude_md_section(commands: list[tuple[CommandDefinition, bool, str | None]], ctx: dict) -> str:
    """Render the section to append to .claude/CLAUDE.md."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("claude_md_section.j2")
    return template.render(commands=commands, ctx=ctx)


def sync_to_project(project_root: Path) -> SyncManifest:
    """Write all agent command files to a project. Returns the manifest."""
    from dazzle import __version__ as dazzle_version

    ctx = build_project_context(project_root)
    all_commands = load_all_commands()

    # Evaluate maturity for each command
    evaluated: list[tuple[CommandDefinition, bool, str | None]] = []
    manifest_commands: dict[str, CommandStatus] = {}
    for cmd in all_commands:
        available, reason = evaluate_maturity(cmd.maturity, ctx)
        evaluated.append((cmd, available, reason))
        manifest_commands[cmd.name] = CommandStatus(
            version=cmd.version, available=available, reason=reason
        )

    # Create directories
    commands_dir = project_root / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    agent_dir = project_root / "agent"
    agent_dir.mkdir(exist_ok=True)

    # Write skill files for available commands
    for cmd, available, _reason in evaluated:
        if available and cmd.template_file:
            content = render_skill(cmd, ctx)
            skill_path = commands_dir / f"{cmd.name}.md"
            skill_path.write_text(
                f"<!-- dazzle-agent-command:{cmd.name}:v{cmd.version} -->\n{content}",
                encoding="utf-8",
            )

    # Seed empty backlog/log files (don't overwrite existing)
    for cmd, available, _reason in evaluated:
        if available and cmd.loop:
            for file_attr in ("backlog_file", "log_file"):
                rel_path = getattr(cmd.loop, file_attr)
                if rel_path:
                    full_path = project_root / rel_path
                    if not full_path.exists():
                        full_path.write_text(
                            f"# {cmd.title}\n\n_Seeded by `dazzle agent sync`._\n",
                            encoding="utf-8",
                        )

    # Write AGENTS.md
    agents_md = render_agents_md(evaluated, ctx)
    (project_root / "AGENTS.md").write_text(agents_md, encoding="utf-8")

    # Append to .claude/CLAUDE.md (idempotent)
    claude_md_path = project_root / ".claude" / "CLAUDE.md"
    marker = "## Autonomous Development Commands"
    existing = ""
    if claude_md_path.exists():
        existing = claude_md_path.read_text(encoding="utf-8")
    if marker not in existing:
        section = render_claude_md_section(evaluated, ctx)
        with open(claude_md_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{section}")

    # Write manifest
    manifest = SyncManifest(
        dazzle_version=dazzle_version,
        commands_version="1.0.0",
        synced_at=datetime.now(timezone.utc).isoformat(),
        commands=manifest_commands,
    )
    manifest_path = commands_dir / ".manifest.json"
    manifest_data = {
        "dazzle_version": manifest.dazzle_version,
        "commands_version": manifest.commands_version,
        "synced_at": manifest.synced_at,
        "commands": {
            name: {"version": cs.version, "available": cs.available, "reason": cs.reason}
            for name, cs in manifest.commands.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return manifest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_command_models.py -v`
Expected: All 20 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/agent_commands/renderer.py
git commit -m "feat(agent-commands): add maturity gate evaluator and template renderer"
```

---

### Task 5: Skill Templates

**Files:**
- Create: `src/dazzle/cli/agent_commands/templates/improve.md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/qa.md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/spec_sync.md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/ship.md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/polish.md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/issues.md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/agents_md.j2`
- Create: `src/dazzle/cli/agent_commands/templates/claude_md_section.j2`
- Test: `tests/unit/test_agent_command_models.py` (extend)

- [ ] **Step 1: Write failing test for template rendering**

Append to `tests/unit/test_agent_command_models.py`:

```python
from dazzle.cli.agent_commands.renderer import render_skill, render_agents_md, render_claude_md_section, TEMPLATES_DIR


def test_all_templates_exist():
    commands = load_all_commands()
    for cmd in commands:
        tmpl_path = TEMPLATES_DIR / cmd.template_file
        assert tmpl_path.exists(), f"Missing template: {cmd.template_file}"
    assert (TEMPLATES_DIR / "agents_md.j2").exists()
    assert (TEMPLATES_DIR / "claude_md_section.j2").exists()


def test_render_improve_skill():
    commands = load_all_commands()
    improve = next(c for c in commands if c.name == "improve")
    ctx = {"entity_names": ["Task", "User"], "persona_names": ["admin"], "project_name": "myapp"}
    html = render_skill(improve, ctx)
    assert "Autonomous Improvement Loop" in html
    assert "dsl.lint" in html or "dazzle lint" in html
    assert "agent/improve-backlog.md" in html


def test_render_agents_md():
    commands = load_all_commands()
    evaluated = [(cmd, True, None) for cmd in commands]
    ctx = {"project_name": "myapp"}
    content = render_agents_md(evaluated, ctx)
    assert "# Agent Commands" in content
    assert "/improve" in content
    assert "dazzle agent sync" in content


def test_render_claude_md_section():
    commands = load_all_commands()
    evaluated = [(cmd, True, None) for cmd in commands]
    ctx = {"project_name": "myapp"}
    content = render_claude_md_section(evaluated, ctx)
    assert "## Autonomous Development Commands" in content
    assert "agent_commands" in content or "check_updates" in content
    assert "Agent Tool Convention" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_command_models.py::test_all_templates_exist -v`
Expected: FAIL — templates don't exist yet

- [ ] **Step 3: Create all eight templates**

```jinja2
{# src/dazzle/cli/agent_commands/templates/improve.md.j2 #}
# /improve — Autonomous Improvement Loop

Discover one quality gap per cycle, fix it, verify, commit. Repeat.

## Backlog

State file: `{{ cmd.loop.backlog_file }}`
Log file: `{{ cmd.loop.log_file }}`

## Cycle

### Step 1: Seed (first run only)

If `{{ cmd.loop.backlog_file }}` is empty or contains only the seeded header, populate it:

1. Run `dazzle validate` — record any validation errors as gaps
2. Run `dazzle lint` — record lint warnings as gaps
3. Call `mcp__dazzle__conformance operation=gaps` — record conformance gaps
4. Call `mcp__dazzle__story operation=coverage` — record uncovered stories
5. Call `mcp__dazzle__test_intelligence operation=coverage` — record untested areas

Write each gap as a row in the backlog table:

| # | Type | Description | Status | Notes |
|---|------|-------------|--------|-------|
| 1 | lint | Missing field description on Task.title | PENDING | |

### Step 2: Pick

Select the highest-priority PENDING gap:
- **Priority**: validation_error > conformance_gap > lint_warning > coverage_gap > enhancement
- Skip any row marked BLOCKED (attempts > 3)

Mark the row IN_PROGRESS. Increment attempts.

### Step 3: Fix

Edit DSL files, app code, or configuration to address the gap. Keep the fix focused — one gap per cycle.

### Step 4: Verify

Re-run the tool that found the gap. Confirm the specific issue is resolved.

### Step 5: Commit

```bash
git add -A && git commit -m "improve: fix [gap-type] — [description]"
```

### Step 6: Log

Append to `{{ cmd.loop.log_file }}`:

```
## Cycle [N] — [timestamp]
- Gap: #[id] [description]
- Action: [what was changed]
- Result: FIXED | BLOCKED | DEFERRED
- Commit: [sha]
```

Mark the backlog row DONE (or BLOCKED if the fix failed after 3 attempts).

### Step 7: Loop

Return to Step 2. Stop after {{ cmd.loop.max_cycles }} cycles or when no PENDING rows remain.

## Lock

Acquire `{{ cmd.loop.lock_file }}` before starting. Release on exit. Stale locks (> {{ cmd.loop.stale_lock_minutes }} min) may be deleted.
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/qa.md.j2 #}
# /qa — Quality Assurance Cycle

Run quality verification against the running app. Requires `dazzle serve`.

## Backlog

State file: `{{ cmd.loop.backlog_file }}`
Log file: `{{ cmd.loop.log_file }}`

## Prerequisites

The app must be running: `dazzle serve --local`

## Cycle

### Step 1: Seed (first run only)

If `{{ cmd.loop.backlog_file }}` is empty, populate it:

1. Call `mcp__dazzle__story operation=coverage` — list stories with test status
2. Call `mcp__dazzle__conformance operation=gaps` — list failing conformance cases
3. Call `mcp__dazzle__test_intelligence operation=coverage` — identify untested paths

Write each item as a row:

| # | Type | Description | Status | Notes |
|---|------|-------------|--------|-------|
| 1 | story | As admin, I can assign tickets | PENDING | |

### Step 2: Pick

Select highest-priority PENDING item (failing conformance > untested story > coverage gap).

### Step 3: Test

1. Generate a test: `dazzle test generate --story [story_name]`
2. Run the test: `dazzle test run`
3. Observe the result

### Step 4: Assess

- If the test passes: mark DONE
- If the test fails due to a real bug: fix the DSL/code, re-test, then mark DONE
- If the test fails due to test design: note in backlog, mark DEFERRED

### Step 5: Commit + Log

Commit fixes and test files. Append cycle result to `{{ cmd.loop.log_file }}`.

### Step 6: Loop

Return to Step 2. Stop after {{ cmd.loop.max_cycles }} cycles or when no PENDING rows remain.
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/spec_sync.md.j2 #}
# /spec-sync — Spec ↔ DSL Sync

Detect drift between SPEC.md and the DSL. Propose patches to either side.

## Steps

### Step 1: Parse both sides

1. Read `SPEC.md` — extract stated entities, personas, workflows, and business rules
2. Call `mcp__dazzle__dsl operation=validate` — get the current DSL state
3. Call `mcp__dazzle__spec_analyze operation=discover_entities spec_path=SPEC.md` — structured entity list from spec

### Step 2: Diff

Compare the two sides:

| Category | In SPEC.md but not DSL | In DSL but not SPEC.md |
|----------|----------------------|----------------------|
| Entities | List missing entities | List undocumented entities |
| Personas | List missing personas | List undocumented personas |
| Workflows | List missing workflows | List undocumented surfaces |

### Step 3: Propose patches

- **Spec-ahead items** (in spec but not DSL): propose DSL additions
- **DSL-ahead items** (in DSL but not spec): propose SPEC.md updates

Present the full diff to the user before applying.

### Step 4: Apply and commit

Apply approved patches. Commit with message: `sync: align [SPEC.md|DSL] — [summary]`
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/ship.md.j2 #}
# /ship — Validate and Ship

Commit all current changes with pre-flight quality gates.

## Steps

### Step 1: Pre-flight

1. Run `git status` to understand what changed
2. Run `dazzle validate` — must pass. Fix any errors before proceeding.
3. Run `dazzle lint` — fix any warnings

### Step 2: Test (if tests exist)

If `dsl/tests/` or `tests/` directories exist, run `dazzle test run`. Fix any failures.

### Step 3: Commit

1. Stage relevant changed files by name (never `git add -A`)
2. Do NOT stage files that look like secrets (.env, credentials, tokens)
3. Write a concise commit message explaining *why* the change was made
4. Use conventional commit style: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`

### Step 4: Push

Run `git push`. If rejected (non-fast-forward), do NOT force-push — inform the user.

### Step 5: Verify

Run `git status` to confirm the worktree is clean.
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/polish.md.j2 #}
# /polish — UX Polish Cycle

Audit UX quality per surface and persona, fix the worst-scoring area per cycle.

## Backlog

State file: `{{ cmd.loop.backlog_file }}`
Log file: `{{ cmd.loop.log_file }}`

## Prerequisites

The app must be running: `dazzle serve --local`

## Cycle

### Step 1: Audit

1. Call `mcp__dazzle__composition operation=audit` — get component quality scores
2. Call `mcp__dazzle__discovery operation=coherence` — get per-persona UX coherence
3. Call `mcp__dazzle__dsl operation=fidelity` — check surface-entity field coverage

Populate or update `{{ cmd.loop.backlog_file }}` with findings:

| # | Surface | Persona | Issue | Score | Status | Notes |
|---|---------|---------|-------|-------|--------|-------|
| 1 | task_list | admin | Missing empty state | 40 | PENDING | |

### Step 2: Pick

Select the lowest-scoring PENDING row.

### Step 3: Investigate

Load the surface in the running app. Check:
- Empty state handling
- Error state handling
- Persona-specific rendering (permissions, hidden fields)
- Responsive layout
- Accessibility (ARIA, keyboard nav)

### Step 4: Fix

Apply DSL adjustments (`ux` blocks, field visibility, empty messages), sitespec tweaks, or template overrides.

### Step 5: Verify

Re-run the audit tool. Confirm the score improved for the target surface.

### Step 6: Commit + Log

Commit with message: `polish: improve [surface] — [what changed]`
Append cycle result to `{{ cmd.loop.log_file }}`.

### Step 7: Loop

Return to Step 1 (re-audit to pick up cascading effects). Stop after {{ cmd.loop.max_cycles }} cycles.
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/issues.md.j2 #}
# /issues — GitHub Issue Resolver

Triage open GitHub issues, implement fixes, ship and close them in a loop.

## Backlog

Log file: `{{ cmd.loop.log_file }}`

## Cycle

### Step 1: Triage

1. Run `gh issue list --state open --limit 50 --json number,title,labels`
2. For each open issue, check if already resolved: `git log --oneline --all --grep="#<number>"`
3. If a commit exists: post a comment summarising the fix, close the issue
4. Display remaining open issues

### Step 2: Pick

Select the highest-priority issue:
- **Priority**: bug > enhancement > feature
- **Dependencies**: issues that unblock others first
- **Complexity**: prefer smaller, well-scoped issues

### Step 3: Investigate

1. Read the full issue: `gh issue view <number>`
2. Search the codebase for relevant files
3. Identify root cause (bugs) or design approach (features)

### Step 4: Fix

Implement the fix. Keep changes focused — one issue per cycle.

### Step 5: Verify

1. Run `dazzle validate`
2. Run `dazzle test run` (if tests exist)
3. Fix any failures

### Step 6: Ship

1. Commit with message referencing the issue: `fix: [description] (#<number>)`
2. Push to remote
3. Post a comment on the issue summarising what was done
4. Close the issue: `gh issue close <number>`

### Step 7: Log

Append to `{{ cmd.loop.log_file }}`:

```
## Issue #[number] — [title] — [timestamp]
- Action: [what was changed]
- Commit: [sha]
- Status: CLOSED
```

### Step 8: Loop

Return to Step 1. Stop after {{ cmd.loop.max_cycles }} cycles or when no open issues remain.
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/agents_md.j2 #}
# Agent Commands

This project uses [Dazzle](https://github.com/manwithacat/dazzle) autonomous development commands.
Run `dazzle agent sync` to update commands when the framework is upgraded.

## Available Commands

{% for cmd, available, reason in commands %}
{% if available %}
### /{{ cmd.name }}

{{ cmd.description }}

- **Pattern**: {{ cmd.pattern }}
{% if cmd.loop %}
- **Backlog**: `{{ cmd.loop.backlog_file }}`
{% endif %}
- **Tools**: {{ cmd.tools.cli | join(", ") }}{% if cmd.tools.mcp %}, MCP: {{ cmd.tools.mcp | join(", ") }}{% endif %}

{% endif %}
{% endfor %}
{% set unavailable = commands | selectattr("1", "false") | list %}
{% if unavailable %}
## Upcoming Commands

These commands will become available as the project matures:

{% for cmd, available, reason in commands %}
{% if not available %}
- **{{ cmd.title }}** — {{ reason }}
{% endif %}
{% endfor %}
{% endif %}

## Agent Tool Convention

When developing new autonomous workflows for this project, follow the established pattern:

- **Backlog**: `agent/{tool-name}-backlog.md` — markdown table tracking items to process. Columns vary by tool, but always include an ID, status (PENDING/IN_PROGRESS/DONE/BLOCKED), and notes.
- **Log**: `agent/{tool-name}-log.md` — append-only cycle history. Each entry records timestamp, what was attempted, and outcome.
- Both files are git-tracked. The historical record of agent cognition and decision-making is valuable.
```

```jinja2
{# src/dazzle/cli/agent_commands/templates/claude_md_section.j2 #}
## Autonomous Development Commands

This project has Dazzle agent commands installed. Commands are synced
from the Dazzle framework and can be updated with `dazzle agent sync`.

### Session Start

At the start of each session, call `mcp__dazzle__agent_commands operation=check_updates`
with `commands_version` from `.claude/commands/.manifest.json`. If stale, run `dazzle agent sync`.

### Available Commands
{% for cmd, available, reason in commands %}
{% if available %}
- `/{{ cmd.name }}` — {{ cmd.description }} ({{ cmd.pattern }})
{% endif %}
{% endfor %}

### Running Loops

Loop commands can be run as single cycles or continuously:
- Single cycle: `/improve`
- Continuous: `/loop /improve`
- Timed: `/loop 30m /improve`

### State Files

- `agent/` — Backlogs and logs (git-tracked)
- `.dazzle/` — Locks and runtime state (gitignored)

### Agent Tool Convention

When developing new autonomous workflows for this project, follow the established pattern:

- **Backlog**: `agent/{tool-name}-backlog.md` — markdown table tracking items to process. Columns vary by tool, but always include an ID, status (PENDING/IN_PROGRESS/DONE/BLOCKED), and notes.
- **Log**: `agent/{tool-name}-log.md` — append-only cycle history. Each entry records timestamp, what was attempted, and outcome.
- Both files are git-tracked. The historical record of agent cognition and decision-making is valuable for project understanding.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_command_models.py -v`
Expected: All 24 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/agent_commands/templates/
git commit -m "feat(agent-commands): add all skill and meta templates"
```

---

### Task 6: CLI `dazzle agent sync` Command

**Files:**
- Modify: `src/dazzle/cli/agent_commands/__init__.py`
- Modify: `src/dazzle/cli/__init__.py`
- Test: `tests/unit/test_agent_sync.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/unit/test_agent_sync.py
"""Integration tests for dazzle agent sync."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def minimal_project(tmp_path):
    """Create a minimal Dazzle project structure."""
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(
        'module test\napp test "Test App"\n\n'
        'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'
    )
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "test"\n\n[modules]\ncore = "dsl"\n'
    )
    (tmp_path / "SPEC.md").write_text("# Test App\n\nA simple task manager.\n" * 10)
    return tmp_path


def test_sync_creates_command_files(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    commands_dir = minimal_project / ".claude" / "commands"
    assert commands_dir.is_dir()
    # improve and ship should be available (min_entities=1, and we have 1 entity)
    assert (commands_dir / "improve.md").exists()
    assert (commands_dir / "ship.md").exists()


def test_sync_creates_manifest(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    manifest_path = minimal_project / ".claude" / "commands" / ".manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert "dazzle_version" in data
    assert "commands_version" in data
    assert "commands" in data
    assert "improve" in data["commands"]


def test_sync_creates_agents_md(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    agents_md = minimal_project / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "Agent Commands" in content
    assert "/improve" in content


def test_sync_seeds_backlog_files(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    assert (minimal_project / "agent" / "improve-backlog.md").exists()
    assert (minimal_project / "agent" / "improve-log.md").exists()


def test_sync_is_idempotent(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    first_agents_md = (minimal_project / "AGENTS.md").read_text()

    sync_to_project(minimal_project)
    second_agents_md = (minimal_project / "AGENTS.md").read_text()

    assert first_agents_md == second_agents_md


def test_sync_preserves_existing_backlogs(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    # First sync seeds empty backlogs
    sync_to_project(minimal_project)

    # User/agent adds content
    backlog = minimal_project / "agent" / "improve-backlog.md"
    backlog.write_text("# Improve Backlog\n\n| # | Type | Status |\n|---|------|--------|\n| 1 | lint | DONE |\n")

    # Second sync should NOT overwrite
    sync_to_project(minimal_project)
    assert "DONE" in backlog.read_text()


def test_sync_appends_to_claude_md(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    # Create existing CLAUDE.md
    claude_md = minimal_project / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text("# Project Instructions\n\nExisting content.\n")

    sync_to_project(minimal_project)
    content = claude_md.read_text()
    assert "Existing content" in content
    assert "Autonomous Development Commands" in content


def test_sync_does_not_duplicate_claude_md_section(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    sync_to_project(minimal_project)

    claude_md = minimal_project / ".claude" / "CLAUDE.md"
    content = claude_md.read_text()
    assert content.count("## Autonomous Development Commands") == 1


def test_unavailable_commands_not_written(minimal_project):
    from dazzle.cli.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    commands_dir = minimal_project / ".claude" / "commands"
    # polish requires 3+ surfaces — our minimal project has 0 surfaces
    assert not (commands_dir / "polish.md").exists()
    # issues requires GitHub remote
    assert not (commands_dir / "issues.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_sync.py -v`
Expected: FAIL — tests may partially pass (sync_to_project exists from Task 4) but some will fail due to AppSpec parsing issues in tmp_path

- [ ] **Step 3: Create the CLI command**

```python
# src/dazzle/cli/agent_commands/__init__.py
"""Agent-first development commands for Dazzle projects.

CLI subgroup: `dazzle agent sync`
"""

from pathlib import Path

import typer

agent_app = typer.Typer(
    name="agent",
    help="Agent-first development commands.",
    no_args_is_help=True,
)


@agent_app.command("sync")
def sync_command(
    project: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project root directory.",
    ),
) -> None:
    """Sync agent commands from the Dazzle framework to the project.

    Writes .claude/commands/*.md, AGENTS.md, and seeds agent/ backlog files.
    Idempotent — safe to run repeatedly.
    """
    project = project.resolve()

    if not (project / "dazzle.toml").exists():
        typer.echo(f"Error: {project} does not contain a dazzle.toml", err=True)
        raise typer.Exit(code=1)

    from .renderer import sync_to_project

    manifest = sync_to_project(project)

    available = sum(1 for cs in manifest.commands.values() if cs.available)
    total = len(manifest.commands)
    typer.echo(f"Synced {available}/{total} agent commands to {project}")

    for name, cs in sorted(manifest.commands.items()):
        status = "available" if cs.available else f"unavailable ({cs.reason})"
        typer.echo(f"  /{name}: {status}")
```

- [ ] **Step 4: Register the CLI subgroup**

In `src/dazzle/cli/__init__.py`, add the import and registration alongside other `add_typer` calls:

Add import near the other CLI imports (around line 50-80):
```python
from dazzle.cli.agent_commands import agent_app
```

Add registration alongside the other `add_typer` calls (around line 267):
```python
app.add_typer(agent_app, name="agent")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_sync.py -v`
Expected: All 9 tests PASS

Note: Some tests may need the `build_project_context` function to gracefully handle projects where AppSpec parsing fails (the `try/except` in Task 4's implementation handles this). If tests fail because the tmp_path project can't fully parse, adjust `build_project_context` to set counts from the TOML file rather than requiring a full AppSpec parse.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/agent_commands/__init__.py src/dazzle/cli/__init__.py tests/unit/test_agent_sync.py
git commit -m "feat(agent-commands): add dazzle agent sync CLI command"
```

---

### Task 7: MCP Handler

**Files:**
- Create: `src/dazzle/mcp/server/handlers/agent_commands.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Test: `tests/unit/test_agent_commands_handler.py`

- [ ] **Step 1: Write failing tests for MCP handler**

```python
# tests/unit/test_agent_commands_handler.py
"""Tests for the agent_commands MCP handler."""

import json
from pathlib import Path
from unittest.mock import patch

from dazzle.mcp.server.handlers.agent_commands import (
    handle_list,
    handle_get,
    handle_check_updates,
)


def _mock_project_context(**overrides):
    ctx = {
        "entity_count": 3,
        "surface_count": 5,
        "story_count": 2,
        "has_spec_md": True,
        "has_github_remote": True,
        "validate_passes": True,
        "app_running": False,
        "entity_names": ["Task", "User", "Comment"],
        "persona_names": ["admin", "user"],
        "surface_names": ["task_list", "task_detail", "user_list", "user_detail", "comment_list"],
        "project_name": "test_app",
    }
    ctx.update(overrides)
    return ctx


def test_list_returns_all_commands():
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_project_context(),
    ):
        result = handle_list(Path("/fake"), {})
    data = json.loads(result)
    assert "commands" in data
    names = [c["name"] for c in data["commands"]]
    assert "improve" in names
    assert "qa" in names
    assert "ship" in names


def test_list_shows_availability():
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_project_context(surface_count=1),
    ):
        result = handle_list(Path("/fake"), {})
    data = json.loads(result)
    polish = next(c for c in data["commands"] if c["name"] == "polish")
    assert polish["available"] is False
    assert "surfaces" in polish["reason"].lower()


def test_get_returns_rendered_skill():
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_project_context(),
    ):
        result = handle_get(Path("/fake"), {"command": "improve"})
    data = json.loads(result)
    assert "content" in data
    assert "Autonomous Improvement Loop" in data["content"]


def test_get_unknown_command():
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_project_context(),
    ):
        result = handle_get(Path("/fake"), {"command": "nonexistent"})
    data = json.loads(result)
    assert "error" in data


def test_check_updates_current():
    result = handle_check_updates(Path("/fake"), {"commands_version": "1.0.0"})
    data = json.loads(result)
    assert data["up_to_date"] is True


def test_check_updates_stale():
    result = handle_check_updates(Path("/fake"), {"commands_version": "0.1.0"})
    data = json.loads(result)
    assert data["up_to_date"] is False
    assert "commands_version" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_commands_handler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create the MCP handler**

```python
# src/dazzle/mcp/server/handlers/agent_commands.py
"""MCP handler for agent_commands tool — read-only operations.

Operations: list, get, check_updates.
File writing is handled by `dazzle agent sync` CLI (ADR-0002).
"""

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.cli.agent_commands.loader import load_all_commands
from dazzle.cli.agent_commands.renderer import (
    build_project_context,
    evaluate_maturity,
    render_skill,
)

logger = logging.getLogger(__name__)

# Bump this when command definitions change
COMMANDS_VERSION = "1.0.0"


def handle_list(project_path: Path, args: dict[str, Any]) -> str:
    """List all commands with availability for the current project."""
    ctx = build_project_context(project_path)
    all_commands = load_all_commands()

    commands_out = []
    for cmd in all_commands:
        available, reason = evaluate_maturity(cmd.maturity, ctx)
        commands_out.append({
            "name": cmd.name,
            "version": cmd.version,
            "title": cmd.title,
            "pattern": cmd.pattern,
            "description": cmd.description,
            "available": available,
            "reason": reason,
        })

    from dazzle import __version__ as dazzle_version

    return json.dumps({
        "commands": commands_out,
        "dazzle_version": dazzle_version,
        "commands_version": COMMANDS_VERSION,
    }, indent=2)


def handle_get(project_path: Path, args: dict[str, Any]) -> str:
    """Get the rendered skill content for a single command."""
    command_name = args.get("command", "")
    ctx = build_project_context(project_path)
    all_commands = load_all_commands()

    cmd = next((c for c in all_commands if c.name == command_name), None)
    if cmd is None:
        return json.dumps({"error": f"Unknown command: {command_name}"}, indent=2)

    available, reason = evaluate_maturity(cmd.maturity, ctx)
    content = render_skill(cmd, ctx) if cmd.template_file else ""

    return json.dumps({
        "name": cmd.name,
        "version": cmd.version,
        "available": available,
        "reason": reason,
        "content": content,
    }, indent=2)


def handle_check_updates(project_path: Path, args: dict[str, Any]) -> str:
    """Check if local command files are up to date."""
    local_version = args.get("commands_version", "0.0.0")
    up_to_date = local_version == COMMANDS_VERSION

    result: dict[str, Any] = {
        "up_to_date": up_to_date,
        "commands_version": COMMANDS_VERSION,
        "local_version": local_version,
    }
    if not up_to_date:
        result["action"] = "Run `dazzle agent sync` to update agent commands."

    return json.dumps(result, indent=2)
```

- [ ] **Step 4: Register the tool and handler**

In `src/dazzle/mcp/server/tools_consolidated.py`, add inside `get_consolidated_tools()` return list:

```python
Tool(
    name="agent_commands",
    description=(
        "Agent development commands: list (available commands with maturity status), "
        "get (rendered skill content for a command), "
        "check_updates (version comparison for sync)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            **PROJECT_PATH_SCHEMA,
            "operation": {
                "type": "string",
                "enum": ["list", "get", "check_updates"],
                "description": "Operation to perform",
            },
            "command": {
                "type": "string",
                "description": "Command name (for 'get' operation)",
            },
            "commands_version": {
                "type": "string",
                "description": "Local commands_version from .manifest.json (for 'check_updates')",
            },
        },
        "required": ["operation"],
    },
),
```

In `src/dazzle/mcp/server/handlers_consolidated.py`, add the handler registration:

Add import string near other module constants:
```python
_MOD_AGENT_CMDS = "dazzle.mcp.server.handlers.agent_commands"
```

Add handler creation alongside other `_make_project_handler` calls:
```python
handle_agent_commands: Callable[[dict[str, Any]], str] = _make_project_handler(
    "agent_commands",
    {
        "list": f"{_MOD_AGENT_CMDS}:handle_list",
        "get": f"{_MOD_AGENT_CMDS}:handle_get",
        "check_updates": f"{_MOD_AGENT_CMDS}:handle_check_updates",
    },
)
```

Add to `CONSOLIDATED_TOOL_HANDLERS` dict:
```python
"agent_commands": handle_agent_commands,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_commands_handler.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/server/handlers/agent_commands.py src/dazzle/mcp/server/tools_consolidated.py src/dazzle/mcp/server/handlers_consolidated.py tests/unit/test_agent_commands_handler.py
git commit -m "feat(agent-commands): add MCP handler and register tool"
```

---

### Task 8: Bootstrap Integration

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/bootstrap.py`

- [ ] **Step 1: Add agent command nudge to bootstrap**

In `src/dazzle/mcp/server/handlers/bootstrap.py`, modify the `_build_instructions` function. Add the agent command setup instruction to both the `has_questions` and no-questions branches.

At the end of both return dicts in `_build_instructions`, add:

```python
"agent_commands_setup": {
    "action": "Run `dazzle agent sync` to install autonomous development commands",
    "description": (
        "This installs agent commands (/improve, /qa, /ship, etc.) that "
        "enable autonomous quality improvement and development workflows."
    ),
    "when": "after_first_successful_validate",
},
```

Specifically, add this key to both the `return` dict at line ~181 (has_questions branch) and the `return` dict at line ~219 (generation branch), inside the `agent_instructions` dict.

- [ ] **Step 2: Run existing bootstrap tests to verify nothing broke**

Run: `pytest tests/unit/ -k bootstrap -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/mcp/server/handlers/bootstrap.py
git commit -m "feat(agent-commands): add agent command setup nudge to bootstrap"
```

---

### Task 9: Quality Gates and Final Verification

- [ ] **Step 1: Run full lint**

```bash
ruff check src/dazzle/cli/agent_commands/ src/dazzle/mcp/server/handlers/agent_commands.py tests/unit/test_agent_command_models.py tests/unit/test_agent_commands_handler.py tests/unit/test_agent_sync.py --fix
ruff format src/dazzle/cli/agent_commands/ src/dazzle/mcp/server/handlers/agent_commands.py tests/unit/test_agent_command_models.py tests/unit/test_agent_commands_handler.py tests/unit/test_agent_sync.py
```

Fix any issues.

- [ ] **Step 2: Run mypy**

```bash
mypy src/dazzle/cli/agent_commands/ --ignore-missing-imports
```

Fix any type errors.

- [ ] **Step 3: Run all new tests**

```bash
pytest tests/unit/test_agent_command_models.py tests/unit/test_agent_commands_handler.py tests/unit/test_agent_sync.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Run full test suite to check for regressions**

```bash
pytest tests/ -m "not e2e" -x --timeout=120
```

Expected: No regressions

- [ ] **Step 5: Commit any lint/type fixes**

```bash
git add -u
git commit -m "chore: lint and type fixes for agent-commands"
```

- [ ] **Step 6: Update CHANGELOG.md**

Add under `## [Unreleased]`:

```markdown
### Added
- Agent-first development commands: `/improve`, `/qa`, `/spec-sync`, `/ship`, `/polish`, `/issues`
- `dazzle agent sync` CLI command to install/update commands in user projects
- MCP `agent_commands` tool (list, get, check_updates) for runtime discovery
- `AGENTS.md` cross-tool convention file generation
- Agent Tool Convention for backlog/log patterns in `agent/` directory
- Bootstrap integration nudges agents to install commands on new projects

### Agent Guidance
- New projects should run `dazzle agent sync` after first successful `dazzle validate`
- Agent commands track state in `agent/` (git-tracked backlogs and logs)
- Session-start: check `mcp__dazzle__agent_commands operation=check_updates` for new capabilities
- See `docs/superpowers/specs/2026-04-16-agent-commands-design.md` for full design
```

- [ ] **Step 7: Final commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add agent-commands to CHANGELOG"
```
