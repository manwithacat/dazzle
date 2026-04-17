"""`dazzle coverage` — framework-artefact coverage audit.

Enumerates what the framework ships (DSL constructs, DisplayModes,
workspace region templates, standalone fragment templates) versus
what example apps in ``examples/*`` actually exercise. An uncovered
artefact is one the framework ships but no example renders — which
means no QA run exercises its template, and any regression in it is
invisible until a consumer hits it in production.

The classic case: ``display: grid`` shipped a full region template
plus the ``region_card`` macro wrapper but no example app used it,
so the nested-card-chrome regression stayed hidden (issue #794 +
follow-up). This command makes that class of gap visible and
closable, one artefact at a time.

Exit codes
----------
- 0: every tracked artefact has at least one example-app consumer.
- 1: at least one uncovered artefact (CI-gate mode).

Usage
-----
    dazzle coverage            # human report
    dazzle coverage --json     # machine-readable matrix
    dazzle coverage --fail-on-uncovered   # CI gate
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer

from dazzle.core.ir.workspaces import DisplayMode

# ---------------------------------------------------------------------------
# Curated inventories
# ---------------------------------------------------------------------------

# Top-level DSL constructs. Kept explicit so the command stays stable
# under parser refactors. If a new construct is added to the DSL, add
# it here — CI will then fail until at least one example uses it.
# Note: includes only top-level, column-0 dispatchable keywords. Sub-
# keywords (``view``, ``graph_edge``, ``graph_node``) are deliberately
# excluded — they appear nested inside other constructs and are covered
# transitively when their parent is exercised.
_DSL_CONSTRUCTS: tuple[str, ...] = (
    "app",
    "entity",
    "surface",
    "workspace",
    "persona",
    "enum",
    "webhook",
    "approval",
    "sla",
    "rhythm",
    "process",
    "ledger",
    "transaction",
    "schedule",
    "story",
    "archetype",
    "scenario",
    "service",
    "integration",
    "foreign_model",
    "feedback_widget",
    "island",
    "experience",
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CategoryCoverage:
    """Coverage matrix for a single artefact category."""

    name: str
    description: str
    # Mapping of artefact name → list of example apps using it (empty =
    # uncovered).
    coverage: dict[str, list[str]] = field(default_factory=dict)

    @property
    def covered(self) -> list[str]:
        return sorted(k for k, v in self.coverage.items() if v)

    @property
    def uncovered(self) -> list[str]:
        return sorted(k for k, v in self.coverage.items() if not v)

    @property
    def percent(self) -> float:
        if not self.coverage:
            return 100.0
        return 100.0 * len(self.covered) / len(self.coverage)


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def _find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` looking for ``pyproject.toml`` + ``examples/``."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "examples").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate Dazzle repo root (expected pyproject.toml + examples/)."
    )


def _example_app_dirs(repo_root: Path) -> list[Path]:
    return sorted(
        d
        for d in (repo_root / "examples").iterdir()
        if d.is_dir() and (d / "dazzle.toml").is_file()
    )


def _strip_dsl_comments(text: str) -> str:
    """Remove ``#`` comments from DSL text before artefact matching.

    Without this the coverage collector would falsely count a commented-
    out ``display: map`` as "covered." Comments can appear mid-line
    (``display: list  # TODO review``) so we strip everything from the
    first unquoted ``#`` to end-of-line. Quoted strings are preserved
    so that ``description: "uses #1 format"`` isn't truncated.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        in_quote: str | None = None
        out_chars: list[str] = []
        for ch in line:
            if in_quote:
                out_chars.append(ch)
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in ('"', "'"):
                in_quote = ch
                out_chars.append(ch)
                continue
            if ch == "#":
                break
            out_chars.append(ch)
        out_lines.append("".join(out_chars))
    return "\n".join(out_lines)


def _read_all_dsl(app_dir: Path) -> str:
    """Concatenate every .dsl file under ``app_dir/dsl/``, comment-stripped."""
    dsl_dir = app_dir / "dsl"
    if not dsl_dir.is_dir():
        return ""
    return "\n".join(_strip_dsl_comments(p.read_text()) for p in dsl_dir.glob("*.dsl"))


def _display_mode_coverage(repo_root: Path) -> CategoryCoverage:
    """Which DisplayMode values appear as ``display:`` in example DSL."""
    cat = CategoryCoverage(
        name="display_modes",
        description=(
            "Workspace region display modes from DisplayMode enum. Each value "
            "has a corresponding template in workspace/regions/ that must be "
            "rendered by at least one example to be QA-visible."
        ),
    )
    all_modes = [m.value for m in DisplayMode]
    cat.coverage = {m: [] for m in all_modes}
    pattern = re.compile(r"\bdisplay:\s*([a-z_]+)")
    for app in _example_app_dirs(repo_root):
        text = _read_all_dsl(app)
        seen = {m.group(1) for m in pattern.finditer(text)}
        for m in seen:
            if m in cat.coverage:
                cat.coverage[m].append(app.name)
    return cat


def _dsl_construct_coverage(repo_root: Path) -> CategoryCoverage:
    """Which top-level DSL constructs appear in example DSL."""
    cat = CategoryCoverage(
        name="dsl_constructs",
        description=(
            "Top-level DSL keywords (entity, surface, workspace, ledger, …). "
            "A construct with zero example coverage is a latent integration "
            "gap — parser, linker, runtime, and MCP tools all have code paths "
            "that are never exercised in the canonical QA loop."
        ),
    )
    cat.coverage = {c: [] for c in _DSL_CONSTRUCTS}
    for app in _example_app_dirs(repo_root):
        text = _read_all_dsl(app)
        for construct in _DSL_CONSTRUCTS:
            # Top-level: keyword at column 0, followed by space or colon.
            # Matches ``entity Task "Task":``, ``enum Status:``, and
            # config-style blocks like ``feedback_widget: enabled``.
            if re.search(rf"(?m)^{re.escape(construct)}[ :]", text):
                cat.coverage[construct].append(app.name)
    return cat


def _fragment_template_coverage(repo_root: Path) -> CategoryCoverage:
    """Which fragment templates are included somewhere under src/dazzle_ui/.

    Orphan fragments (no include site) can't possibly be rendered, so
    any regression in them is invisible until someone hand-includes.
    """
    cat = CategoryCoverage(
        name="fragment_templates",
        description=(
            "Standalone fragment templates in src/dazzle_ui/templates/fragments/ "
            "that the framework actively renders. A fragment with no include "
            "site in any template or Python renderer is dead code. Parking-lot "
            "primitives (see fragment_registry.PARKING_LOT_FRAGMENTS) are "
            "excluded — they're registered for downstream opt-in but have no "
            "runtime caller, so they're not counted against the gate."
        ),
    )
    frag_dir = repo_root / "src" / "dazzle_ui" / "templates" / "fragments"
    if not frag_dir.is_dir():
        return cat
    # Fragments can be included by any template (dazzle_ui) or rendered
    # directly by any Python handler (dazzle_ui, dazzle_back, dazzle).
    # Scan all three roots — a fragment rendered by a route is every bit
    # as "covered" as one included in a template.
    search_roots = [
        repo_root / "src" / "dazzle_ui",
        repo_root / "src" / "dazzle_back",
        repo_root / "src" / "dazzle",
    ]
    # The registry file enumerates fragments — it lists them but doesn't
    # render them, so its mention is not evidence of coverage. Exclude
    # it from the scan so only real template includes and real Python
    # render calls count.
    registry_path = repo_root / "src" / "dazzle_ui" / "runtime" / "fragment_registry.py"
    # Parking-lot primitives (see fragment_registry.PARKING_LOT_FRAGMENTS)
    # are framework-shipped but intentionally opt-in — no runtime caller
    # by default. Skip them from the coverage denominator so the metric
    # reflects only fragments the framework actually renders.
    try:
        from dazzle_ui.runtime.fragment_registry import PARKING_LOT_FRAGMENTS
    except ImportError:
        PARKING_LOT_FRAGMENTS = frozenset()
    all_fragments = sorted(p.stem for p in frag_dir.glob("*.html"))
    fragments = [f for f in all_fragments if f not in PARKING_LOT_FRAGMENTS]
    cat.coverage = {f: [] for f in fragments}
    for frag in fragments:
        include_pattern = re.compile(rf"fragments/{re.escape(frag)}(?:\.html)?\b")
        for root in search_roots:
            if not root.is_dir():
                continue
            found = False
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix not in (".html", ".py"):
                    continue
                if path == frag_dir / f"{frag}.html":
                    continue
                # Skip the fragment registry — its mention is enumeration,
                # not rendering.
                if path == registry_path:
                    continue
                try:
                    if include_pattern.search(path.read_text()):
                        cat.coverage[frag].append(path.relative_to(repo_root).as_posix())
                        found = True
                        break
                except (OSError, UnicodeDecodeError):
                    continue
            if found:
                break
    return cat


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_human(cats: list[CategoryCoverage]) -> str:
    lines: list[str] = []
    lines.append("Framework artefact coverage")
    lines.append("=" * 60)
    total_items = sum(len(c.coverage) for c in cats)
    total_covered = sum(len(c.covered) for c in cats)
    lines.append(
        f"Overall: {total_covered}/{total_items} "
        f"({100.0 * total_covered / max(total_items, 1):.0f}%)"
    )
    lines.append("")
    for cat in cats:
        lines.append(
            f"## {cat.name}  —  {len(cat.covered)}/{len(cat.coverage)} ({cat.percent:.0f}%)"
        )
        lines.append(f"   {cat.description}")
        if cat.uncovered:
            lines.append("   UNCOVERED:")
            for item in cat.uncovered:
                lines.append(f"     - {item}")
        lines.append("")
    return "\n".join(lines)


def _render_json(cats: list[CategoryCoverage]) -> str:
    payload: dict[str, Any] = {}
    for cat in cats:
        payload[cat.name] = {
            "description": cat.description,
            "percent": round(cat.percent, 1),
            "covered": {item: cat.coverage[item] for item in cat.covered},
            "uncovered": cat.uncovered,
        }
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def coverage_command(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    fail_on_uncovered: bool = typer.Option(
        False,
        "--fail-on-uncovered",
        help="Exit with code 1 if any tracked artefact is uncovered (CI gate mode).",
    ),
) -> None:
    """Audit framework-artefact coverage across example apps.

    Every artefact the framework ships (DSL construct, DisplayMode,
    fragment template) must be rendered by at least one example —
    otherwise no QA run exercises it and regressions are invisible.
    """
    repo_root = _find_repo_root()
    cats = [
        _display_mode_coverage(repo_root),
        _dsl_construct_coverage(repo_root),
        _fragment_template_coverage(repo_root),
    ]
    if json_output:
        typer.echo(_render_json(cats))
    else:
        typer.echo(_render_human(cats))

    if fail_on_uncovered and any(cat.uncovered for cat in cats):
        raise typer.Exit(code=1)
