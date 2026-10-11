"""Makefile recipes must resolve, and must not rebuild the CI venv.

* **Every file a `make` recipe names exists.** pytest exits 4 on a missing
  file, so a dangling path makes a gate fail for a reason unrelated to what it
  guards (`make test-ux-preflight` once named a test deleted by #1720).
* **The preflight recipes do not call `uv run`.** The suite shells out to them;
  on a 3.12/3.13 CI cell `uv run` recreates `.venv` as 3.14 mid-suite (CI badge
  red 2026-10-06). A 3.14 laptop cannot see it any other way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"

_FILE_REF = re.compile(
    r"(?<![\w/.])((?:tests|scripts|src|docs|examples|fixtures|packages)/[\w./-]+\.(?:py|sh|md|toml|txt|yml|yaml|json))"
)
_MAKE_TARGET_DEF = re.compile(r"^([a-z][a-z0-9-]*):", re.MULTILINE)


def _recipe_of(target: str) -> str:
    """The recipe lines of one Makefile target (tab-indented body)."""
    lines = MAKEFILE.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^{re.escape(target)}:")
    start = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        body.append(line)
    return "\n".join(body)


def test_no_make_recipe_references_a_missing_file() -> None:
    defined = set(_MAKE_TARGET_DEF.findall(MAKEFILE.read_text(encoding="utf-8")))
    problems: list[str] = []
    for target in sorted(defined):
        for path in sorted({m.group(1) for m in _FILE_REF.finditer(_recipe_of(target))}):
            if not (REPO / path).exists():
                problems.append(f"make {target} names a missing file: {path}")
    assert not problems, "\n".join(problems)


def test_the_recipe_scan_actually_scanned() -> None:
    """Falsification guard: an empty extraction would pass the check above vacuously."""
    defined = _MAKE_TARGET_DEF.findall(MAKEFILE.read_text(encoding="utf-8"))
    assert len(defined) > 20, f"only {len(defined)} targets parsed from the Makefile"
    scanned = {m.group(1) for t in defined for m in _FILE_REF.finditer(_recipe_of(t))}
    assert len(scanned) > 5, f"only {len(scanned)} file references found in recipes"


def test_preflight_recipe_does_not_rebuild_the_venv() -> None:
    """`UV_NO_SYNC` on the python-tests pytest steps is the belt for any other
    nested `uv run` during the suite."""
    import yaml

    for target in ("test-ux-preflight", "test-ux-deep"):
        recipe = _recipe_of(target)
        assert not re.search(r"(\$\(UV\)|\buv) run\b", recipe), (
            f"make {target} calls uv run; that recreates .venv on a non-3.14 "
            f"CI cell. Use .venv/bin/python -m."
        )
        assert ".venv/bin/python -m" in recipe, (
            f"make {target} must invoke the project venv interpreter"
        )

    doc = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = doc["jobs"]["python-tests"]["steps"]
    pytest_steps = [s for s in steps if str(s.get("name", "")).startswith("Run tests with pytest")]
    assert len(pytest_steps) == 2
    for step in pytest_steps:
        env = step.get("env") or {}
        assert str(env.get("UV_NO_SYNC")) == "1", step.get("name")
