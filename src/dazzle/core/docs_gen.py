"""
Documentation generator for the DAZZLE DSL reference.

Reads concept and pattern definitions from the semantics knowledge base
(TOML files) and produces markdown reference documentation grouped by
doc page.

Usage:
    python -m dazzle.core.docs_gen           # print to stdout
    dazzle docs generate                     # write docs/reference/
"""

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KB_DIR = Path(__file__).parent.parent / "mcp" / "semantics_kb"


def _project_docs_dir() -> Path:
    """Resolve docs/reference/ relative to CWD (project root), not package dir."""
    return Path.cwd() / "docs" / "reference"


def _project_readme_path() -> Path:
    """Resolve README.md relative to CWD (project root), not package dir."""
    return Path.cwd() / "README.md"


_HEADER = (
    "> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.\n"
    "> Do not edit manually; run `dazzle docs generate` to regenerate."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_concepts(kb_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load all concepts and patterns from TOML files.

    Reads every ``*.toml`` in *kb_dir* (except ``doc_pages.toml``).
    For ``[concepts.X]`` entries, returns them as-is.
    For ``[patterns.X]`` entries, adds ``source="patterns"`` to each.
    Returns flat dict of name -> info.
    """
    kb = kb_dir or _KB_DIR
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(kb.glob("*.toml")):
        if path.name == "doc_pages.toml":
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for name, info in data.get("concepts", {}).items():
            result[name] = dict(info)
        for name, info in data.get("patterns", {}).items():
            entry = dict(info)
            entry["source"] = "patterns"
            result[name] = entry
    return result


def load_page_metadata(pages_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load page definitions from ``doc_pages.toml``.

    Returns dict of slug -> {title, slug, order, intro}.
    """
    path = pages_path or (_KB_DIR / "doc_pages.toml")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for slug, page in data.get("pages", {}).items():
        result[slug] = dict(page)
    return result


def generate_reference_docs(kb_dir: Path | None = None) -> dict[str, str]:
    """Generate all reference doc pages as markdown.

    Returns dict of slug -> markdown_content.
    Includes an ``"index"`` key for the index page.
    """
    kb = kb_dir or _KB_DIR
    all_concepts = load_concepts(kb)
    pages = load_page_metadata(kb / "doc_pages.toml")

    # Group concepts by doc_page
    by_page: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for name, info in all_concepts.items():
        dp = info.get("doc_page")
        if dp:
            by_page.setdefault(dp, []).append((name, info))

    # Sort each page's concepts by doc_order then name
    for slug in by_page:
        by_page[slug].sort(key=lambda pair: (pair[1].get("doc_order", 999), pair[0]))

    result: dict[str, str] = {}
    for slug, page_meta in sorted(pages.items(), key=lambda p: p[1].get("order", 999)):
        # Hand-written pages are registered in doc_pages.toml only so the
        # generated index links them — the generator must NOT render/overwrite
        # their on-disk content. (#1372: the naive "just link them" fix would
        # be silently reverted by `dazzle docs generate`.)
        if page_meta.get("handwritten"):
            continue
        concepts = by_page.get(slug, [])
        # Exactly one trailing newline — the repo's end-of-file-fixer
        # hook normalises committed files the same way, so the generator
        # and the hook never tug-of-war (#1534 drift gate).
        result[slug] = _render_page(slug, page_meta, concepts, all_concepts).rstrip("\n") + "\n"

    result["index"] = _render_index(pages)
    return result


def write_reference_docs(output_dir: Path | None = None) -> list[Path]:
    """Write reference docs to disk. Returns list of paths written."""
    out = output_dir or _project_docs_dir()
    out.mkdir(parents=True, exist_ok=True)
    docs = generate_reference_docs()
    paths: list[Path] = []
    for slug, content in docs.items():
        p = out / f"{slug}.md"
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


def check_docs_coverage(kb_dir: Path | None = None) -> list[str]:
    """Check for coverage issues. Returns list of issue strings.

    Each issue starts with ``"ERROR: "`` or ``"WARNING: "``.

    Errors:
    - doc_page value not in doc_pages.toml
    - Page in doc_pages.toml with no concepts

    Warnings:
    - Concept without doc_page field
    - Concept with empty definition
    """
    kb = kb_dir or _KB_DIR
    all_concepts = load_concepts(kb)
    pages = load_page_metadata(kb / "doc_pages.toml")
    issues: list[str] = []

    pages_with_concepts: set[str] = set()
    for name, info in all_concepts.items():
        dp = info.get("doc_page")
        if not dp:
            issues.append(f"WARNING: Concept '{name}' has no doc_page field")
            continue
        if dp not in pages:
            issues.append(
                f"ERROR: Concept '{name}' references doc_page '{dp}' which is not in doc_pages.toml"
            )
        else:
            pages_with_concepts.add(dp)
        # Check definition — patterns may use 'description' instead
        defn = info.get("definition", "").strip()
        desc = info.get("description", "").strip()
        if not defn and not desc:
            issues.append(f"WARNING: Concept '{name}' has empty definition")

    for slug, page_meta in pages.items():
        if slug in pages_with_concepts:
            continue
        # Prose pages (those with a non-empty `body`) are exempt — their content
        # lives in doc_pages.toml directly, not in per-concept TOML entries.
        if (page_meta.get("body") or "").strip():
            continue
        # Auto-source pages introspect code at build time (e.g. the MCP tool
        # registry). They're allowed to have no concept entries.
        if (page_meta.get("auto_source") or "").strip():
            continue
        # Hand-written pages own their content on disk; they're registered only
        # for index linking and never sourced from concept TOML entries (#1372).
        if page_meta.get("handwritten"):
            continue
        issues.append(f"ERROR: Page '{slug}' in doc_pages.toml has no concepts")

    return issues


def inject_readme_feature_table(readme_path: Path | None = None) -> bool:
    """Inject feature table between markers in README.md.

    Looks for ``<!-- BEGIN FEATURE TABLE -->`` and
    ``<!-- END FEATURE TABLE -->`` markers. Replaces content between
    them with a markdown table of pages.
    Returns ``True`` if README was modified, ``False`` if markers not found.
    """
    path = readme_path or _project_readme_path()
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    begin = "<!-- BEGIN FEATURE TABLE -->"
    end = "<!-- END FEATURE TABLE -->"
    i_begin = text.find(begin)
    i_end = text.find(end)
    if i_begin == -1 or i_end == -1:
        return False

    pages = load_page_metadata()
    table = _render_feature_table(pages)
    new_text = text[: i_begin + len(begin)] + "\n" + table + "\n" + text[i_end:]
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _concept_title(name: str) -> str:
    """Convert concept_name to 'Concept Name'."""
    return name.replace("_", " ").title()


def _concept_anchor(name: str) -> str:
    """Convert concept_name to kebab-case anchor: 'concept-name'."""
    return name.replace("_", "-").lower()


def _get_best_practices(info: dict[str, Any]) -> list[str]:
    """Extract best_practices list from a concept info dict.

    Handles both ``best_practices = [...]`` (list) and
    ``[concepts.X.best_practices] tips = [...]`` (nested dict).
    """
    bp = info.get("best_practices")
    if bp is None:
        return []
    if isinstance(bp, list):
        return bp
    if isinstance(bp, dict):
        return list(bp.get("tips", []))
    return []


def _get_definition(info: dict[str, Any]) -> str:
    """Get the definition text, falling back to description for patterns."""
    defn: str = info.get("definition", "")
    defn = defn.strip()
    if defn:
        return defn
    desc: str = info.get("description", "")
    return desc.strip()


def _render_concept(
    name: str, info: dict[str, Any], all_concepts: dict[str, dict[str, Any]]
) -> str:
    """Render a single concept as markdown."""
    lines: list[str] = []
    title = _concept_title(name)
    lines.append(f"## {title}")
    lines.append("")

    definition = _get_definition(info)
    if definition:
        lines.append(definition)
        lines.append("")

    # Syntax
    syntax = info.get("syntax", "").strip()
    if syntax:
        lines.append("### Syntax")
        lines.append("")
        lines.append("```dsl")
        lines.append(syntax)
        lines.append("```")
        lines.append("")

    # Example
    example = info.get("example", "").strip()
    if example:
        lines.append("### Example")
        lines.append("")
        lines.append("```dsl")
        lines.append(example)
        lines.append("```")
        lines.append("")

    # Best Practices
    bp_list = _get_best_practices(info)
    if bp_list:
        lines.append("### Best Practices")
        lines.append("")
        for bp in bp_list:
            lines.append(f"- {bp}")
        lines.append("")

    # Related
    related = info.get("related", [])
    if related:
        rendered: list[str] = []
        for rel_name in related:
            rel_info = all_concepts.get(rel_name)
            rel_title = _concept_title(rel_name)
            if rel_info and rel_info.get("doc_page"):
                rel_page = rel_info["doc_page"]
                rel_anchor = _concept_anchor(rel_name)
                rendered.append(f"[{rel_title}]({rel_page}.md#{rel_anchor})")
            else:
                rendered.append(rel_title)
        lines.append(f"**Related:** {', '.join(rendered)}")
        lines.append("")

    return "\n".join(lines)


def _render_page(
    slug: str,
    page_meta: dict[str, Any],
    concepts: list[tuple[str, dict[str, Any]]],
    all_concepts: dict[str, dict[str, Any]],
) -> str:
    """Render a single reference doc page.

    Three page shapes are supported, dispatched in this order:

      1. Auto-source page — if doc_pages.toml carries an ``auto_source`` field,
         the page body is generated by introspecting code at build time. Used for
         live inventories (e.g. ``auto_source = "mcp_tools"`` reflects the live
         MCP tool registry). The intro from doc_pages.toml goes above the
         generated content; concept assembly is skipped.

      2. Prose page — if doc_pages.toml carries a non-empty ``body`` field for the
         page, the body is rendered verbatim after the intro. Concept rendering is
         skipped. Use when the page is largely flowing explanation, tables, and
         worked examples rather than a catalogue of constructs.

      3. Concept-assembled (default) — concepts in semantics_kb/*.toml carrying a
         matching ``doc_page`` field are rendered in ``doc_order`` then alphabetical.
         The intro from doc_pages.toml goes above the assembled concepts.
    """
    lines: list[str] = []
    title = page_meta.get("title", _concept_title(slug))
    intro = page_meta.get("intro", "").strip()
    body = page_meta.get("body", "").strip()
    auto_source = page_meta.get("auto_source", "").strip()

    lines.append(f"# {title}")
    lines.append("")
    lines.append(_HEADER)
    lines.append("")
    if intro:
        lines.append(intro)
        lines.append("")

    if auto_source:
        generated = _generate_auto_source(auto_source)
        lines.append(generated)
        lines.append("")
        return "\n".join(lines)

    if body:
        lines.append(body)
        lines.append("")
        return "\n".join(lines)

    lines.append("---")
    lines.append("")

    for name, info in concepts:
        lines.append(_render_concept(name, info, all_concepts))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


_AUTO_SOURCE_GENERATORS: dict[str, Callable[[], str]] = {}


def register_auto_source(name: str, generator: Callable[[], str]) -> None:
    """Register a live-inventory generator for an ``auto_source`` doc page.

    Layers above core (e.g. ``dazzle.mcp``) register here — at import time of
    their inventory module — so core never imports them. Keeps the core→mcp
    isolation boundary clean (smells check 1.3).
    """
    _AUTO_SOURCE_GENERATORS[name] = generator


def _generate_auto_source(source: str) -> str:
    """Generate body content for an auto-source page via the registry."""
    generator = _AUTO_SOURCE_GENERATORS.get(source)
    if generator is None:
        raise ValueError(
            f"Unknown auto_source {source!r}. Register it via "
            "docs_gen.register_auto_source(...) (e.g. dazzle.mcp.server.docs_inventory) "
            "or fix the doc_pages.toml entry."
        )
    return generator()


def render_mcp_tools_inventory(tools: list[Any]) -> str:
    """Render the MCP tool inventory page from a list of tool objects.

    The mcp layer owns the registry and supplies ``tools``; core only renders.
    Registered as the ``mcp_tools`` auto-source from
    ``dazzle.mcp.server.docs_inventory`` so core never imports ``dazzle.mcp``.
    """
    tools = sorted(tools, key=lambda t: t.name)
    total_ops = 0
    lines: list[str] = []

    # Header tally — recomputed every build, never hand-edited.
    for tool in tools:
        ops = _extract_operations(tool.inputSchema)
        total_ops += len(ops)

    lines.append(
        f"**Live count:** {len(tools)} tools, {total_ops} operations. "
        "Regenerated from the registry every time `dazzle docs generate` runs."
    )
    lines.append("")
    lines.append(
        "Each tool is a single MCP entry point that dispatches on the `operation` "
        "argument. The Bootstrap tool (`bootstrap`) is the exception — it takes "
        "free-form spec text, not an operation enum, and is the canonical entry "
        'point for "build me an app" requests.'
    )
    lines.append("")
    lines.append("## Tool index")
    lines.append("")
    lines.append("| Tool | Operations | Summary |")
    lines.append("|------|------------|---------|")
    for tool in tools:
        ops = _extract_operations(tool.inputSchema)
        op_count = f"{len(ops)}" if ops else "—"
        summary = _first_sentence(tool.description or "").rstrip(".")
        # mkdocs's default slugify lowercases and keeps underscores when they
        # appear inside an identifier. Backticks are stripped. The result is
        # the tool name verbatim.
        anchor = tool.name
        lines.append(f"| [`{tool.name}`](#{anchor}) | {op_count} | {summary} |")
    lines.append("")
    lines.append("## Per-tool detail")
    lines.append("")

    for tool in tools:
        lines.append(f"### `{tool.name}`")
        lines.append("")
        desc = (tool.description or "").strip()
        if desc:
            lines.append(desc)
            lines.append("")
        ops = _extract_operations(tool.inputSchema)
        if ops:
            op_str = ", ".join(f"`{op}`" for op in ops)
            lines.append(f"**Operations ({len(ops)}):** {op_str}")
            lines.append("")
        params = _extract_parameters(tool.inputSchema)
        if params:
            lines.append("**Parameters:**")
            lines.append("")
            for param_name, param_info, required in params:
                ptype = param_info.get("type", "any")
                pdesc = (param_info.get("description") or "").strip()
                tag = " *(required)*" if required else ""
                if pdesc:
                    lines.append(f"- `{param_name}` *({ptype})*{tag} — {pdesc}")
                else:
                    lines.append(f"- `{param_name}` *({ptype})*{tag}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _extract_operations(schema: dict[str, Any]) -> list[str]:
    """Extract the operation enum from an MCP tool's input schema."""
    props = schema.get("properties") or {}
    operation = props.get("operation") or {}
    enum = operation.get("enum") or []
    return [str(v) for v in enum]


def _extract_parameters(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any], bool]]:
    """Return (name, info, required) for each schema property.

    The `operation` parameter is omitted — it's covered by the operations list
    above. Parameters are returned in the order they appear in the schema's
    properties dict; required parameters are flagged.
    """
    props = schema.get("properties") or {}
    required: set[str] = set(schema.get("required") or [])
    out: list[tuple[str, dict[str, Any], bool]] = []
    for name, info in props.items():
        if name == "operation":
            continue
        out.append((name, info, name in required))
    return out


def _first_sentence(text: str) -> str:
    """Extract the first sentence from text (up to the first period)."""
    text = text.strip()
    dot = text.find(".")
    if dot == -1:
        return text
    return text[: dot + 1]


def _render_index(pages: dict[str, dict[str, Any]]) -> str:
    """Render the index page."""
    lines: list[str] = []
    lines.append("# DSL Reference")
    lines.append("")
    lines.append("> **Auto-generated** by `docs_gen.py`. Run `dazzle docs generate` to regenerate.")
    lines.append("")
    lines.append("| Section | Description |")
    lines.append("|---------|-------------|")

    sorted_pages = sorted(pages.items(), key=lambda p: p[1].get("order", 999))
    generated = [(s, m) for s, m in sorted_pages if not m.get("handwritten")]
    handwritten = [(s, m) for s, m in sorted_pages if m.get("handwritten")]

    for slug, meta in generated:
        title = meta.get("title", _concept_title(slug))
        desc = _first_sentence(meta.get("intro", "").strip())
        lines.append(f"| [{title}]({slug}.md) | {desc} |")

    # Hand-written guides & operations pages — registered in doc_pages.toml with
    # `handwritten = true` so they're linked here but never overwritten (#1372).
    if handwritten:
        lines.append("")
        lines.append("## Guides & Operations")
        lines.append("")
        lines.append("| Page | Description |")
        lines.append("|------|-------------|")
        for slug, meta in handwritten:
            title = meta.get("title", _concept_title(slug))
            desc = _first_sentence(meta.get("intro", "").strip())
            lines.append(f"| [{title}]({slug}.md) | {desc} |")

    lines.append("")
    return "\n".join(lines)


def _render_feature_table(pages: dict[str, dict[str, Any]]) -> str:
    """Render the feature table for README injection."""
    lines: list[str] = []
    lines.append("| Feature | Description |")
    lines.append("|---------|-------------|")

    sorted_pages = sorted(pages.items(), key=lambda p: p[1].get("order", 999))
    for slug, meta in sorted_pages:
        title = meta.get("title", _concept_title(slug))
        intro = meta.get("intro", "").strip()
        desc = _first_sentence(intro)
        lines.append(f"| [{title}](docs/reference/{slug}.md) | {desc} |")

    return "\n".join(lines)
