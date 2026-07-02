"""Every example app carries a committed, fresh, stakeholder-grade SPECIFICATION.md.

The quality bar for the spec-narrative pipeline's committed output (the guides-bar
pattern, applied to specs):

1. **Existence** — every app under ``examples/`` has a ``SPECIFICATION.md``.
2. **Freshness** — the document's footer fingerprint matches the brief recomputed
   from the live DSL. A model change without regeneration fails here; the fix is
   ``/spec-narrate`` for that example (the footer comes from
   ``dazzle spec brief --fingerprint``).
3. **Structure** — an Executive summary is present, and there are at least as
   many ``##`` sections as the brief's populated skeleton entries.
4. **Verifiability** — every technical-foundation / compliance claim the app
   activates has its ``evidence`` command cited in the document (the "run this
   to check" contract is the document's spine).
5. **Vocabulary** — no database jargon (the audience is non-technical) and no
   placeholder text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

_REPO = Path(__file__).resolve().parents[2]
_EXAMPLES = sorted(p.name for p in (_REPO / "examples").iterdir() if (p / "dazzle.toml").exists())

_FORBIDDEN = ["foreign key", "varchar", "uuid", "primary key", "lorem", "TODO:"]

_FOOTER_RE = re.compile(r"<!--\s*dazzle-spec-brief:\s*(sha256:[0-9a-f]{64})\s*-->")


def _brief(example: str):
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.spec_narrative.brief import build_brief

    return build_brief(load_project_appspec(_REPO / "examples" / example))


@pytest.fixture(scope="module")
def briefs() -> dict:
    return {ex: _brief(ex) for ex in _EXAMPLES}


def _doc(example: str) -> str:
    path = _REPO / "examples" / example / "SPECIFICATION.md"
    assert path.exists(), f"{example} has no SPECIFICATION.md — generate it with /spec-narrate"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("example", _EXAMPLES)
def test_spec_exists_and_is_fresh(example: str, briefs: dict) -> None:
    from dazzle.spec_narrative.brief import brief_fingerprint

    doc = _doc(example)
    m = _FOOTER_RE.search(doc)
    assert m, f"{example}/SPECIFICATION.md is missing the dazzle-spec-brief footer"
    expected = brief_fingerprint(briefs[example])
    assert m.group(1) == expected, (
        f"{example}/SPECIFICATION.md is stale (footer {m.group(1)[:18]}… != live "
        f"{expected[:18]}…) — the DSL changed; re-run /spec-narrate for this example"
    )


@pytest.mark.parametrize("example", _EXAMPLES)
def test_spec_structure_matches_skeleton(example: str, briefs: dict) -> None:
    doc = _doc(example)
    assert re.search(r"^##\s+Executive summary", doc, re.IGNORECASE | re.MULTILINE), (
        f"{example}: no Executive summary section"
    )
    populated = sum(1 for s in briefs[example].skeleton if s.populated)
    headings = len(re.findall(r"^##\s+", doc, re.MULTILINE))
    assert headings >= populated, (
        f"{example}: {headings} sections for {populated} populated skeleton entries"
    )


@pytest.mark.parametrize("example", _EXAMPLES)
def test_spec_cites_every_activated_claims_evidence(example: str, briefs: dict) -> None:
    doc = _doc(example)
    cited_ids = {cid for s in briefs[example].skeleton for cid in s.claim_ids}
    missing = [
        c.evidence
        for c in briefs[example].activated_claims
        if c.id in cited_ids and c.evidence not in doc
    ]
    assert not missing, (
        f"{example}: activated claims lack their evidence command in the doc: {missing}"
    )


@pytest.mark.parametrize("example", _EXAMPLES)
def test_spec_vocabulary_is_stakeholder_safe(example: str) -> None:
    doc = _doc(example).lower()
    hits = [w for w in _FORBIDDEN if w.lower() in doc]
    assert not hits, f"{example}: forbidden vocabulary in SPECIFICATION.md: {hits}"
