#!/usr/bin/env python3
"""
Reference Docs Generator for Dazzle

Generates per-file reference documentation from source code.
Implements Section 12 of the MkDocs Material spec.

Usage:
    python tools/gen_reference_docs.py           # Full generation
    python tools/gen_reference_docs.py --mode=ci # CI mode (fail if changes)
    python tools/gen_reference_docs.py --incremental # Only changed files
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Project root
ROOT = Path(__file__).parent.parent


def load_config() -> dict[str, Any]:
    """Load generator configuration."""
    config_path = ROOT / "tools" / "reference_docs.config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path) as f:
        return json.load(f)


def get_git_sha() -> str:
    """Get current git commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        )
        return result.stdout.strip()[:12]
    except subprocess.CalledProcessError:
        return "unknown"


def get_changed_files(base_ref: str = "origin/main") -> set[str]:
    """Get files changed since base ref."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        )
        return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
    except subprocess.CalledProcessError:
        return set()


def matches_pattern(path: str, patterns: list[str]) -> bool:
    """Check if path matches any glob pattern."""
    from fnmatch import fnmatch

    for pattern in patterns:
        if fnmatch(path, pattern):
            return True
    return False


def find_source_files(config: dict[str, Any]) -> list[Path]:
    """Find all source files matching include/exclude patterns."""
    include = config.get("include", [])
    exclude = config.get("exclude", [])

    files = []
    for pattern in include:
        for path in ROOT.glob(pattern):
            if path.is_file():
                rel_path = str(path.relative_to(ROOT))
                if not matches_pattern(rel_path, exclude):
                    files.append(path)

    return sorted(files)


def detect_language(path: Path) -> str:
    """Detect programming language from file extension."""
    ext = path.suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
    }.get(ext, "unknown")


def extract_python_facts(path: Path) -> dict[str, Any]:
    """Extract facts from a Python file using AST."""
    content = path.read_text(encoding="utf-8", errors="replace")

    facts: dict[str, Any] = {
        "imports": [],
        "exports": [],
        "classes": [],
        "functions": [],
        "docstring": None,
        "invariants": [],
        "events": {"emits": [], "consumes": []},
    }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return facts

    # Module docstring
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        facts["docstring"] = tree.body[0].value.value.strip()

    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                facts["imports"].append(f"{module}.{alias.name}")

        # Classes
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            facts["classes"].append({"name": node.name, "doc": doc[:100]})
            facts["exports"].append(node.name)

        # Functions
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                doc = ast.get_docstring(node) or ""
                facts["functions"].append({"name": node.name, "doc": doc[:100]})
                facts["exports"].append(node.name)

    # Find invariants (lines with MUST, MUST NOT, invariant, idempotent)
    invariant_pattern = re.compile(
        r"#.*\b(MUST|MUST NOT|invariant|idempotent)\b", re.IGNORECASE
    )
    for i, line in enumerate(content.split("\n"), 1):
        if invariant_pattern.search(line):
            facts["invariants"].append(line.strip())

    # Find event patterns
    event_pattern = re.compile(r"['\"]([A-Z][a-zA-Z]+(?:Requested|Completed|Created|Updated|Deleted|Failed))['\"]")
    for match in event_pattern.finditer(content):
        event_name = match.group(1)
        if "emit" in content[max(0, match.start() - 50) : match.start()].lower():
            facts["events"]["emits"].append(event_name)
        else:
            facts["events"]["consumes"].append(event_name)

    return facts


def extract_javascript_facts(path: Path) -> dict[str, Any]:
    """Extract facts from a JavaScript file using regex."""
    content = path.read_text(encoding="utf-8", errors="replace")

    facts: dict[str, Any] = {
        "imports": [],
        "exports": [],
        "functions": [],
        "docstring": None,
        "invariants": [],
        "events": {"emits": [], "consumes": []},
    }

    # Find imports
    import_pattern = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]")
    for match in import_pattern.finditer(content):
        facts["imports"].append(match.group(1))

    # Find exports
    export_pattern = re.compile(r"export\s+(?:function|const|class|async function)\s+(\w+)")
    for match in export_pattern.finditer(content):
        facts["exports"].append(match.group(1))

    # Find function definitions with JSDoc
    func_pattern = re.compile(
        r"/\*\*([^*]*(?:\*(?!/)[^*]*)*)\*/\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"
    )
    for match in func_pattern.finditer(content):
        doc = match.group(1).strip().replace("*", "").strip()[:100]
        facts["functions"].append({"name": match.group(2), "doc": doc})

    # Module docstring (first JSDoc comment)
    first_jsdoc = re.search(r"^/\*\*([^*]*(?:\*(?!/)[^*]*)*)\*/", content, re.MULTILINE)
    if first_jsdoc:
        facts["docstring"] = first_jsdoc.group(1).strip().replace("*", "").strip()[:200]

    return facts


def extract_facts(path: Path) -> dict[str, Any]:
    """Extract facts from a source file."""
    lang = detect_language(path)
    if lang == "python":
        return extract_python_facts(path)
    elif lang in ("javascript", "typescript"):
        return extract_javascript_facts(path)
    return {}


def find_related_tests(path: Path) -> list[str]:
    """Find test files related to this source file."""
    rel_path = path.relative_to(ROOT)
    name = path.stem

    test_patterns = [
        ROOT / "tests" / "unit" / f"test_{name}.py",
        ROOT / "tests" / "integration" / f"test_{name}.py",
        path.parent / "tests" / f"test_{name}.py",
        path.with_name(f"{name}.test.js"),
        path.with_name(f"{name}.test.ts"),
    ]

    found = []
    for test_path in test_patterns:
        if test_path.exists():
            found.append(str(test_path.relative_to(ROOT)))

    return found


def determine_scope(path: Path) -> str:
    """Determine the module/package scope of a file."""
    rel_path = path.relative_to(ROOT)
    parts = rel_path.parts

    if parts[0] == "src":
        if len(parts) > 1:
            return parts[1]  # e.g., "dazzle", "dazzle_dnr_back"
    return "unknown"


def generate_page(path: Path, facts: dict[str, Any], git_sha: str) -> str:
    """Generate a reference doc page for a source file."""
    rel_path = path.relative_to(ROOT)
    lang = detect_language(path)
    scope = determine_scope(path)
    timestamp = datetime.now(timezone.utc).isoformat()
    tests = find_related_tests(path)

    # Build purpose section
    purpose = facts.get("docstring") or "No module docstring available."
    if len(purpose) > 300:
        purpose = purpose[:300] + "..."

    # Build exports section
    exports_md = ""
    if facts.get("exports"):
        for exp in facts["exports"][:20]:  # Limit to 20 exports
            exports_md += f"- `{exp}`\n"
    else:
        exports_md = "No public exports detected.\n"

    # Build imports section
    imports_md = ""
    if facts.get("imports"):
        for imp in facts["imports"][:20]:  # Limit to 20 imports
            imports_md += f"- `{imp}`\n"
    else:
        imports_md = "No imports detected.\n"

    # Build events section
    events = facts.get("events", {})
    emits = events.get("emits", [])
    consumes = events.get("consumes", [])
    events_md = ""
    if emits:
        events_md += f"**Emits:** {', '.join(f'`{e}`' for e in emits[:5])}\n\n"
    if consumes:
        events_md += f"**Consumes:** {', '.join(f'`{c}`' for c in consumes[:5])}\n\n"
    if not events_md:
        events_md = "None detected.\n"

    # Build invariants section
    invariants = facts.get("invariants", [])
    invariants_md = ""
    if invariants:
        for inv in invariants[:5]:
            invariants_md += f"- {inv}\n"
    else:
        invariants_md = "No invariants documented.\n"

    # Build tests section
    tests_md = ""
    if tests:
        for test in tests:
            tests_md += f"- `{test}`\n"
    else:
        tests_md = "No related tests found.\n"

    # Generate markdown
    return f"""# {rel_path}

**Generated:** {timestamp}

**Commit:** {git_sha}

**Language:** {lang}

**Scope:** {scope}

## Purpose

{purpose}

## Key Exports

{exports_md}
## Dependencies

### Imports

{imports_md}
## Event Interactions

{events_md}
## Invariants and Assumptions

{invariants_md}
## Tests

{tests_md}
## Notes

This page was automatically generated by `tools/gen_reference_docs.py`.
"""


def get_submodule(path: Path, scope: str) -> str:
    """Get the submodule path within a scope."""
    rel_path = path.relative_to(ROOT)
    parts = list(rel_path.parts)

    # Remove 'src' and scope from path
    if parts[0] == "src" and len(parts) > 2:
        # Return the subdirectory path after the scope
        subparts = parts[2:-1]  # Exclude filename
        if subparts:
            return "/".join(subparts)
    return ""


def generate_module_page(scope: str, files: list[Path], output_dir: Path) -> str:
    """Generate a module-level index page with all files."""
    # Group files by submodule
    by_submodule: dict[str, list[Path]] = {}
    for f in files:
        submodule = get_submodule(f, scope)
        by_submodule.setdefault(submodule, []).append(f)

    # Sort submodules, with root files first
    sorted_submodules = sorted(by_submodule.keys(), key=lambda x: (x != "", x))

    content = f"""# {scope}

Auto-generated reference documentation for the `{scope}` module.

| Metric | Value |
|--------|-------|
| **Total Files** | {len(files)} |
| **Submodules** | {len([s for s in sorted_submodules if s])} |

"""

    for submodule in sorted_submodules:
        submodule_files = sorted(by_submodule[submodule], key=lambda f: f.name)

        if submodule:
            content += f"## {submodule}/\n\n"
        else:
            content += "## Root\n\n"

        content += f"*{len(submodule_files)} files*\n\n"
        content += "| File | Description |\n"
        content += "|------|-------------|\n"

        for f in submodule_files:
            rel_path = f.relative_to(ROOT)
            doc_path = f"../files/{rel_path}.md"
            # Try to get a short description from the file
            try:
                first_line = f.read_text(encoding="utf-8", errors="replace").split("\n")[0]
                if first_line.startswith('"""') or first_line.startswith("'''"):
                    desc = first_line.strip("\"' ")[:60]
                elif first_line.startswith("//") or first_line.startswith("#"):
                    desc = first_line.lstrip("/#! ").strip()[:60]
                else:
                    desc = ""
            except Exception:
                desc = ""

            if not desc:
                desc = f.stem
            if len(desc) > 60:
                desc = desc[:57] + "..."

            content += f"| [{f.name}]({doc_path}) | {desc} |\n"

        content += "\n"

    return content


def generate_index(files: list[Path], output_dir: Path) -> tuple[str, dict[str, str]]:
    """Generate the reference docs index page and module pages."""
    # Group files by scope
    by_scope: dict[str, list[Path]] = {}
    for f in files:
        scope = determine_scope(f)
        by_scope.setdefault(scope, []).append(f)

    # Generate module pages
    module_pages: dict[str, str] = {}
    for scope in by_scope:
        module_pages[scope] = generate_module_page(scope, by_scope[scope], output_dir)

    # Generate main index
    content = """# API Reference

Auto-generated reference documentation for the Dazzle codebase.

!!! note "Auto-generated content"
    These pages are generated from source code analysis. For curated documentation,
    see the [Architecture](../architecture/overview.md) and [DSL Reference](../reference/index.md) sections.

## Modules

| Module | Files | Description |
|--------|-------|-------------|
"""

    module_descriptions = {
        "dazzle": "Core DSL parser, IR, validator, and CLI",
        "dazzle_dnr_back": "FastAPI backend runtime and services",
        "dazzle_dnr_ui": "JavaScript UI runtime and components",
    }

    for scope in sorted(by_scope.keys()):
        scope_files = by_scope[scope]
        desc = module_descriptions.get(scope, "Module documentation")
        content += f"| [{scope}](modules/{scope}.md) | {len(scope_files)} | {desc} |\n"

    content += """
## Quick Links

- **Parser**: [dazzle/core/parser.py](files/src/dazzle/core/parser.py.md)
- **IR Types**: [dazzle/core/ir/](modules/dazzle.md#coreir)
- **Validator**: [dazzle/core/validator.py](files/src/dazzle/core/validator.py.md)
- **CLI**: [dazzle/cli/](modules/dazzle.md#cli)
- **Backend Runtime**: [dazzle_dnr_back/runtime/](modules/dazzle_dnr_back.md#runtime)
- **UI Components**: [dazzle_dnr_ui/runtime/](modules/dazzle_dnr_ui.md#runtimestaticjs)
"""

    return content, module_pages


def write_meta(output_dir: Path, files: list[Path], git_sha: str) -> None:
    """Write generation metadata."""
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "generator_version": "1.0",
        "file_count": len(files),
        "files": [str(f.relative_to(ROOT)) for f in files],
    }
    meta_path = output_dir.parent / "_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate reference documentation")
    parser.add_argument(
        "--mode",
        choices=["full", "ci"],
        default="full",
        help="Generation mode (ci fails if changes detected)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only regenerate changed files",
    )
    args = parser.parse_args()

    config = load_config()
    output_dir = ROOT / config["output_dir"]
    git_sha = get_git_sha()

    # Find source files
    files = find_source_files(config)
    print(f"Found {len(files)} source files to process")

    # Filter for incremental mode
    if args.incremental:
        changed = get_changed_files()
        files = [f for f in files if str(f.relative_to(ROOT)) in changed]
        print(f"Incremental mode: {len(files)} changed files")

    if not files:
        print("No files to process")
        return 0

    # Generate pages
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        rel_path = path.relative_to(ROOT)
        doc_path = output_dir / f"{rel_path}.md"

        # Extract facts
        facts = extract_facts(path)

        # Generate page
        content = generate_page(path, facts, git_sha)

        # Write file
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(content)
        print(f"  Generated: {doc_path.relative_to(ROOT)}")

    # Generate index and module pages
    all_files = find_source_files(config)  # Use all files for index
    index_content, module_pages = generate_index(all_files, output_dir)

    # Write main index
    index_path = output_dir.parent / "index.md"
    index_path.write_text(index_content)
    print(f"  Generated: {index_path.relative_to(ROOT)}")

    # Write module pages
    modules_dir = output_dir.parent / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    for scope, content in module_pages.items():
        module_path = modules_dir / f"{scope}.md"
        module_path.write_text(content)
        print(f"  Generated: {module_path.relative_to(ROOT)}")

    # Write metadata
    write_meta(output_dir, all_files, git_sha)
    print(f"  Generated: docs/api-reference/_meta.json")

    # CI mode: check for uncommitted changes
    if args.mode == "ci":
        result = subprocess.run(
            ["git", "diff", "--exit-code", "--", "docs/reference"],
            cwd=ROOT,
            capture_output=True,
        )
        if result.returncode != 0:
            print("\nError: Reference docs are out of date!")
            print("Run 'python tools/gen_reference_docs.py' and commit the changes.")
            return 1

    print(f"\nGenerated {len(files)} reference doc pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
