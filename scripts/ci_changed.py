#!/usr/bin/env python3
"""Path-aware CI extras — run only the checks that own the changed paths.

Usage (from monorepo root)::

    python scripts/ci_changed.py              # vs origin/main...HEAD (or HEAD~1)
    python scripts/ci_changed.py --base HEAD~1
    python scripts/ci_changed.py --status     # one-line summary of selected packs
    python scripts/ci_changed.py --list       # print planned commands, do not run

Exit 0 = all selected packs green (or no packs selected).
Exit 1 = a selected pack failed.
Exit 2 = usage / git error.

Wired into:

* ``make ci-changed`` / ``bash scripts/ci_local.sh changed``
* ``/ship`` after Tier 0 when the diff is non-empty (recommended)
* agents mid-edit for a fast local loop without full ci-core
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass
class Pack:
    name: str
    reason: str
    pytest: list[str] = field(default_factory=list)
    shell: list[list[str]] = field(default_factory=list)


def _python() -> str:
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _git_changed(base: str) -> list[str]:
    # Prefer triple-dot merge-base range when base is a branch.
    cmds = [
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", base],
        ["git", "diff", "--name-only", "--cached"],
    ]
    files: set[str] = set()
    for cmd in cmds:
        proc = subprocess.run(cmd, cwd=REPO, check=False, capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            files.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    # Unstaged + untracked relevant paths (local WIP)
    proc = subprocess.run(
        ["git", "status", "--porcelain", "-u"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            # " M path" / "?? path" / "A  path"
            path = line[3:].strip() if len(line) > 3 else ""
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                files.add(path)
    return sorted(files)


def select_packs(paths: list[str]) -> list[Pack]:
    packs: list[Pack] = []
    py = _python()

    def any_prefix(*prefixes: str) -> bool:
        return any(p.startswith(pref) for p in paths for pref in prefixes)

    def any_glob_substr(*subs: str) -> bool:
        return any(any(s in p for s in subs) for p in paths)

    example_dsl = [
        p for p in paths if p.startswith("examples/") and ("/dsl/" in p or p.endswith(".dsl"))
    ]
    if example_dsl or any(
        p.startswith("examples/") and p.endswith("SPECIFICATION.md") for p in paths
    ):
        apps = sorted(
            {p.split("/")[1] for p in paths if p.startswith("examples/") and "/" in p[9:]}
        )
        packs.append(
            Pack(
                name="examples-spec",
                reason=f"example DSL/SPEC touch ({', '.join(apps[:6])}{'…' if len(apps) > 6 else ''})",
                pytest=[
                    "tests/unit/test_example_spec_bar.py",
                ],
            )
        )

    if any_prefix("src/dazzle/mcp/semantics_kb/") or any(
        p.endswith("patterns.toml") for p in paths
    ):
        packs.append(
            Pack(
                name="kb-meta",
                reason="semantics_kb / patterns.toml",
                pytest=[
                    "tests/unit/test_patterns_phase2_kb_1217.py::test_pattern_count_meta_matches_actual_count",
                    "tests/unit/test_patterns_subtype_of_kb_1248.py::test_pattern_count_meta_matches_actual_count",
                ],
            )
        )

    if any_glob_substr(
        "test_golden_master",
        "__snapshots__/test_golden",
        "core/parser",
        "core/linker",
        "core/ir/",
    ) or any_prefix("src/dazzle/core/"):
        packs.append(
            Pack(
                name="ir-golden",
                reason="core IR / golden snapshot surface",
                pytest=[
                    "tests/integration/test_golden_master.py::test_simple_dsl_to_ir_snapshot",
                    "tests/unit/test_ir_field_reader_parity.py::test_no_new_ir_field_orphans",
                ],
            )
        )

    if any_glob_substr(
        "viewport",
        "app-shell",
        "_render_shell",
        "dz-sidebar",
        "app-shell.css",
    ) or any_prefix(
        "src/dazzle/testing/viewport.py",
        "src/dazzle/render/fragment/renderer/_render_shell.py",
        "src/dazzle/render/dispatch.py",
        "packages/",  # design-system package tree (shell CSS/JS)
    ):
        packs.append(
            Pack(
                name="shell-viewport",
                reason="app shell / viewport / design-system chrome",
                pytest=[
                    "tests/unit/test_viewport.py",
                    "tests/unit/render/fragment/test_topbar_primitive.py",
                ],
            )
        )

    if any_prefix("src/") and not only_tests(paths):
        packs.append(
            Pack(
                name="bandit-src",
                reason="src/ Python change",
                shell=[
                    [
                        py,
                        "-m",
                        "bandit",
                        "-c",
                        "pyproject.toml",
                        "-r",
                        "src/",
                        "--severity-level",
                        "medium",
                    ]
                ],
            )
        )

    if any_prefix("src/dazzle/spec_narrative/") or any(
        "spec_brief_simple_task" in p for p in paths
    ):
        packs.append(
            Pack(
                name="spec-brief",
                reason="spec narrative / brief baseline",
                pytest=["tests/unit/test_spec_narrative_brief_snapshot.py"],
            )
        )

    # Dedup by name preserving order
    seen: set[str] = set()
    out: list[Pack] = []
    for pack in packs:
        if pack.name in seen:
            continue
        seen.add(pack.name)
        out.append(pack)
    return out


def only_tests(paths: list[str]) -> bool:
    return bool(paths) and all(
        p.startswith("tests/") or p.startswith("docs/") or p.endswith(".md") for p in paths
    )


def run_packs(packs: list[Pack], *, dry_run: bool = False) -> int:
    if not packs:
        print("ci-changed: no path packs selected (diff empty or outside mapped surfaces)")
        return 0
    py = _python()
    rc = 0
    for pack in packs:
        print(f"==> ci-changed pack: {pack.name}  ({pack.reason})")
        if pack.pytest:
            cmd = [py, "-m", "pytest", *pack.pytest, "-q", "--tb=line"]
            print("   ", " ".join(cmd))
            if not dry_run:
                proc = subprocess.run(cmd, cwd=REPO, check=False)
                if proc.returncode != 0:
                    rc = 1
        for shell_cmd in pack.shell:
            print("   ", " ".join(shell_cmd))
            if not dry_run:
                # Ensure bandit importable when needed
                if "bandit" in shell_cmd:
                    probe = subprocess.run(
                        [py, "-c", "import bandit"],
                        cwd=REPO,
                        check=False,
                        capture_output=True,
                    )
                    if probe.returncode != 0:
                        subprocess.run(
                            ["uv", "pip", "install", "bandit[toml]"],
                            cwd=REPO,
                            check=False,
                        )
                proc = subprocess.run(shell_cmd, cwd=REPO, check=False)
                if proc.returncode != 0:
                    rc = 1
    if rc == 0:
        print("OK ci-changed all selected packs green")
    else:
        print("FAIL ci-changed: one or more packs failed", file=sys.stderr)
    return rc


def resolve_base(explicit: str | None) -> str:
    if explicit:
        return explicit
    # Prefer origin/main if it exists
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if proc.returncode == 0:
        return "origin/main"
    return "HEAD~1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", help="git base ref (default: origin/main or HEAD~1)")
    parser.add_argument("--list", action="store_true", help="Print packs only")
    parser.add_argument("--status", action="store_true", help="One-line pack summary")
    parser.add_argument("--dry-run", action="store_true", help="Print commands, do not run")
    args = parser.parse_args(argv)

    base = resolve_base(args.base)
    paths = _git_changed(base)
    packs = select_packs(paths)

    if args.status:
        names = ",".join(p.name for p in packs) if packs else "-"
        print(f"ci_changed base={base} files={len(paths)} packs={names}")
        return 0

    if args.list:
        print(f"base={base} files={len(paths)}")
        for p in paths[:40]:
            print(f"  {p}")
        if len(paths) > 40:
            print(f"  … +{len(paths) - 40} more")
        print("packs:", ", ".join(p.name for p in packs) or "(none)")
        return 0

    if args.dry_run:
        print(f"base={base} files={len(paths)}")
        return run_packs(packs, dry_run=True)

    return run_packs(packs, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
