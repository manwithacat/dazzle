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
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KB_DIR = Path(__file__).parent.parent / "mcp" / "semantics_kb"
_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "reference"
_README_PATH = Path(__file__).parent.parent.parent.parent / "README.md"

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
        data = tomllib.loads(path.read_text())
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
    data = tomllib.loads(path.read_text())
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
        concepts = by_page.get(slug, [])
        result[slug] = _render_page(slug, page_meta, concepts, all_concepts)

    result["index"] = _render_index(pages)
    return result


def write_reference_docs(output_dir: Path | None = None) -> list[Path]:
    """Write reference docs to disk. Returns list of paths written."""
    out = output_dir or _DOCS_DIR
    out.mkdir(parents=True, exist_ok=True)
    docs = generate_reference_docs()
    paths: list[Path] = []
    for slug, content in docs.items():
        p = out / f"{slug}.md"
        p.write_text(content)
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

    for slug in pages:
        if slug not in pages_with_concepts:
            issues.append(f"ERROR: Page '{slug}' in doc_pages.toml has no concepts")

    return issues


def inject_readme_feature_table(readme_path: Path | None = None) -> bool:
    """Inject feature table between markers in README.md.

    Looks for ``<!-- BEGIN FEATURE TABLE -->`` and
    ``<!-- END FEATURE TABLE -->`` markers. Replaces content between
    them with a markdown table of pages.
    Returns ``True`` if README was modified, ``False`` if markers not found.
    """
    path = readme_path or _README_PATH
    if not path.exists():
        return False
    text = path.read_text()
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
        path.write_text(new_text)
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
    """Render a single reference doc page."""
    lines: list[str] = []
    title = page_meta.get("title", _concept_title(slug))
    intro = page_meta.get("intro", "").strip()

    lines.append(f"# {title}")
    lines.append("")
    lines.append(_HEADER)
    lines.append("")
    if intro:
        lines.append(intro)
        lines.append("")

    lines.append("---")
    lines.append("")

    for name, info in concepts:
        lines.append(_render_concept(name, info, all_concepts))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


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
    for slug, meta in sorted_pages:
        title = meta.get("title", _concept_title(slug))
        intro = meta.get("intro", "").strip()
        desc = _first_sentence(intro)
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
