"""Drift gate: every shell script in scripts/ uses `set -euo pipefail`.

Layer-3 net for the `shell_without_strict_mode` counter-prior. Catches
scripts that ship without strict mode — silent continuation past failed
commands is one of the highest-leverage corpus-prior shapes to inoculate
against because the fix is mechanical (one line).

Scope:
  - All `*.sh` files under scripts/.
  - All `*.sh` files under app/ (where Dazzle user-project sync/ops jobs live).

Excluded:
  - Scripts in third-party / vendored trees.
  - Scripts deliberately marked as snippets (see ALLOWLIST below).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Scripts that intentionally don't use strict mode (e.g. snippets that need
# to inspect their own exit codes). Add an explicit comment in the script
# itself when adding to this list.
ALLOWLIST: set[str] = set()

STRICT_MODE_RE = re.compile(r"^\s*set\s+-(?=[^\s]*[eu])[^\s]*", re.MULTILINE)


def _shell_scripts() -> list[Path]:
    """Find shell scripts in scripts/ and app/, skipping vendored trees."""
    paths: list[Path] = []
    for directory in ("scripts", "app"):
        base = REPO_ROOT / directory
        if not base.exists():
            continue
        for path in base.rglob("*.sh"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in {"node_modules", "vendor", ".venv"} for part in path.parts):
                continue
            if rel in ALLOWLIST:
                continue
            paths.append(path)
    return paths


@pytest.mark.parametrize("script", _shell_scripts(), ids=lambda p: p.name)
def test_shell_strict_mode(script: Path) -> None:
    """Every script must contain `set -e[u…]` (strict mode) near the top.

    The regex permits `set -e`, `set -eu`, `set -euo pipefail`, `set -ex`,
    etc. — any form that enables at least error-exit and ideally also unset-
    variable detection.
    """
    text = script.read_text(errors="replace")
    # Only look at the first 30 lines — strict mode goes at the top.
    head = "\n".join(text.splitlines()[:30])
    assert STRICT_MODE_RE.search(head), (
        f"{script.relative_to(REPO_ROOT)}: missing `set -euo pipefail` (or equivalent) "
        "near the top. See docs/counter-priors/shell-without-strict-mode.md."
    )


def test_strict_mode_regex_recognises_canonical_forms() -> None:
    """Sanity — the regex catches all common strict-mode declarations."""
    for line in (
        "set -e",
        "set -eu",
        "set -euo pipefail",
        "set -ex",
        "    set -euo pipefail",  # leading whitespace
    ):
        assert STRICT_MODE_RE.search(line), f"regex missed: {line!r}"


def test_strict_mode_regex_rejects_set_o_noclobber() -> None:
    """Sanity — the regex doesn't fire on `set -o` flags that aren't `-e`/`-u`.

    Known limits documented but not asserted: `echo set -e` (inside a string)
    is a false positive of the simple regex. Accepted because the parametrized
    test only scans the first 30 lines of each script, where `echo set -e` is
    vanishingly rare.
    """
    assert not STRICT_MODE_RE.search("set -o noclobber")
    assert not STRICT_MODE_RE.search("set +e")
