"""Gates that catch documentation drift from the parser/codebase.

Each test here asserts a one-directional invariant: the doc claims X
exists, and X must still exist in the parser. When the parser changes
and a doc lies as a result, the test fails with a message pointing
at the stale line.

The backlog post-mortem for #794 surfaced this gap: coverage curation
revealed that `CLAUDE.md` named `view`, `graph_edge`, and `graph_node`
as top-level DSL constructs when they're actually sub-keywords. Cost:
one `/improve` cycle spent disproving each.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _agents_md_constructs() -> list[str]:
    """Parse the ``**Constructs**:`` line from AGENTS.md.

    Accepts backtick-quoted names on the same line — the canonical
    quick-reference format. Returns them in order of appearance.
    """
    text = (REPO_ROOT / "AGENTS.md").read_text()
    match = re.search(r"\*\*Constructs\*\*:(.+)", text)
    assert match, "AGENTS.md no longer has a `**Constructs**:` line"
    line = match.group(1)
    # Also absorb the parenthetical extended list that follows — it
    # names additional parser-dispatchable keywords for reference, and
    # those must also resolve (the drift test is one-way: everything
    # the doc names must exist).
    following = text.split(match.group(0), 1)[1].split("\n\n", 1)[0]
    combined = line + "\n" + following
    return [m.group(1) for m in re.finditer(r"`([a-z_]+)`", combined)]


def _parser_top_level_keywords() -> set[str]:
    """Extract the set of top-level dispatchable keywords from the
    parser's dispatch table in ``src/dazzle/core/dsl_parser_impl/__init__.py``.

    Match lines of the form ``TokenType.FOO: self._dispatch_foo,`` —
    that's the authoritative list because a keyword is only a top-level
    construct iff it has a dispatch entry there. The TokenType enum in
    ``lexer.py`` has members for sub-keywords too, but those aren't
    dispatched.
    """
    text = (REPO_ROOT / "src" / "dazzle" / "core" / "dsl_parser_impl" / "__init__.py").read_text()
    # "TokenType.FOO: self._dispatch_bar," — take the _dispatch_<name>
    # suffix rather than the enum name so the test tracks the keyword
    # as the user types it in DSL (e.g. TokenType.QUESTION_DECL →
    # _dispatch_question, keyword is `question`).
    method_names = re.findall(r"TokenType\.[A-Z_]+:\s*self\._dispatch_([a-z_]+)", text)
    # Also include the `app` keyword — it's parsed by the module-header
    # path in base.py, not via the dispatch dict, but it IS a top-level
    # construct that users type at column 0.
    return set(method_names) | {"app"}


def test_agents_md_constructs_all_exist_in_parser() -> None:
    """Every DSL construct named in AGENTS.md must exist in the parser.

    This is a one-way gate: the parser can dispatch on more constructs
    than AGENTS.md mentions (AGENTS.md curates the user-facing subset).
    But any name AGENTS.md lists must actually be a real top-level
    keyword — otherwise the doc is lying.
    """
    claimed = _agents_md_constructs()
    real = _parser_top_level_keywords()
    # Exclude `question` because the parser dispatch method is named
    # `_dispatch_question` but the keyword in the DSL is the token
    # `question_decl`. If CLAUDE.md writes `question` or `question_decl`
    # here, both are legal — we allow either to resolve.
    hidden = {"question_decl"}

    stale = [name for name in claimed if name not in real and name not in hidden]
    assert not stale, (
        f"AGENTS.md names {stale!r} as DSL constructs, but the parser "
        f"does not dispatch on them as top-level keywords. Either:\n"
        f"  (a) remove the stale name(s) from the AGENTS.md "
        f"`**Constructs**:` line, OR\n"
        f"  (b) add a parser dispatch entry in "
        f"src/dazzle/core/dsl_parser_impl/__init__.py.\n"
        f"Parser's real top-level set: {sorted(real)}"
    )


def _agents_md_mcp_table() -> dict[str, str]:
    """Parse the ``### MCP Tools`` table from AGENTS.md.

    Returns {tool_name: operations_cell_text} for every data row.
    """
    text = (REPO_ROOT / "AGENTS.md").read_text()
    section = text.split("### MCP Tools", 1)
    assert len(section) == 2, "AGENTS.md no longer has a `### MCP Tools` section"
    rows = {}
    for line in section[1].splitlines():
        m = re.match(r"\|\s*`([a-z0-9_]+)`\s*\|\s*(.+?)\s*\|\s*$", line)
        if m:
            rows[m.group(1)] = m.group(2)
        elif rows and line.strip() and not line.startswith("|"):
            break  # table ended
    assert rows, "AGENTS.md `### MCP Tools` table has no parseable rows"
    return rows


def test_agents_md_mcp_tools_table_matches_registry() -> None:
    """The AGENTS.md MCP tools table must match the live registry exactly.

    #1369 post-mortem: the hand-maintained table silently rotted to 26 of
    34 tools, ~12 stale op lists, and a phantom `llm ask` op that never
    existed — while the same file instructed agents to call a
    `knowledge counter_prior` op the table didn't list. Two-way gate:
    same tool names, and per-tool the listed ops must equal the
    `operation` enum in the tool's input schema. Tools without an
    operation enum (e.g. `bootstrap`) keep a prose cell, unchecked.
    """
    from unittest.mock import patch

    from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

    # The table documents the consolidated (non-dev) tool set. is_dev_mode()
    # reads a process-global that any earlier in-process MCP state init flips
    # to True when the working dir is this repo (a dev environment) — under
    # xdist that made this gate scheduling-dependent: the registry grew the
    # dev-mode `project` tool on whichever worker ran such a test first
    # (failed the py3.14 cell on v0.92.81). Pin dev mode off for the read.
    with patch("dazzle.mcp.server.tools_consolidated.is_dev_mode", return_value=False):
        registry = {t.name: t for t in get_all_consolidated_tools()}
    table = _agents_md_mcp_table()

    missing = sorted(set(registry) - set(table))
    phantom = sorted(set(table) - set(registry))
    assert not missing and not phantom, (
        f"AGENTS.md `### MCP Tools` table drifted from the registry.\n"
        f"  Tools missing from the table: {missing}\n"
        f"  Table rows with no registry tool: {phantom}\n"
        f"Regenerate the row(s) from "
        f"dazzle.mcp.server.tools_consolidated.get_all_consolidated_tools()."
    )

    stale_ops = []
    for name, tool in registry.items():
        enum = (tool.inputSchema or {}).get("properties", {}).get("operation", {}).get("enum")
        if not enum:
            continue
        listed = {op.strip() for op in table[name].split(",")}
        if listed != set(enum):
            stale_ops.append(
                f"  {name}: table says {sorted(listed)}, registry enum is {sorted(enum)}"
            )
    assert not stale_ops, (
        "AGENTS.md MCP tools table op lists drifted from the registry "
        "operation enums:\n" + "\n".join(stale_ops)
    )


def _backticked_dir_names(line: str) -> set[str]:
    """Backticked tokens that look like directory names (no path parts)."""
    return {m.group(1) for m in re.finditer(r"`([a-z0-9_]+)`", line)}


def test_agents_md_examples_and_fixtures_lists_match_disk() -> None:
    """The Examples section's two lists must match the directory trees.

    Two-way: every directory must be listed, every listed name must be a
    directory. Pre-#1369 the examples line lagged 3 apps and the fixtures
    line lagged 5 probes behind disk.
    """
    text = (REPO_ROOT / "AGENTS.md").read_text()
    for label, prefix, root in (
        ("examples", "Working Dazzle apps in `examples/`:", REPO_ROOT / "examples"),
        ("fixtures", "Framework-validation fixtures in `fixtures/`", REPO_ROOT / "fixtures"),
    ):
        line = next((ln for ln in text.splitlines() if ln.startswith(prefix)), None)
        assert line, f"AGENTS.md no longer has the {label} list line (prefix: {prefix!r})"
        # Strip the lead-in (and the fixtures parenthetical lead-in) so only
        # the name list is scanned; path-bearing tokens never match the
        # directory-name pattern.
        names = _backticked_dir_names(line.split(":", 1)[1])
        on_disk = {p.name for p in root.iterdir() if p.is_dir()}
        unlisted = sorted(on_disk - names)
        ghosts = sorted(names - on_disk)
        assert not unlisted and not ghosts, (
            f"AGENTS.md {label} list drifted from {root.name}/:\n"
            f"  on disk but not listed: {unlisted}\n"
            f"  listed but no directory: {ghosts}"
        )


def test_every_reference_page_is_linked_from_index() -> None:
    """Every docs/reference/*.md must be linked from the generated index.

    #1372: index.md is auto-generated from doc_pages.toml, so ~29 hand-written
    pages could never appear in it and were undiscoverable. Hand-written pages
    are now registered in doc_pages.toml with `handwritten = true` (linked,
    never overwritten). This gate makes a new orphaned reference page a CI
    failure — register it in doc_pages.toml (handwritten pages) or it won't be
    discoverable from the index.
    """
    ref_dir = REPO_ROOT / "docs" / "reference"
    index = (ref_dir / "index.md").read_text()
    linked = set(re.findall(r"\(([a-z0-9-]+)\.md\)", index))
    on_disk = {p.stem for p in ref_dir.glob("*.md")} - {"index"}
    orphaned = sorted(on_disk - linked)
    assert not orphaned, (
        "Reference pages exist on disk but aren't linked from "
        "docs/reference/index.md:\n  "
        + "\n  ".join(orphaned)
        + "\nRegister each in src/dazzle/mcp/semantics_kb/doc_pages.toml "
        "(add `handwritten = true` for hand-written pages) and run "
        "`dazzle docs generate`."
    )


def _cli_group_names() -> set[str]:
    """Registered CLI command-group names (every `add_typer(..., name=...)`)."""
    text = (REPO_ROOT / "src" / "dazzle" / "cli" / "__init__.py").read_text()
    return set(re.findall(r'add_typer\([a-z_]+_app,\s*name="([a-z0-9-]+)"', text))


def test_cli_md_documents_every_command_group() -> None:
    """Every registered CLI command group must be named in cli.md.

    #1372: cli.md was hand-maintained with no gate, so 45 of the registered
    Typer sub-apps were never documented. This gate asserts each group name
    appears in the CLI reference; the canonical list is the "Command Groups"
    table.
    """
    groups = _cli_group_names()
    assert groups, "no add_typer(name=...) groups found — parser drift?"
    cli_md = (REPO_ROOT / "docs" / "reference" / "cli.md").read_text()
    missing = sorted(
        g for g in groups if f"dazzle {g}`" not in cli_md and f"`dazzle {g}`" not in cli_md
    )
    assert not missing, (
        "CLI command groups registered in src/dazzle/cli/__init__.py but not "
        "documented in docs/reference/cli.md:\n  "
        + "\n  ".join(missing)
        + "\nAdd a row to the `## Command Groups` table."
    )


def test_coverage_tool_constructs_all_exist_in_parser() -> None:
    """The curated list in dazzle.cli.coverage._DSL_CONSTRUCTS (which
    feeds the ``dazzle coverage --fail-on-uncovered`` CI gate) must
    also be a subset of the parser's real dispatch table. Otherwise
    the coverage gate would chase a ghost keyword nobody can render.
    """
    from dazzle.cli.coverage import _DSL_CONSTRUCTS

    real = _parser_top_level_keywords()
    stale = [name for name in _DSL_CONSTRUCTS if name not in real]
    assert not stale, (
        f"coverage.py names {stale!r} in _DSL_CONSTRUCTS but the parser "
        f"doesn't dispatch on them. Remove them from coverage.py or "
        f"add parser dispatches."
    )


def test_generated_reference_pages_match_disk() -> None:
    """#1534 — the auto-generated reference pages must be byte-identical
    to a fresh `dazzle docs generate`. Hand-edits to generated pages get
    silently deleted on the next regeneration (three sections were lost
    that way); content belongs in the semantics-KB TOML sources. On
    drift: move your edit into `src/dazzle/mcp/semantics_kb/*.toml` and
    run `dazzle docs generate`.
    """
    pytest.importorskip("mcp")
    import json
    import subprocess
    import sys

    # A SUBPROCESS, not an in-process call: the mcp tool registry is
    # process-global and other tests in the same xdist worker mutate it
    # (the CLAUDE.md mcp-isolation gotcha) — an in-process regeneration
    # of the auto-source mcp-tools page drifts nondeterministically.
    script = (
        "import json, dazzle.mcp.server.docs_inventory;"
        "from dazzle.core.docs_gen import generate_reference_docs;"
        "print(json.dumps(generate_reference_docs()))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    generated: dict[str, str] = json.loads(proc.stdout)

    docs_dir = REPO_ROOT / "docs" / "reference"
    stale: list[str] = []
    for slug, content in generated.items():
        on_disk = (docs_dir / f"{slug}.md").read_text(encoding="utf-8")
        if on_disk != content:
            stale.append(slug)
    assert not stale, (
        f"generated reference pages drifted from disk: {stale} — hand-edits to "
        "auto-generated pages are deleted on regeneration; move the content into "
        "src/dazzle/mcp/semantics_kb/*.toml and run `dazzle docs generate`"
    )
