"""A commit SHA cited in the harness docs must resolve.

The programme plan cited three SHAs that were invented at the moment of writing
(`e4600f4a1`, `1c4d5a9a2f`, `8c4d0f1c6`) — none of them resolved, and all three
read as authoritative because they were in backticks next to a workstream heading.

That is the exact failure class this repo keeps paying for: a pointer that looks
verifiable and is wrong. `ExampleRef` cited the first line of a DSL file instead
of the field's own line; `_union_rule_filters` logged a stale residual; and now
the plan itself cited commits that never existed. A cheap check closes the class
for documentation, which is where an agent forms its beliefs.

Scope: the always-on and harness surfaces an agent reads to orient — `AGENTS.md`
and `docs/harness/**`. Other docs are not walked (they legitimately quote
short SHAs and upstream URLs).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
DOCS = [REPO / "AGENTS.md", *sorted((REPO / "docs" / "harness").glob("*.md"))]

# A backticked hex token of 7+ chars. Short hashes collide with words like
# `facade`; 7 is git's minimum unambiguous length, so require 8 to be safe.
_SHA = re.compile(r"`([0-9a-f]{8,40})`")


def _shallow() -> bool:
    """True when the history needed to resolve cited commits is absent.

    Covers both a shallow clone (CI) and a plain export with no `.git` at all
    (a tarball, an archive build), where nothing can be resolved and nothing
    should be claimed.

    CI checks out with a shallow fetch, so a commit from three hours ago is not
    in the object store. Treating that as "does not resolve" made this gate red
    on main while green locally — the exact failure the repository's own dead-def
    ratchet documents its `git ls-files` skip for.
    """
    if not (REPO / ".git").exists():
        return True
    return (REPO / ".git" / "shallow").exists()


def _resolves(sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=REPO,
            capture_output=True,
            timeout=60,
            check=False,
        ).returncode
        == 0
    )


def test_there_are_docs_to_check() -> None:
    """Falsification guard — an empty scope passes vacuously."""
    assert len(DOCS) >= 5, f"only found {len(DOCS)} harness docs"


def test_every_cited_sha_resolves() -> None:
    if _shallow():
        pytest.skip(
            "shallow clone: older commits are absent from the object store, so a cited "
            "SHA cannot be distinguished from a fabricated one here. Runs in full "
            "clones (locally and in any job with fetch-depth: 0)."
        )
    bad: list[str] = []
    for doc in DOCS:
        if not doc.is_file():
            continue
        for sha in sorted(set(_SHA.findall(doc.read_text(encoding="utf-8")))):
            if not _resolves(sha):
                bad.append(f"{doc.relative_to(REPO)}: `{sha}`")
    assert not bad, (
        "cited commits that do not resolve — a reader cannot verify them and a "
        "wrong pointer is worse than none:\n  " + "\n  ".join(bad)
    )
