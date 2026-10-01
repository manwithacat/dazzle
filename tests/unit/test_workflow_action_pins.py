"""Every third-party `uses:` in a workflow must pin a full commit SHA.

Why this exists
---------------
Two workflows in this repo used a floating tag, so a tag move could change what
CI runs without a review. Beyond that, hand-written pins go wrong in a specific
way: a 40-character SHA is easy to truncate or mistype by a character or two,
and the workflow still parses — it just resolves to nothing, or fails at run
time with an opaque error. Both happened while adding `main-hygiene.yml`, and
neither was caught by YAML parsing or by `ruff`.

What this catches
-----------------
A `uses:` that is neither a full 40-hex SHA nor an explicitly allowlisted tag.
A mistyped pin is the common case, and it is silent until the job runs.

How to satisfy it
-----------------
Copy the SHA from an existing pin rather than retyping it, and note the human
version in a trailing comment (`# v7.0.1`) so `dependabot` can still propose
bumps — that is the convention across this repo's workflows.

What this does NOT catch
------------------------
Whether the SHA points at the action you meant. That is what a review is for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"

_SHA = re.compile(r"^[0-9a-f]{40}$")
_USES = re.compile(r"uses:\s*(?P<action>[\w.-]+/[\w./-]+)@(?P<ref>[^\s#]+)")

# Local composite actions (`./path`) are resolved from the repo, never pinned.
_LOCAL = re.compile(r"^\./")

# Tag refs that predate the pinning convention. Each needs a reason; an
# allowlist that grows silently is the same problem this gate exists to stop.
_TAG_ALLOWLIST: dict[str, str] = {
    "actions/setup-python": (
        "floating @v7 in ci.yml and hm-update-visual-baselines.yml; pinned by SHA "
        "everywhere else. Pre-existing debt this gate now makes visible."
    ),
    "actions/checkout": (
        "floating @v7.0.1 in sync-hatchi-maxchi.yml and "
        "hm-update-visual-baselines.yml; pinned by SHA in the other 15 workflows."
    ),
    "actions/upload-artifact": (
        "floating @v7 in fuzz-nightly.yml and hm-update-visual-baselines.yml; "
        "pinned by SHA in ci.yml."
    ),
}


def _pins() -> list[tuple[str, str, str, str]]:
    found: list[tuple[str, str, str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = _USES.search(line)
            if not m:
                continue
            action, ref = m.group("action"), m.group("ref")
            if _LOCAL.match(ref):
                continue
            found.append((path.name, f"{lineno}:{action}", action, ref))
    return found


def test_workflow_pins_are_well_formed() -> None:
    pins = _pins()
    assert pins, "no `uses:` pins found — the regex is probably wrong"

    bad: list[str] = []
    for fname, where, action, ref in pins:
        if _SHA.match(ref):
            continue
        if action in _TAG_ALLOWLIST and not ref.startswith((".", "..")):
            continue
        bad.append(f"{fname}:{where} -> @{ref}")

    assert not bad, (
        "Every third-party `uses:` must pin a full 40-character commit SHA. A "
        "truncated or mistyped SHA parses fine and fails only at run time.\n"
        f"Tag refs allowed (with reason): {sorted(_TAG_ALLOWLIST)}\n  " + "\n  ".join(bad)
    )


def test_tag_allowlist_entries_are_still_needed() -> None:
    """An allowlist entry nobody uses is rot; keep it honest."""
    used = {action for _f, _w, action, ref in _pins() if not _SHA.match(ref)}
    stale = sorted(set(_TAG_ALLOWLIST) - used)
    assert not stale, (
        f"`_TAG_ALLOWLIST` names actions that now pin a SHA: {stale}. Remove them, "
        "or the allowlist becomes a place where exemptions quietly accumulate."
    )
