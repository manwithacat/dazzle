#!/usr/bin/env python3
"""
Reference Docs Generator for Dazzle

Generates per-file reference documentation from source code.
Implements Section 12 of the MkDocs Material spec.

Usage:
    python scripts/gen_reference_docs.py           # Full generation
    python scripts/gen_reference_docs.py --mode=ci # CI mode (fail if changes)
    python scripts/gen_reference_docs.py --incremental # Only changed files
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
    config_path = ROOT / "scripts" / "reference_docs.config.json"
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

    # Find invariants from multiple sources
    lines = content.split("\n")

    # 1. Comment-based invariants (MUST, invariant, idempotent, etc.)
    invariant_comment_pattern = re.compile(
        r"#.*\b(MUST|MUST NOT|invariant|idempotent|precondition|postcondition)\b", re.IGNORECASE
    )

    # 2. raise ValueError/TypeError patterns (validation)
    # Handles both regular strings and f-strings (f"..." or f'...')
    validation_raise_pattern = re.compile(
        r"raise\s+(?:ValueError|TypeError|AssertionError)\s*\(\s*f?['\"]([^'\"]+)['\"]"
    )

    # 3. assert statements with meaningful conditions
    assert_pattern = re.compile(r"^\s*assert\s+(.+?)(?:,\s*['\"](.+)['\"])?$")

    for i, line in enumerate(lines, 1):
        # Comment-based invariants
        if invariant_comment_pattern.search(line):
            facts["invariants"].append(line.strip())

        # Validation raises
        raise_match = validation_raise_pattern.search(line)
        if raise_match:
            msg = raise_match.group(1)
            if len(msg) > 10:  # Skip trivial messages
                facts["invariants"].append(f"Validates: {msg[:80]}")

        # Assert statements (only if they have a message or meaningful condition)
        assert_match = assert_pattern.match(line)
        if assert_match:
            condition = assert_match.group(1).strip()
            message = assert_match.group(2)
            if message:
                facts["invariants"].append(f"Assert: {message[:60]}")
            elif len(condition) > 5 and "==" in condition or "is not" in condition:
                facts["invariants"].append(f"Assert: {condition[:60]}")

    # Deduplicate invariants
    facts["invariants"] = list(dict.fromkeys(facts["invariants"]))[:10]

    # Find event patterns - expanded detection
    emits: set[str] = set()
    consumes: set[str] = set()

    # 1. Direct emit_event, _emit_event, emit_created/updated/deleted calls
    emit_call_pattern = re.compile(
        r"(?:await\s+)?(?:self\.)?_?emit_(?:event|created|updated|deleted|failed)\s*\("
    )

    # 2. Event bus emit patterns
    bus_emit_pattern = re.compile(
        r"(?:event_?bus|bus)\.(?:emit|publish|send)\s*\(\s*['\"]([^'\"]+)['\"]"
    )

    # 3. Topic strings near emit calls
    topic_pattern = re.compile(r"['\"]([a-z_]+\.(?:created|updated|deleted|failed|sent|received))['\"]")

    # 4. Event class names (e.g., TaskCreatedEvent, OrderSubmittedEvent)
    event_class_pattern = re.compile(r"\b([A-Z][a-zA-Z]+(?:Event|Message|Command))\b")

    # 5. @subscribe, @handler, @on_event decorators
    handler_decorator_pattern = re.compile(r"@(?:subscribe|handler|on_event|handles)\s*\(\s*['\"]([^'\"]+)['\"]")

    for line in lines:
        # Check for emit calls
        if emit_call_pattern.search(line):
            # Look for topic string on same line or nearby context
            topic_match = topic_pattern.search(line)
            if topic_match:
                emits.add(topic_match.group(1))
            else:
                # Generic emit detected
                if "created" in line.lower():
                    emits.add("entity.created")
                elif "updated" in line.lower():
                    emits.add("entity.updated")
                elif "deleted" in line.lower():
                    emits.add("entity.deleted")

        # Bus emit patterns
        bus_match = bus_emit_pattern.search(line)
        if bus_match:
            emits.add(bus_match.group(1))

        # Handler decorators
        handler_match = handler_decorator_pattern.search(line)
        if handler_match:
            consumes.add(handler_match.group(1))

    # Look for event class usage throughout file
    for match in event_class_pattern.finditer(content):
        event_name = match.group(1)
        context = content[max(0, match.start() - 100):match.end() + 50].lower()
        if "emit" in context or "publish" in context or "send" in context:
            emits.add(event_name)
        elif "handle" in context or "consume" in context or "subscribe" in context or "receive" in context:
            consumes.add(event_name)

    facts["events"]["emits"] = sorted(emits)[:10]
    facts["events"]["consumes"] = sorted(consumes)[:10]

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
    parent_name = path.parent.name

    found: list[str] = []

    # Direct name patterns across test directories
    direct_patterns = [
        f"tests/**/test_{name}.py",
        f"tests/**/test_{name}_*.py",
        f"tests/**/*_{name}_test.py",
        f"tests/**/*{name}*.py",
    ]

    for pattern in direct_patterns:
        for test_path in ROOT.glob(pattern):
            if test_path.is_file():
                rel = str(test_path.relative_to(ROOT))
                if rel not in found:
                    found.append(rel)

    # Check for tests in the same package's tests directory
    pkg_tests = path.parent / "tests"
    if pkg_tests.exists():
        for test_file in pkg_tests.glob(f"test_{name}*.py"):
            rel = str(test_file.relative_to(ROOT))
            if rel not in found:
                found.append(rel)

    # Check for module-level tests matching parent directory name
    if parent_name and parent_name != "src":
        for pattern in [f"tests/**/test_{parent_name}*.py"]:
            for test_path in ROOT.glob(pattern):
                if test_path.is_file():
                    rel = str(test_path.relative_to(ROOT))
                    if rel not in found:
                        found.append(rel)

    # JavaScript test files
    js_test_patterns = [
        path.with_suffix(".test.js"),
        path.with_suffix(".test.ts"),
        path.with_name(f"{name}.spec.js"),
        path.with_name(f"{name}.spec.ts"),
    ]
    for test_path in js_test_patterns:
        if test_path.exists():
            found.append(str(test_path.relative_to(ROOT)))

    # Limit to 5 most relevant tests
    return found[:5]


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
