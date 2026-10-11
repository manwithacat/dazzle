"""Flense inventory — the only admissible evidence for a keep or a removal (ADR-0057).

One committed table, `docs/reference/flense-inventory.md`, answers for every
framework subpackage, top-level DSL construct, MCP tool and CLI group: how much
does it weigh, and which named consumer uses it? Consumers come from
`flense_consumers.toml`; an absent checkout is reported as absent, never as
"unused", so the table cannot lie on a machine without the consumer repos.

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
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "flense_consumers.toml"
OUTPUT = REPO / "docs" / "reference" / "flense-inventory.md"
PARSER_INIT = REPO / "src" / "dazzle" / "core" / "dsl_parser_impl" / "__init__.py"
CLI_INIT = REPO / "src" / "dazzle" / "cli" / "__init__.py"
_SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", "dist"}


def _py_lines(root: Path) -> int:
    total = 0
    for p in root.rglob("*.py"):
        if _SKIP_DIRS.isdisjoint(p.parts):
            total += sum(1 for _ in p.open("rb"))
    return total


def _md_lines(root: Path) -> int:
    # The inventory excludes itself so a rerun is a fixed point.
    return sum(sum(1 for _ in p.open("rb")) for p in root.rglob("*.md") if p != OUTPUT)


def construct_keywords() -> list[str]:
    """Top-level keywords from the parser dispatch table, plus `app`."""
    text = PARSER_INIT.read_text(encoding="utf-8")
    names = set(re.findall(r"TokenType\.[A-Z_]+:\s*self\._dispatch_([a-z_]+)", text))
    return sorted(names | {"app"})


def cli_groups() -> list[str]:
    text = CLI_INIT.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'add_typer\([^)]*?name="([a-z-]+)"', text)))


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
        if _SKIP_DIRS.isdisjoint(p.parts):
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
    test_files = [p for p in tests.rglob("test_*.py") if _SKIP_DIRS.isdisjoint(p.parts)]
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
        rows.append({"tool": t.name, "operations": len(enum)})
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
        "mcp_tools": mcp_tools(),
        "cli_groups": cli_groups(),
        "docs": docs_mass(),
        "totals": {
            "src_lines": _py_lines(REPO / "src" / "dazzle"),
            "test_lines": _py_lines(REPO / "tests"),
            "docs_lines": _md_lines(REPO / "docs"),
            "construct_count": len(keywords),
        },
    }


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
