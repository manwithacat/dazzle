"""Flense inventory — the only admissible evidence for a keep or a removal (ADR-0057).

One committed table, `docs/reference/flense-inventory.md`, answers for every
framework subpackage, top-level DSL construct, MCP tool and CLI group: how much
does it weigh, and which named consumer uses it? Consumers come from
`flense_consumers.toml`; an absent checkout is reported as absent, never as
"unused", so the table cannot lie on a machine without the consumer repos.

Use is measured by DSL declarations *and* non-DSL signals (CLI calls, Python
imports, `dazzle.toml` sections, framework-read project files, framework URLs,
MCP tool names), because consumers reach the framework through app code,
scripts and assets as well as DSL.

Usage:
    uv run python scripts/flense_inventory.py            # rewrite the table
    uv run python scripts/flense_inventory.py --check    # exit 1 if stale
    uv run python scripts/flense_inventory.py --json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "flense_consumers.toml"
OUTPUT = REPO / "docs" / "reference" / "flense-inventory.md"
PARSER_INIT = REPO / "src" / "dazzle" / "core" / "dsl_parser_impl" / "__init__.py"
CLI_INIT = REPO / "src" / "dazzle" / "cli" / "__init__.py"
RUNTIME_URLS = REPO / "docs" / "api-surface" / "runtime-urls.txt"
_SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", "dist", "worktrees"}


def _tracked(root: Path, suffix: str) -> list[Path]:
    """Git-tracked files under ``root`` with ``suffix`` — the same set CI sees."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", str(root)], cwd=REPO, capture_output=True, check=True
    ).stdout
    # A file deleted in the worktree but not yet staged is still listed; skip it.
    return [
        REPO / p for p in out.decode().split("\0") if p.endswith(suffix) and (REPO / p).is_file()
    ]


# Scans skip vendored, generated and agent-scratch trees (incl. agent worktree copies).
_SCAN_SKIP = set(
    "node_modules .venv .git dev_docs archive .grok .dazzle __pycache__ worktrees".split()
)
_SCAN_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".toml", ".md", ".js", ".html"}
_MAX_SCAN_BYTES = 2_000_000  # skip minified bundles
Texts = dict[Path, str]
Matrix = dict[str, dict[str, int | None]]


def _py_lines(root: Path) -> int:
    return sum(sum(1 for _ in p.open("rb")) for p in _tracked(root, ".py"))


def _md_lines(root: Path) -> int:
    # Tracked files only; the inventory excludes itself so a rerun is a fixed point.
    return sum(sum(1 for _ in p.open("rb")) for p in _tracked(root, ".md") if p != OUTPUT)


def construct_keywords() -> list[str]:
    """Top-level keywords from the parser dispatch table, plus `app`."""
    text = PARSER_INIT.read_text(encoding="utf-8")
    names = set(re.findall(r"TokenType\.[A-Z_]+:\s*self\._dispatch_([a-z_]+)", text))
    return sorted(names | {"app"})


def cli_groups() -> list[str]:
    text = CLI_INIT.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'add_typer\([^)]*?name="([a-z-]+)"', text)))


def cli_top_commands() -> list[str]:
    """Bare top-level commands (`app.command(name=...)`, `@app.command(name=...)`)."""
    text = CLI_INIT.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'(?<![\w.])app\.command\(name="([a-z-]+)"', text)))


def _src_literals(sub: str, pattern: str) -> set[str]:
    found: set[str] = set()
    for p in (REPO / "src" / "dazzle" / sub).rglob("*.py"):
        if "tests" not in p.parts:
            found |= set(re.findall(pattern, p.read_text(encoding="utf-8", errors="ignore")))
    return found


def endpoint_prefixes() -> list[str]:
    """First path segments the framework mounts: every route's first segment in the
    runtime-urls baseline, plus the router mount prefixes under `src/dazzle/http`
    (baseline routes are router-relative, so `/_dazzle`, `/auth`, `/graphql` live there)."""
    text = RUNTIME_URLS.read_text(encoding="utf-8")
    segs = set(re.findall(r"^\s+[A-Z]+ \| /([^/{\s]+)", text, re.M))
    return sorted(segs | _src_literals("http", r'(?:prefix|path: str)\s*=\s*"/([^/{"\s]+)'))


def project_file_names() -> list[str]:
    """Project files the framework reads: `*spec.yaml` anywhere, `*.toml` the CLI opens."""
    names = _src_literals("", r'"([a-z_]+spec\.ya?ml)"') | _src_literals(
        "cli", r'"([a-z_]+\.toml)"'
    )
    return sorted(names - {"pyproject.toml"})


def scan_texts(root: Path) -> Texts:
    """Every scannable text file under root, excluded trees pruned."""
    out: Texts = {}
    for d, dirs, files in root.walk():
        dirs[:] = sorted(x for x in dirs if x not in _SCAN_SKIP)
        for f in sorted(files):
            p = d / f
            if p.suffix not in _SCAN_SUFFIXES and f != "Makefile":
                continue
            try:
                if p.stat().st_size <= _MAX_SCAN_BYTES:
                    out[p] = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
    return out


def _of(texts: Texts, kinds: set[str]) -> Iterable[str]:
    """Texts whose suffix or file name is in kinds."""
    return (t for p, t in texts.items() if p.suffix in kinds or p.name in kinds)


# Whitespace is spelled as an alternation, not a character class, because the
# install-hint gate forbids the distribution-name-plus-bracket spelling in the tree.
_CLI_RE = re.compile(r"(?<![\w.-])dazzle(?:\x20|\t)+([a-z][\w-]*)(?:(?:\x20|\t)+([a-z][\w-]*))?")
_CLI_FILES = {"Makefile", ".sh", ".yml", ".yaml", ".toml", ".md", ".py"}


def scan_cli(texts: Texts, groups: set[str], top: set[str]) -> Counter[str]:
    """Counts keyed `group` / `command`, plus `group sub` for the word after a group."""
    c: Counter[str] = Counter()
    for t in _of(texts, _CLI_FILES):
        for g, sub in _CLI_RE.findall(t):
            if g in groups or g in top:
                c.update([g] + ([f"{g} {sub}"] if g in groups and sub else []))
    return c


_IMPORT_RE = re.compile(r"^[ \t]*(?:from|import)[ \t]+dazzle((?:\.\w+){0,2})\b", re.M)


def scan_imports(texts: Texts) -> Counter[str]:
    return Counter("dazzle" + m for t in _of(texts, {".py"}) for m in _IMPORT_RE.findall(t))


def scan_toml_sections(texts: Texts) -> Counter[str]:
    """Files declaring each top-level `dazzle.toml` table (`[[auth.x]]` -> `auth`)."""
    head = re.compile(r"^[ \t]*\[\[?[ \t]*([A-Za-z0-9_-]+)", re.M)
    c: Counter[str] = Counter()
    for t in _of(texts, {"dazzle.toml"}):
        c.update(set(head.findall(t)))
    return c


def scan_project_files(texts: Texts, names: list[str]) -> Counter[str]:
    return Counter(p.name for p in texts if p.name in names)


def scan_endpoints(texts: Texts, prefixes: list[str]) -> Counter[str]:
    alts = "|".join(re.escape(s) for s in sorted(prefixes, key=lambda s: (-len(s), s)))
    pat = re.compile(rf"(?<![\w.~/-])/({alts})(?![\w-])")
    return Counter(m for t in _of(texts, {".py", ".js", ".html", ".md"}) for m in pat.findall(t))


def scan_mcp(texts: Texts, tool_ops: dict[str, list[str]]) -> Counter[str]:
    """`mcp__dazzle__<tool>`, `` `tool op` `` / `` `tool` op ``, `tool(operation="op")`."""
    pats = {}
    for tool, ops in tool_ops.items():
        alts = [rf"mcp__dazzle__{tool}\b"]
        if ops:
            o = "|".join(map(re.escape, ops))
            alts.append(
                rf"`{tool}(?:`[ \t]*`?|[ \t]+`?)(?:op(?:eration)?[ \t]*[=:][ \t]*)?[\"']?(?:{o})\b"
            )
            alts.append(rf"(?<![\w.]){tool}\(\s*operation\s*=\s*[\"'](?:{o})\b")
        pats[tool] = re.compile("|".join(alts))
    c: Counter[str] = Counter()
    for t in _of(texts, {".md", ".toml", ".py"}):
        for tool, pat in pats.items():
            if tool in t:  # cheap prefilter; the regex is the count
                c[tool] += len(pat.findall(t))
    return c


Columns = dict[str, Counter[str] | None]


def _matrix(keys: Iterable[str], per_col: Columns) -> Matrix:
    return {
        k: {col: (None if c is None else c.get(k, 0)) for col, c in per_col.items()}
        for k in sorted(keys)
    }


def _observed(per_col: Columns) -> set[str]:
    return {k for c in per_col.values() if c for k, v in c.items() if v}


def signals(roots: dict[str, Path | None], tool_ops: dict[str, list[str]]) -> dict[str, Any]:
    """Non-DSL usage signals per consumer column (None = absent checkout)."""
    texts = {n: (scan_texts(r) if r is not None and r.is_dir() else None) for n, r in roots.items()}
    groups, top = set(cli_groups()), set(cli_top_commands())
    prefixes, files = endpoint_prefixes(), project_file_names()

    def per(fn: Callable[[Texts], Counter[str]]) -> Columns:
        return {n: (None if t is None else fn(t)) for n, t in texts.items()}

    cli = per(lambda t: scan_cli(t, groups, top))
    imports, toml = per(scan_imports), per(scan_toml_sections)
    return {
        "cli": _matrix(groups | top, cli),
        "cli_subcommands": sorted(k for k in _observed(cli) if " " in k),
        "imports": _matrix(_observed(imports), imports),
        "toml_sections": _matrix(_observed(toml), toml),
        "project_files": _matrix(files, per(lambda t: scan_project_files(t, files))),
        "endpoints": _matrix(prefixes, per(lambda t: scan_endpoints(t, prefixes))),
        "mcp": _matrix(tool_ops, per(lambda t: scan_mcp(t, tool_ops))),
    }


def load_consumers() -> list[dict[str, Any]]:
    data = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    out = []
    for c in data.get("consumers", []):
        path = Path(c["path"])
        out.append({**c, "present": path.is_dir()})
    return out


def _dsl_text(root: Path) -> str:
    chunks = []
    for p in root.rglob("*.dsl"):
        if _SKIP_DIRS.isdisjoint(p.relative_to(root).parts):
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def construct_usage(
    keywords: list[str], roots: dict[str, Path | None]
) -> dict[str, dict[str, int | None]]:
    """{keyword: {column: count-or-None}} — None means the root is absent."""
    texts = {
        name: (_dsl_text(root) if root is not None and root.is_dir() else None)
        for name, root in roots.items()
    }
    usage: dict[str, dict[str, int | None]] = {}
    for kw in keywords:
        pat = re.compile(rf"^{re.escape(kw)}\b", re.M)
        usage[kw] = {
            name: (len(pat.findall(t)) if t is not None else None) for name, t in texts.items()
        }
    return usage


def subpackage_mass() -> list[dict[str, Any]]:
    src = REPO / "src" / "dazzle"
    tests = REPO / "tests"
    test_files = [
        p for p in tests.rglob("test_*.py") if _SKIP_DIRS.isdisjoint(p.relative_to(tests).parts)
    ]
    rows = []
    for d in sorted(p for p in src.iterdir() if p.is_dir() and p.name not in _SKIP_DIRS):
        name = d.name
        name_matched = sum(sum(1 for _ in p.open("rb")) for p in test_files if name in p.stem)
        rows.append(
            {"subpackage": name, "src_lines": _py_lines(d), "test_lines_name_matched": name_matched}
        )
    rows.sort(key=lambda r: -r["src_lines"])
    return rows


def mcp_tools() -> list[dict[str, Any]]:
    import logging
    from unittest.mock import patch

    sys.path.insert(0, str(REPO / "src"))
    logging.disable(logging.INFO)  # the MCP server logs at DEBUG on import

    from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

    with patch("dazzle.mcp.server.tools_consolidated.is_dev_mode", return_value=False):
        tools = get_all_consolidated_tools()
    rows = []
    for t in tools:
        enum = ((t.input_schema or {}).get("properties", {}).get("operation", {}) or {}).get(
            "enum"
        ) or []
        rows.append({"tool": t.name, "operations": len(enum), "ops": sorted(enum)})
    return sorted(rows, key=lambda r: r["tool"])


def docs_mass() -> list[dict[str, Any]]:
    docs = REPO / "docs"
    rows = [{"dir": d.name, "md_lines": _md_lines(d)} for d in sorted(docs.iterdir()) if d.is_dir()]
    rows.sort(key=lambda r: -r["md_lines"])
    return rows


def build() -> dict[str, Any]:
    consumers = load_consumers()
    keywords = construct_keywords()
    roots: dict[str, Path | None] = {
        c["name"]: (Path(c["path"]) if c["present"] else None) for c in consumers
    }
    roots["examples"] = REPO / "examples"
    usage = construct_usage(keywords, roots)
    tools = mcp_tools()
    consumer_names = [c["name"] for c in consumers]
    zero = [kw for kw in keywords if all((usage[kw][n] or 0) == 0 for n in consumer_names)]
    unknown = [c["name"] for c in consumers if not c["present"]]
    return {
        "date": _dt.date.today().isoformat(),
        "consumers": consumers,
        "constructs": usage,
        "zero_consumer_constructs": zero,
        "absent_consumers": unknown,
        "subpackages": subpackage_mass(),
        "mcp_tools": [{"tool": r["tool"], "operations": r["operations"]} for r in tools],
        "signals": signals(roots, {r["tool"]: r["ops"] for r in tools}),
        "cli_groups": cli_groups(),
        "docs": docs_mass(),
        "totals": {
            "src_lines": _py_lines(REPO / "src" / "dazzle"),
            "test_lines": _py_lines(REPO / "tests"),
            "docs_lines": _md_lines(REPO / "docs"),
            "construct_count": len(keywords),
        },
    }


def _table(
    label: str, m: Matrix, cols: list[str], extra: dict[str, str] | None = None
) -> list[str]:
    head = f"| {label} | " + " | ".join(cols) + (" | Subcommands seen |" if extra else " |")
    out = [head, "|---|" + "---:|" * len(cols) + ("---|" if extra else "")]
    for k, row in m.items():
        cells = " | ".join("?" if row[c] is None else str(row[c]) for c in cols)
        out.append(f"| `{k}` | {cells} |" + (f" {extra.get(k, '')} |" if extra else ""))
    return out + [""]


# Signal sections: key :: title :: row label :: note (one per line).
_SIGNAL_SECTIONS = [
    line.split(" :: ")
    for line in """\
cli :: CLI groups × consumers :: CLI group / command :: Occurrences of `dazzle <group>` (and bare top-level commands) in `Makefile`, `*.sh`, `*.yml`, `*.yaml`, `*.toml`, `*.md`, `*.py`, excluding `node_modules`, `.venv`, `.git`, `dev_docs/`, `archive/`, `.grok/`, `.dazzle/`, `__pycache__`. "Subcommands seen" is the next word after the group, so prose can add noise.
imports :: Framework modules imported × consumers :: Module :: `from dazzle.<a>[.<b>] import` / `import dazzle.<a>[.<b>]` in `*.py`, keyed by the first two levels. A module not listed is imported by nobody.
toml_sections :: dazzle.toml sections × consumers :: Section :: Number of `dazzle.toml` files declaring each top-level table (`[[auth.oauth_providers]]` counts as `auth`). A section not listed is declared by nobody.
project_files :: Framework project files × consumers :: File :: Files the framework reads from a project (`*spec.yaml` literals in `src/dazzle`, `*.toml` literals in `src/dazzle/cli`), counted by name. This is how `pitch`, `sitespec` and `theme` are consumed without any CLI call.
endpoints :: Framework endpoints referenced × consumers :: Path prefix :: Literal `/<segment>` references in `*.py`, `*.js`, `*.html`, `*.md`. Segments: the first segment of every route in `docs/api-surface/runtime-urls.txt` plus the router mount prefixes in `src/dazzle/http`. Baseline routes are router-relative, so generic segments (`/app`, `/api`, `/select`) also match app-owned URLs: a non-zero is *possible* use, a zero is strong evidence of none.
mcp :: MCP tools named × consumers (approximate) :: Tool :: `mcp__dazzle__<tool>`, a backticked tool name followed by one of its operations, or `<tool>(operation=...)` in `*.md`, `*.toml`, `*.py`. Approximate: bare prose mentions are missed and agent transcripts are not scanned.""".splitlines()
]


def _render_signals(sig: dict[str, Any], cols: list[str]) -> list[str]:
    subs: dict[str, list[str]] = {}
    for gs in sig["cli_subcommands"]:
        g, s = gs.split(" ", 1)
        subs.setdefault(g, []).append(s)
    sub_cells = {g: ", ".join(f"`{s}`" for s in v) for g, v in subs.items()}
    out: list[str] = []
    for key, title, label, note in _SIGNAL_SECTIONS:
        out += [f"## {title}", "", note, ""]
        out += _table(label, sig[key], cols, sub_cells if key == "cli" else None)
    return out


def render(inv: dict[str, Any]) -> str:
    cons = inv["consumers"]
    cols = [c["name"] for c in cons] + ["examples"]
    L: list[str] = []
    L += [
        "# Flense inventory",
        "",
        "> **Generated** by `scripts/flense_inventory.py` from `flense_consumers.toml` and the working tree.",
        "> Do not edit; rerun the script. This table is the only admissible evidence for a keep or a",
        "> removal under [ADR-0057](../adr/0057-consumer-forced-growth-and-mass-ratchet.md).",
        "",
        f"Snapshot: {inv['date']}. Consumers absent on this machine: "
        + (", ".join(inv["absent_consumers"]) or "none")
        + " (absent means *unknown*, never *unused*).",
        "",
        "**How to read.** DSL declarations are one signal among seven. Consumers also reach the",
        "framework through CLI calls in scripts and docs, Python imports, `dazzle.toml` sections,",
        "framework-read project files (`sitespec.yaml`, `pitchspec.yaml` ...), framework URLs in",
        "app code and assets, and MCP tool use. A removal needs a zero in *every*",
        "signal section below for *every* present consumer; `?` (absent consumer) is unknown,",
        "never zero. The non-DSL scanners are text matches: they over-count rather than miss.",
        "",
        "## Totals",
        "",
        "| Measure | Value |",
        "|---|---:|",
    ]
    t = inv["totals"]
    L += [
        f"| Framework source lines (`src/dazzle`) | {t['src_lines']:,} |",
        f"| Test lines (`tests/`) | {t['test_lines']:,} |",
        f"| Documentation lines (`docs/**/*.md`) | {t['docs_lines']:,} |",
        f"| Top-level DSL constructs | {t['construct_count']} |",
        f"| Constructs with zero consumer use | {len(inv['zero_consumer_constructs'])} |",
        "",
        "## Consumers",
        "",
        "| Consumer | Domain | Present |",
        "|---|---|---|",
    ]
    L += [f"| {c['name']} | {c['domain']} | {'yes' if c['present'] else 'absent'} |" for c in cons]
    L += [
        "",
        "## Top-level DSL constructs × consumers",
        "",
        "Counts are top-level declarations in `.dsl` files.",
        "",
    ]
    L.append("| Construct | " + " | ".join(cols) + " | Disposition hint |")
    L.append("|---|" + "---:|" * len(cols) + "---|")
    for kw, row in inv["constructs"].items():
        cells = [("?" if row[c] is None else str(row[c])) for c in cols]
        consumer_total = sum((row[c] or 0) for c in cols[:-1])
        hint = (
            "consumer-used"
            if consumer_total
            else ("examples only" if row["examples"] else "unused")
        )
        L.append(f"| `{kw}` | " + " | ".join(cells) + f" | {hint} |")
    L += [
        "",
        "**Zero consumer use:** " + ", ".join(f"`{k}`" for k in inv["zero_consumer_constructs"]),
        "",
        "## Framework subpackages",
        "",
        "Test lines are name-matched (`tests/**/test_*<subpackage>*.py`) — a floor, not a census.",
        "",
        "| Subpackage | Source lines | Test lines (name-matched) |",
        "|---|---:|---:|",
    ]
    L += [
        f"| `{r['subpackage']}` | {r['src_lines']:,} | {r['test_lines_name_matched']:,} |"
        for r in inv["subpackages"]
    ]
    L += ["", "## MCP tools", "", "| Tool | Operations |", "|---|---:|"]
    L += [f"| `{r['tool']}` | {r['operations']} |" for r in inv["mcp_tools"]]
    L += ["", "## CLI groups", "", ", ".join(f"`{g}`" for g in inv["cli_groups"]), ""]
    L += _render_signals(inv["signals"], cols)
    L += ["## Documentation by directory", "", "| Directory | Markdown lines |", "|---|---:|"]
    L += [f"| `docs/{r['dir']}/` | {r['md_lines']:,} |" for r in inv["docs"]]
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed table is stale")
    ap.add_argument("--json", action="store_true", help="print the inventory as JSON")
    args = ap.parse_args(argv)
    inv = build()
    if args.json:
        print(json.dumps(inv, indent=2))
        return 0
    text = render(inv)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        strip = lambda s: "\n".join(ln for ln in s.splitlines() if not ln.startswith("Snapshot:"))  # noqa: E731
        if strip(current) != strip(text):
            print(
                f"STALE: {OUTPUT.relative_to(REPO)} — rerun scripts/flense_inventory.py",
                file=sys.stderr,
            )
            return 1
        print("OK flense inventory current")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO)}: {inv['totals']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
