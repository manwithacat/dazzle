# Fitness Investigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a greenfield `src/dazzle/fitness/investigator/` package that takes a ranked cluster from `fitness-queue.md` and produces a structured `Proposal` on disk. Read-only over the repo; write-side limited to `.dazzle/fitness-proposals/`.

**Architecture:** Six-module package (case_file, proposal, attempted, tools, mission, runner) plus a metrics sink. Uses the existing `DazzleAgent` framework with `NullObserver` + `NullExecutor` backends (investigator is blind to the browser; it only uses tools). Terminal action is `propose_fix`, enforced via a completion closure that reads a `ToolState.terminal_status` flag. `corrector.py` is untouched — audit + delete is a separate follow-up ship.

**Tech Stack:** Python 3.12+, existing `dazzle.agent.core` (Mission, AgentTool, DazzleAgent), existing `dazzle.fitness.triage` (Cluster, DedupeKey, read_queue_file), existing `dazzle.fitness.backlog` (read_backlog), existing `dazzle.fitness.models` (Finding, EvidenceEmbedded), Typer for CLI, pytest for tests, PyYAML for frontmatter, ripgrep subprocess fallback.

**Spec:** `docs/superpowers/specs/2026-04-14-fitness-investigator-design.md`

---

## Adaptations from spec

The plan implements the spec faithfully but adapts three implementation details that the spec specified at too-high a level:

1. **`ProposedFix` replaces `corrector.Fix`.** The spec said "reuse `corrector.Fix`" but the actual `corrector.Fix` has `touched_files: list[str]`, `summary: str`, `diff: str` — it's a multi-file bundle, not the per-fix shape the spec wanted. The plan defines a fresh `ProposedFix` dataclass in `investigator/proposal.py` with `file_path`, `line_range`, `diff`, `rationale`, `confidence`. The "don't refactor corrector.py" invariant still holds — the investigator simply doesn't import from it.
2. **`MissionComplete` replaced with `ToolState.terminal_status` flag.** `DazzleAgent._execute_tool` catches all exceptions from tool handlers and converts them to failed `ActionResult`s — raising `MissionComplete` would get swallowed. The plan has `propose_fix` set `state.terminal_status = "proposed"` (or `"blocked_*"`) and the mission's completion closure returns `True` when `state.terminal_status is not None`.
3. **Case file goes in `system_prompt`, not a "first user turn seed observation".** Existing `Mission` has no seed-observation field; mission-specific context lives in `system_prompt`. `build_investigator_mission` formats `case_file.to_prompt_text()` into the system prompt.

Everything else matches the spec verbatim.

---

## File structure

```
src/dazzle/fitness/investigator/
  __init__.py              # public exports
  case_file.py             # LocusExcerpt, CaseFile, build_case_file, CaseFileBuildError
  proposal.py              # ProposedFix, Proposal, save/load/validation/blocked artefacts
  attempted.py             # AttemptedIndex, AttemptedEntry, load/save/rebuild/mark
  tools.py                 # ToolState, 6 AgentTool builders
  agent_backends.py        # NullObserver + NullExecutor
  mission.py               # build_investigator_mission, system prompt
  runner.py                # InvestigationResult, run_investigation, walk_queue
  metrics.py               # append_metric

src/dazzle/fitness/backlog.py          # MODIFY: add read_backlog_findings
src/dazzle/cli/fitness.py              # MODIFY: add investigate subcommand

tests/unit/fitness/investigator/
  __init__.py
  test_backlog_findings.py   # read_backlog_findings round-trip
  test_case_file.py
  test_proposal.py
  test_attempted.py
  test_tools.py
  test_mission.py
  test_runner.py
  test_metrics.py

tests/unit/fitness/test_investigate_cli.py
tests/integration/fitness/test_investigator_real.py  # e2e-gated

docs/reference/fitness-investigator.md  # new
CHANGELOG.md                             # modify: Unreleased → Added
.claude/CLAUDE.md                        # modify: Extending section pointer
```

Each module is ≤ 400 LOC target. `tools.py` is the largest (6 tool builders + ToolState + shared helpers) — if it exceeds 500 LOC, split into `tools_read.py` + `tools_write.py`.

---

## Task list (20 tasks)

The tasks below are broken into smaller batches that a subagent controller can dispatch sequentially. Each task contains its own steps. I'll emit them in sections to keep within output budgets; resume by reading the existing plan file and appending the next batch.

**Batch status:**
- [x] Plan header + structure
- [x] Batch 1 (Tasks 1–4): backlog reader, dataclasses, proposal I/O, attempted index
- [x] Batch 2 (Tasks 5–8): case file (sample, siblings, windowing, prompt rendering)
- [ ] Batch 3 (Tasks 9–14): six tools
- [ ] Batch 4 (Tasks 15–17): mission assembly, metrics, runner
- [ ] Batch 5 (Tasks 18–20): CLI, integration test, docs

Each batch will be appended to this file as the plan is written. The implementer should execute one task at a time following TDD: red → green → commit. Type-check with `mypy src/dazzle/fitness/investigator/` after each task.

---

## Task 1: `read_backlog_findings` — reconstruct Finding objects from backlog file

**Files:**
- Modify: `src/dazzle/fitness/backlog.py`
- Test: `tests/unit/fitness/investigator/test_backlog_findings.py` (new file)
- Create: `tests/unit/fitness/investigator/__init__.py` (empty)

**Why:** `read_backlog` returns plain row dicts. The case file needs full `Finding` objects (including `evidence_embedded`) which live only in the `### <id>` envelope JSON blocks below the table. This task adds a new reader that parses both.

- [ ] **Step 1: Create tests directory and write the failing test**

Create `tests/unit/fitness/investigator/__init__.py` (empty file).

Create `tests/unit/fitness/investigator/test_backlog_findings.py`:

```python
"""Tests for read_backlog_findings — round-trip a Finding through backlog I/O."""

from datetime import datetime, UTC
from pathlib import Path

import pytest

from dazzle.fitness.backlog import read_backlog_findings, upsert_findings
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _sample_finding(fid: str = "f_001") -> Finding:
    return Finding(
        id=fid,
        created=datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC),
        run_id="run_abc",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="high",
        persona="admin",
        capability_ref="Ticket.create",
        expected="error announced via aria-describedby",
        observed="aria-describedby missing on control",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"step": 1, "description": "check aria-describedby"},
            diff_summary=[],
            transcript_excerpt=[{"kind": "observe", "text": "control has no describedby"}],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def test_read_backlog_findings_round_trip(tmp_path: Path) -> None:
    backlog = tmp_path / "fitness-backlog.md"
    original = _sample_finding("f_001")
    upsert_findings(backlog, [original])

    findings = read_backlog_findings(backlog)
    assert len(findings) == 1
    got = findings[0]
    assert got.id == "f_001"
    assert got.axis == "coverage"
    assert got.severity == "high"
    assert got.persona == "admin"
    assert got.expected == "error announced via aria-describedby"
    assert got.observed == "aria-describedby missing on control"
    assert got.evidence_embedded.transcript_excerpt == [
        {"kind": "observe", "text": "control has no describedby"}
    ]


def test_read_backlog_findings_missing_file(tmp_path: Path) -> None:
    assert read_backlog_findings(tmp_path / "does-not-exist.md") == []


def test_read_backlog_findings_multiple(tmp_path: Path) -> None:
    backlog = tmp_path / "fitness-backlog.md"
    upsert_findings(backlog, [_sample_finding("f_001"), _sample_finding("f_002")])

    findings = read_backlog_findings(backlog)
    assert sorted(f.id for f in findings) == ["f_001", "f_002"]


def test_read_backlog_findings_ignores_table_only_rows(tmp_path: Path) -> None:
    """A row in the table with no matching envelope block should be skipped."""
    backlog = tmp_path / "fitness-backlog.md"
    backlog.write_text(
        "# Fitness Backlog\n\n"
        "| id | created | locus | axis | severity | persona | status | route | summary |\n"
        "|----|---------|-------|------|----------|---------|--------|-------|---------|\n"
        "| f_orphan | 2026-04-14T12:00:00+00:00 | implementation | coverage | high | admin | PROPOSED | soft | some summary |\n"
        "\n## Evidence\n\n"
    )
    assert read_backlog_findings(backlog) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/investigator/test_backlog_findings.py -v`
Expected: FAIL — `ImportError: cannot import name 'read_backlog_findings' from 'dazzle.fitness.backlog'`

- [ ] **Step 3: Implement `read_backlog_findings` in `src/dazzle/fitness/backlog.py`**

Read the existing `src/dazzle/fitness/backlog.py` first to see its imports and structure. Then append at the end (after `upsert_findings`):

```python
import json
import re

from dazzle.fitness.models import EvidenceEmbedded, Finding

_ENVELOPE_BLOCK_RE = re.compile(
    r"^### (?P<id>\S+)\s*\n+```json\n(?P<payload>.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def read_backlog_findings(path: Path) -> list[Finding]:
    """Parse the envelope blocks in a fitness-backlog.md file into Finding objects.

    Only returns findings whose envelope block contains a valid JSON payload.
    Table-only rows with no matching envelope are ignored — those indicate
    the file was partially written or manually edited and cannot be
    reconstructed losslessly.
    """
    if not path.exists():
        return []

    text = path.read_text()
    findings: list[Finding] = []
    for m in _ENVELOPE_BLOCK_RE.finditer(text):
        try:
            payload = json.loads(m.group("payload"))
        except json.JSONDecodeError:
            continue
        findings.append(_payload_to_finding(payload))
    return findings


def _payload_to_finding(payload: dict[str, object]) -> Finding:
    """Reconstruct a Finding from the JSON envelope payload."""
    ev = payload["evidence_embedded"]
    assert isinstance(ev, dict)
    evidence = EvidenceEmbedded(
        expected_ledger_step=ev.get("expected_ledger_step") or {},  # type: ignore[arg-type]
        diff_summary=ev.get("diff_summary") or [],  # type: ignore[arg-type]
        transcript_excerpt=ev.get("transcript_excerpt") or [],  # type: ignore[arg-type]
    )
    created_str = payload["created"]
    assert isinstance(created_str, str)
    return Finding(
        id=str(payload["id"]),
        created=datetime.fromisoformat(created_str),
        run_id=str(payload["run_id"]),
        cycle=payload.get("cycle"),  # type: ignore[arg-type]
        axis=payload["axis"],  # type: ignore[arg-type]
        locus=payload["locus"],  # type: ignore[arg-type]
        severity=payload["severity"],  # type: ignore[arg-type]
        persona=str(payload["persona"]),
        capability_ref=str(payload["capability_ref"]),
        expected=str(payload["expected"]),
        observed=str(payload["observed"]),
        evidence_embedded=evidence,
        disambiguation=bool(payload.get("disambiguation", False)),
        low_confidence=bool(payload.get("low_confidence", False)),
        status=payload["status"],  # type: ignore[arg-type]
        route=payload["route"],  # type: ignore[arg-type]
        fix_commit=payload.get("fix_commit"),  # type: ignore[arg-type]
        alternative_fix=payload.get("alternative_fix"),  # type: ignore[arg-type]
    )
```

Also ensure `from datetime import datetime` is imported at the top of the file if it isn't already.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/investigator/test_backlog_findings.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Type-check**

Run: `mypy src/dazzle/fitness/backlog.py --ignore-missing-imports`
Expected: no errors in the new function

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/fitness/backlog.py tests/unit/fitness/investigator/__init__.py tests/unit/fitness/investigator/test_backlog_findings.py
git commit -m "feat(fitness): read_backlog_findings — reconstruct Finding from envelope JSON"
```

---

## Task 2: Proposal dataclasses (`ProposedFix`, `Proposal`, `ProposalStatus`)

**Files:**
- Create: `src/dazzle/fitness/investigator/__init__.py`
- Create: `src/dazzle/fitness/investigator/proposal.py`
- Test: `tests/unit/fitness/investigator/test_proposal.py` (new)

- [ ] **Step 1: Write the failing test for dataclass construction**

Create `tests/unit/fitness/investigator/test_proposal.py`:

```python
"""Tests for Proposal and ProposedFix dataclasses."""

from datetime import datetime, UTC

from dazzle.fitness.investigator.proposal import ProposedFix, Proposal


def _fix(file_path: str = "src/foo.py", diff: str = "--- a/src/foo.py\n+++ b/src/foo.py\n") -> ProposedFix:
    return ProposedFix(
        file_path=file_path,
        line_range=(10, 15),
        diff=diff,
        rationale="add the missing attribute",
        confidence=0.8,
    )


def test_proposed_fix_is_frozen() -> None:
    f = _fix()
    try:
        f.confidence = 0.9  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ProposedFix should be frozen")


def test_proposal_construction() -> None:
    p = Proposal(
        proposal_id="abc123",
        cluster_id="CL-deadbeef",
        created=datetime(2026, 4, 14, tzinfo=UTC),
        investigator_run_id="run-1",
        fixes=(_fix(),),
        overall_confidence=0.82,
        rationale="the reason we are doing this fix for real",
        alternatives_considered=("option A — rejected because X",),
        verification_plan="re-run Phase B against support_tickets with admin persona",
        evidence_paths=("src/foo.py",),
        tool_calls_summary=("read_file(src/foo.py)", "propose_fix(1 fixes)"),
        status="proposed",
    )
    assert p.cluster_id == "CL-deadbeef"
    assert p.fixes[0].file_path == "src/foo.py"
    assert p.status == "proposed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/investigator/test_proposal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.fitness.investigator'`

- [ ] **Step 3: Create the package and write minimal module**

Create `src/dazzle/fitness/investigator/__init__.py`:

```python
"""Dazzle fitness investigator subsystem.

See docs/superpowers/specs/2026-04-14-fitness-investigator-design.md
for the full design.
"""
```

Create `src/dazzle/fitness/investigator/proposal.py`:

```python
"""Proposal dataclasses and on-disk serialisation.

A Proposal is the investigator's terminal output — one per cluster per run.
Serialised as markdown with YAML frontmatter to
.dazzle/fitness-proposals/<cluster_id>-<proposal_id[:8]>.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ProposalStatus = Literal[
    "proposed",
    "applied",
    "verified",
    "reverted",
    "rejected",
]


@dataclass(frozen=True)
class ProposedFix:
    """A single-file fix inside a Proposal.

    Distinct from corrector.Fix (which is a multi-file bundle) — the
    investigator models one diff per file so the per-file rationale
    and confidence are meaningful.
    """

    file_path: str  # repo-relative
    line_range: tuple[int, int] | None
    diff: str  # unified diff anchored to file_path
    rationale: str  # one or two sentences; ≥1 char
    confidence: float  # 0.0..1.0


@dataclass(frozen=True)
class Proposal:
    """Terminal output of one investigator mission run."""

    proposal_id: str  # UUID4 hex
    cluster_id: str  # back-reference, e.g. "CL-a1b2c3d4"
    created: datetime  # UTC
    investigator_run_id: str  # DazzleAgent transcript anchor
    fixes: tuple[ProposedFix, ...]
    overall_confidence: float  # 0.0..1.0
    rationale: str  # ≥20 chars, the "why"
    alternatives_considered: tuple[str, ...]  # ≤5 lines
    verification_plan: str  # ≥20 chars
    evidence_paths: tuple[str, ...]  # repo-relative
    tool_calls_summary: tuple[str, ...]  # ordered
    status: ProposalStatus
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/investigator/test_proposal.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/investigator/__init__.py src/dazzle/fitness/investigator/proposal.py tests/unit/fitness/investigator/test_proposal.py
git commit -m "feat(investigator): ProposedFix + Proposal dataclasses"
```

---

## Task 3: Proposal validation, save, load, blocked artefacts

**Files:**
- Modify: `src/dazzle/fitness/investigator/proposal.py`
- Test: `tests/unit/fitness/investigator/test_proposal.py` (extend)
- New dependency: `PyYAML` — already in project deps (verify: `grep PyYAML pyproject.toml`). If missing, add to `[project]` dependencies and note in commit.

- [ ] **Step 1: Write the failing validation tests**

Append to `tests/unit/fitness/investigator/test_proposal.py`:

```python
from pathlib import Path

import pytest

from dazzle.fitness.investigator.proposal import (
    ProposalError,
    ProposalParseError,
    ProposalValidationError,
    ProposalWriteError,
    load_proposal,
    save_proposal,
    write_blocked_artefact,
)


def _valid_proposal(cluster_id: str = "CL-deadbeef", proposal_id: str = "abc12345ef678901") -> Proposal:
    return Proposal(
        proposal_id=proposal_id,
        cluster_id=cluster_id,
        created=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        investigator_run_id="run-1",
        fixes=(
            ProposedFix(
                file_path="src/foo.py",
                line_range=(10, 15),
                diff="--- a/src/foo.py\n+++ b/src/foo.py\n@@ -10,1 +10,1 @@\n-old\n+new\n",
                rationale="add the missing thing",
                confidence=0.85,
            ),
        ),
        overall_confidence=0.82,
        rationale="A sufficiently long rationale that passes the 20-character minimum check.",
        alternatives_considered=("option A — rejected because X",),
        verification_plan="Re-run Phase B against support_tickets; expect cluster to disappear.",
        evidence_paths=("src/foo.py",),
        tool_calls_summary=("read_file(src/foo.py)", "propose_fix(1 fixes)"),
        status="proposed",
    )


def test_save_proposal_happy_path(tmp_path: Path) -> None:
    proposal = _valid_proposal()
    path = save_proposal(
        proposal,
        tmp_path,
        case_file_text="# Case File\n\n(example)\n",
        investigation_log="Looked at src/foo.py; found the missing attribute.\n",
    )
    assert path.exists()
    assert path.name == f"{proposal.cluster_id}-{proposal.proposal_id[:8]}.md"
    assert path.parent == tmp_path / ".dazzle" / "fitness-proposals"

    loaded = load_proposal(path)
    assert loaded.cluster_id == proposal.cluster_id
    assert loaded.proposal_id == proposal.proposal_id
    assert loaded.overall_confidence == 0.82
    assert loaded.status == "proposed"
    assert len(loaded.fixes) == 1
    assert loaded.fixes[0].file_path == "src/foo.py"


def test_save_proposal_rejects_empty_fixes(tmp_path: Path) -> None:
    p = _valid_proposal()
    empty = Proposal(**{**p.__dict__, "fixes": ()})
    with pytest.raises(ProposalValidationError, match="fixes"):
        save_proposal(empty, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_short_rationale(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "rationale": "too short"})
    with pytest.raises(ProposalValidationError, match="rationale"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_short_verification_plan(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "verification_plan": "nope"})
    with pytest.raises(ProposalValidationError, match="verification_plan"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_out_of_range_confidence(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "overall_confidence": 1.5})
    with pytest.raises(ProposalValidationError, match="confidence"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_bad_cluster_id(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad = Proposal(**{**p.__dict__, "cluster_id": "not-a-cluster-id"})
    with pytest.raises(ProposalValidationError, match="cluster_id"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_diff_path_mismatch(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad_fix = ProposedFix(
        file_path="src/foo.py",
        line_range=(10, 15),
        diff="--- a/src/bar.py\n+++ b/src/bar.py\n",  # wrong path
        rationale="whatever",
        confidence=0.8,
    )
    bad = Proposal(**{**p.__dict__, "fixes": (bad_fix,)})
    with pytest.raises(ProposalValidationError, match="diff"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_too_many_alternatives(tmp_path: Path) -> None:
    p = _valid_proposal()
    too_many = tuple(f"alt {i}" for i in range(6))
    bad = Proposal(**{**p.__dict__, "alternatives_considered": too_many})
    with pytest.raises(ProposalValidationError, match="alternatives"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_rejects_traversal_fix_path(tmp_path: Path) -> None:
    p = _valid_proposal()
    bad_fix = ProposedFix(
        file_path="../../etc/passwd",
        line_range=None,
        diff="--- a/../../etc/passwd\n+++ b/../../etc/passwd\n",
        rationale="no",
        confidence=0.1,
    )
    bad = Proposal(**{**p.__dict__, "fixes": (bad_fix,)})
    with pytest.raises(ProposalValidationError, match="traversal|escape"):
        save_proposal(bad, tmp_path, case_file_text="", investigation_log="")


def test_save_proposal_collision_raises(tmp_path: Path) -> None:
    p = _valid_proposal()
    save_proposal(p, tmp_path, case_file_text="", investigation_log="")
    with pytest.raises(ProposalWriteError, match="already exists"):
        save_proposal(p, tmp_path, case_file_text="", investigation_log="")


def test_write_blocked_artefact(tmp_path: Path) -> None:
    path = write_blocked_artefact(
        cluster_id="CL-abcdef12",
        dazzle_root=tmp_path,
        reason="step_cap",
        case_file_text="# Case File\n(example)\n",
        transcript="step 1 ... step 25",
    )
    assert path.exists()
    assert path.name == "CL-abcdef12.md"
    assert path.parent == tmp_path / ".dazzle" / "fitness-proposals" / "_blocked"
    content = path.read_text()
    assert "step_cap" in content
    assert "# Case File" in content


def test_load_proposal_malformed_frontmatter(tmp_path: Path) -> None:
    proposals_dir = tmp_path / ".dazzle" / "fitness-proposals"
    proposals_dir.mkdir(parents=True)
    bad = proposals_dir / "CL-deadbeef-12345678.md"
    bad.write_text("no frontmatter here\n")
    with pytest.raises(ProposalParseError):
        load_proposal(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/investigator/test_proposal.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_proposal' from ...`

- [ ] **Step 3: Extend `src/dazzle/fitness/investigator/proposal.py`**

Append to `src/dazzle/fitness/investigator/proposal.py`:

```python
import re
from pathlib import Path
from typing import Any

import yaml


class ProposalError(Exception):
    """Base for all proposal errors."""


class ProposalValidationError(ProposalError):
    """Raised when a Proposal violates its schema or content rules."""


class ProposalWriteError(ProposalError):
    """Raised when writing a proposal to disk fails (collision, permissions)."""


class ProposalParseError(ProposalError):
    """Raised when loading a proposal file with malformed frontmatter."""


_CLUSTER_ID_RE = re.compile(r"^CL-[0-9a-f]{8,}$")
_DIFF_PATH_RE = re.compile(r"^---\s+a/(?P<a_path>\S+)\s*$", re.MULTILINE)


def _proposals_dir(dazzle_root: Path) -> Path:
    return dazzle_root / ".dazzle" / "fitness-proposals"


def _blocked_dir(dazzle_root: Path) -> Path:
    return _proposals_dir(dazzle_root) / "_blocked"


def _validate(proposal: Proposal, dazzle_root: Path) -> None:
    """Apply all validation rules. Raises ProposalValidationError on any failure."""
    if not proposal.fixes:
        raise ProposalValidationError("fixes must be non-empty")
    if len(proposal.alternatives_considered) > 5:
        raise ProposalValidationError(
            f"alternatives_considered: max 5 entries, got {len(proposal.alternatives_considered)}"
        )
    if len(proposal.verification_plan) < 20:
        raise ProposalValidationError(
            f"verification_plan too short (min 20 chars, got {len(proposal.verification_plan)})"
        )
    if len(proposal.rationale) < 20:
        raise ProposalValidationError(
            f"rationale too short (min 20 chars, got {len(proposal.rationale)})"
        )
    if not _CLUSTER_ID_RE.match(proposal.cluster_id):
        raise ProposalValidationError(
            f"cluster_id must match ^CL-[0-9a-f]{{8,}}$, got {proposal.cluster_id!r}"
        )
    if not (0.0 <= proposal.overall_confidence <= 1.0):
        raise ProposalValidationError(
            f"overall_confidence out of range [0,1]: {proposal.overall_confidence}"
        )
    root_resolved = dazzle_root.resolve()
    for idx, fix in enumerate(proposal.fixes):
        if not (0.0 <= fix.confidence <= 1.0):
            raise ProposalValidationError(
                f"fix[{idx}].confidence out of range [0,1]: {fix.confidence}"
            )
        # Diff parses as unified diff and path matches
        m = _DIFF_PATH_RE.search(fix.diff)
        if not m:
            raise ProposalValidationError(
                f"fix[{idx}].diff is not a valid unified diff (no --- a/<path> line)"
            )
        a_path = m.group("a_path")
        if a_path != fix.file_path:
            raise ProposalValidationError(
                f"fix[{idx}].diff path {a_path!r} does not match file_path {fix.file_path!r}"
            )
        # Traversal guard: resolve the proposed path against dazzle_root and
        # verify it stays inside the repo root. Use the unresolved path first
        # so obviously-bad inputs like '../../etc/passwd' are caught cleanly.
        try:
            target = (dazzle_root / fix.file_path).resolve()
            target.relative_to(root_resolved)
        except ValueError:
            raise ProposalValidationError(
                f"fix[{idx}].file_path escapes dazzle_root (traversal): {fix.file_path!r}"
            )


def save_proposal(
    proposal: Proposal,
    dazzle_root: Path,
    *,
    case_file_text: str,
    investigation_log: str,
) -> Path:
    """Validate, serialise, and write a Proposal. Returns the path written.

    Raises:
        ProposalValidationError: schema or content rule violated.
        ProposalWriteError: target file already exists or disk write fails.
    """
    _validate(proposal, dazzle_root)

    directory = _proposals_dir(dazzle_root)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{proposal.cluster_id}-{proposal.proposal_id[:8]}.md"
    target = directory / filename

    if target.exists():
        raise ProposalWriteError(f"proposal already exists: {target}")

    body = _serialise_proposal(proposal, case_file_text=case_file_text, investigation_log=investigation_log)

    try:
        target.write_text(body)
    except OSError as e:
        raise ProposalWriteError(f"failed to write {target}: {e}") from e
    return target


def _serialise_proposal(
    proposal: Proposal,
    *,
    case_file_text: str,
    investigation_log: str,
) -> str:
    """Render a Proposal as markdown with YAML frontmatter."""
    frontmatter: dict[str, Any] = {
        "proposal_id": proposal.proposal_id,
        "cluster_id": proposal.cluster_id,
        "created": proposal.created.isoformat(),
        "investigator_run_id": proposal.investigator_run_id,
        "overall_confidence": proposal.overall_confidence,
        "status": proposal.status,
        "rationale": proposal.rationale,
        "fixes": [
            {
                "file_path": f.file_path,
                "line_range": list(f.line_range) if f.line_range else None,
                "rationale": f.rationale,
                "confidence": f.confidence,
            }
            for f in proposal.fixes
        ],
        "verification_plan": proposal.verification_plan,
        "alternatives_considered": list(proposal.alternatives_considered),
        "evidence_paths": list(proposal.evidence_paths),
        "tool_calls_summary": list(proposal.tool_calls_summary),
    }

    # Emit diffs as a single fenced block in the body (YAML can't hold them cleanly).
    diff_block = "\n".join(f.diff.rstrip() for f in proposal.fixes)

    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False)
    return (
        "---\n"
        f"{yaml_text}"
        "---\n\n"
        "## Case file\n\n"
        f"{case_file_text.rstrip()}\n\n"
        "## Investigation log\n\n"
        f"{investigation_log.rstrip()}\n\n"
        "## Proposed diff\n\n"
        "```diff\n"
        f"{diff_block}\n"
        "```\n"
    )


def load_proposal(path: Path) -> Proposal:
    """Parse a proposal file back into a Proposal dataclass.

    Reads only the frontmatter; ignores the markdown body.
    """
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ProposalParseError(f"no frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ProposalParseError(f"unterminated frontmatter: {path}")
    try:
        fm = yaml.safe_load(text[4:end])
    except yaml.YAMLError as e:
        raise ProposalParseError(f"malformed frontmatter: {e}") from e
    if not isinstance(fm, dict):
        raise ProposalParseError(f"frontmatter not a dict: {path}")

    try:
        fixes = tuple(
            ProposedFix(
                file_path=str(f["file_path"]),
                line_range=tuple(f["line_range"]) if f.get("line_range") else None,  # type: ignore[arg-type]
                diff="",  # body-only; load_proposal does not reconstruct diff text
                rationale=str(f["rationale"]),
                confidence=float(f["confidence"]),
            )
            for f in fm["fixes"]
        )
        return Proposal(
            proposal_id=str(fm["proposal_id"]),
            cluster_id=str(fm["cluster_id"]),
            created=datetime.fromisoformat(fm["created"]),
            investigator_run_id=str(fm["investigator_run_id"]),
            fixes=fixes,
            overall_confidence=float(fm["overall_confidence"]),
            rationale=str(fm["rationale"]),
            alternatives_considered=tuple(fm.get("alternatives_considered") or ()),
            verification_plan=str(fm["verification_plan"]),
            evidence_paths=tuple(fm.get("evidence_paths") or ()),
            tool_calls_summary=tuple(fm.get("tool_calls_summary") or ()),
            status=fm["status"],
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ProposalParseError(f"invalid proposal frontmatter: {e}") from e


def write_blocked_artefact(
    cluster_id: str,
    dazzle_root: Path,
    *,
    reason: str,
    case_file_text: str,
    transcript: str,
) -> Path:
    """Write a failure-case artefact under .dazzle/fitness-proposals/_blocked/."""
    directory = _blocked_dir(dazzle_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{cluster_id}.md"
    body = (
        f"# Blocked investigation: {cluster_id}\n\n"
        f"**Reason:** {reason}\n\n"
        "## Case file\n\n"
        f"{case_file_text.rstrip()}\n\n"
        "## Transcript\n\n"
        "```\n"
        f"{transcript.rstrip()}\n"
        "```\n"
    )
    path.write_text(body)
    return path
```

At the top of the file, add:

```python
from dazzle.fitness.investigator.proposal import ProposedFix, Proposal  # already defined above — ensure no circular import
```

(If you're appending within the same file, no import is needed — this note is only relevant if you split `_validate` and friends into a submodule.)

- [ ] **Step 4: Verify PyYAML is available**

Run: `python -c "import yaml; print(yaml.__version__)"`
Expected: prints a version (e.g. `6.0.2`). If it errors, add `"pyyaml>=6.0"` to `[project]` dependencies in `pyproject.toml` and run `pip install -e .` before continuing.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/investigator/test_proposal.py -v`
Expected: PASS (13 tests)

- [ ] **Step 6: Type-check**

Run: `mypy src/dazzle/fitness/investigator/proposal.py --ignore-missing-imports`
Expected: clean or only pre-existing unrelated errors

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/fitness/investigator/proposal.py tests/unit/fitness/investigator/test_proposal.py
git commit -m "feat(investigator): Proposal save/load/validate + blocked artefact writer"
```

---

## Task 4: `AttemptedIndex` — rebuildable idempotence cache

**Files:**
- Create: `src/dazzle/fitness/investigator/attempted.py`
- Test: `tests/unit/fitness/investigator/test_attempted.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/fitness/investigator/test_attempted.py`:

```python
"""Tests for AttemptedIndex — the rebuildable idempotence cache."""

from datetime import datetime, UTC
from pathlib import Path

from dazzle.fitness.investigator.attempted import (
    AttemptedEntry,
    AttemptedIndex,
    load_attempted,
    mark_attempted,
    rebuild_attempted,
    save_attempted,
)
from dazzle.fitness.investigator.proposal import (
    Proposal,
    ProposedFix,
    save_proposal,
    write_blocked_artefact,
)


def _proposal(cluster_id: str = "CL-deadbeef", proposal_id: str = "abc12345ef678901") -> Proposal:
    return Proposal(
        proposal_id=proposal_id,
        cluster_id=cluster_id,
        created=datetime(2026, 4, 14, tzinfo=UTC),
        investigator_run_id="run-1",
        fixes=(
            ProposedFix(
                file_path="src/foo.py",
                line_range=(1, 2),
                diff="--- a/src/foo.py\n+++ b/src/foo.py\n",
                rationale="y",
                confidence=0.9,
            ),
        ),
        overall_confidence=0.9,
        rationale="A sufficiently long rationale for validation purposes here.",
        alternatives_considered=(),
        verification_plan="Re-run Phase B and look for cluster disappearance.",
        evidence_paths=(),
        tool_calls_summary=(),
        status="proposed",
    )


def test_load_attempted_missing_file_rebuilds_from_disk(tmp_path: Path) -> None:
    save_proposal(_proposal(), tmp_path, case_file_text="", investigation_log="")

    index = load_attempted(tmp_path)
    assert "CL-deadbeef" in index.clusters
    assert index.clusters["CL-deadbeef"].status == "proposed"
    assert "abc12345ef678901" in index.clusters["CL-deadbeef"].proposal_ids


def test_mark_attempted_updates_entry(tmp_path: Path) -> None:
    index = AttemptedIndex(clusters={})
    mark_attempted(index, "CL-cafef00d", proposal_id="deadbeef11112222", status="proposed")
    assert index.clusters["CL-cafef00d"].proposal_ids == ["deadbeef11112222"]
    assert index.clusters["CL-cafef00d"].status == "proposed"


def test_save_load_round_trip(tmp_path: Path) -> None:
    index = AttemptedIndex(
        clusters={
            "CL-11112222": AttemptedEntry(
                proposal_ids=["p1"],
                last_attempt=datetime(2026, 4, 14, tzinfo=UTC),
                status="proposed",
            ),
        }
    )
    save_attempted(index, tmp_path)

    reloaded = load_attempted(tmp_path)
    assert "CL-11112222" in reloaded.clusters
    assert reloaded.clusters["CL-11112222"].status == "proposed"


def test_rebuild_from_blocked_artefact(tmp_path: Path) -> None:
    write_blocked_artefact(
        "CL-33334444",
        tmp_path,
        reason="step_cap",
        case_file_text="",
        transcript="",
    )
    index = rebuild_attempted(tmp_path)
    assert "CL-33334444" in index.clusters
    assert index.clusters["CL-33334444"].status == "blocked"


def test_load_attempted_handles_corrupt_index(tmp_path: Path) -> None:
    proposals_dir = tmp_path / ".dazzle" / "fitness-proposals"
    proposals_dir.mkdir(parents=True)
    (proposals_dir / "_attempted.json").write_text("not valid json {")

    # Should silently rebuild from disk
    index = load_attempted(tmp_path)
    assert isinstance(index, AttemptedIndex)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/investigator/test_attempted.py -v`
Expected: FAIL — `ModuleNotFoundError: ... attempted`

- [ ] **Step 3: Implement `attempted.py`**

Create `src/dazzle/fitness/investigator/attempted.py`:

```python
"""Rebuildable idempotence cache for the investigator.

.dazzle/fitness-proposals/_attempted.json tracks which clusters have been
investigated. It is a write-through cache, not an authoritative store — if
deleted or corrupt, load_attempted rebuilds from the proposal files on disk.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal

from dazzle.fitness.investigator.proposal import (
    ProposalParseError,
    ProposalStatus,
    load_proposal,
)

AttemptStatus = ProposalStatus | Literal["blocked"]


@dataclass
class AttemptedEntry:
    proposal_ids: list[str] = field(default_factory=list)
    last_attempt: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: AttemptStatus = "proposed"


@dataclass
class AttemptedIndex:
    clusters: dict[str, AttemptedEntry] = field(default_factory=dict)


def _index_path(dazzle_root: Path) -> Path:
    return dazzle_root / ".dazzle" / "fitness-proposals" / "_attempted.json"


def load_attempted(dazzle_root: Path) -> AttemptedIndex:
    """Load the index; rebuild from disk if missing or corrupt."""
    path = _index_path(dazzle_root)
    if not path.exists():
        return rebuild_attempted(dazzle_root)
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return rebuild_attempted(dazzle_root)
    if not isinstance(raw, dict):
        return rebuild_attempted(dazzle_root)
    return _deserialise(raw)


def save_attempted(index: AttemptedIndex, dazzle_root: Path) -> None:
    """Atomic write via tempfile + rename."""
    path = _index_path(dazzle_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _serialise(index)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False, suffix=".tmp"
    ) as tf:
        json.dump(data, tf, indent=2, sort_keys=True)
        tmp_name = tf.name
    Path(tmp_name).replace(path)


def rebuild_attempted(dazzle_root: Path) -> AttemptedIndex:
    """Scan .dazzle/fitness-proposals/ and _blocked/ to reconstruct the index."""
    index = AttemptedIndex(clusters={})
    proposals_dir = dazzle_root / ".dazzle" / "fitness-proposals"
    if not proposals_dir.exists():
        return index

    # Top-level proposal files
    for path in sorted(proposals_dir.glob("CL-*.md")):
        try:
            proposal = load_proposal(path)
        except ProposalParseError:
            continue
        entry = index.clusters.setdefault(proposal.cluster_id, AttemptedEntry())
        entry.proposal_ids.append(proposal.proposal_id)
        entry.last_attempt = max(entry.last_attempt, proposal.created)
        entry.status = proposal.status

    # Blocked artefacts
    blocked_dir = proposals_dir / "_blocked"
    if blocked_dir.exists():
        for path in sorted(blocked_dir.glob("CL-*.md")):
            cluster_id = path.stem
            entry = index.clusters.setdefault(cluster_id, AttemptedEntry())
            if not entry.proposal_ids:  # only mark blocked if no successful proposal exists
                entry.status = "blocked"
                entry.last_attempt = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    return index


def mark_attempted(
    index: AttemptedIndex,
    cluster_id: str,
    *,
    proposal_id: str | None,
    status: AttemptStatus,
) -> None:
    """Update an entry in-place. Caller is responsible for calling save_attempted."""
    entry = index.clusters.setdefault(cluster_id, AttemptedEntry())
    if proposal_id is not None and proposal_id not in entry.proposal_ids:
        entry.proposal_ids.append(proposal_id)
    entry.last_attempt = datetime.now(UTC)
    entry.status = status


def _serialise(index: AttemptedIndex) -> dict[str, dict[str, object]]:
    return {
        cluster_id: {
            "proposal_ids": entry.proposal_ids,
            "last_attempt": entry.last_attempt.isoformat(),
            "status": entry.status,
        }
        for cluster_id, entry in index.clusters.items()
    }


def _deserialise(raw: dict[str, object]) -> AttemptedIndex:
    index = AttemptedIndex(clusters={})
    for cluster_id, data in raw.items():
        if not isinstance(data, dict):
            continue
        try:
            index.clusters[cluster_id] = AttemptedEntry(
                proposal_ids=list(data.get("proposal_ids") or []),  # type: ignore[arg-type]
                last_attempt=datetime.fromisoformat(str(data["last_attempt"])),
                status=data["status"],  # type: ignore[arg-type]
            )
        except (KeyError, ValueError, TypeError):
            continue
    return index
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/investigator/test_attempted.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Type-check**

Run: `mypy src/dazzle/fitness/investigator/attempted.py --ignore-missing-imports`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/fitness/investigator/attempted.py tests/unit/fitness/investigator/test_attempted.py
git commit -m "feat(investigator): AttemptedIndex rebuildable idempotence cache"
```

---

## Task 5: `LocusExcerpt` + `CaseFile` dataclasses + happy-path `build_case_file`

**Files:**
- Create: `src/dazzle/fitness/investigator/case_file.py`
- Test: `tests/unit/fitness/investigator/test_case_file.py` (new)

This task covers the dataclasses and the first-pass builder: load sample, collect siblings (up to 5, simple sort order — diversity picker is Task 6), load locus file as `mode="full"` when small (windowing is Task 7).

- [ ] **Step 1: Write the failing happy-path test**

Create `tests/unit/fitness/investigator/test_case_file.py`:

```python
"""Tests for build_case_file and CaseFile dataclasses."""

from datetime import datetime, UTC
from pathlib import Path

import pytest

from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.investigator.case_file import (
    BacklogReader,
    CaseFile,
    CaseFileBuildError,
    CaseFileTraversalError,
    LocusExcerpt,
    build_case_file,
)
from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.triage import Cluster


def _finding(
    fid: str,
    *,
    persona: str = "admin",
    summary_observed: str = "aria-describedby missing",
    evidence_text: str = "line 47: control has no describedby",
) -> Finding:
    return Finding(
        id=fid,
        created=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        run_id="run-1",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="high",
        persona=persona,
        capability_ref="Ticket.create",
        expected="error announced via aria-describedby",
        observed=summary_observed,
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"step": 1, "description": "check aria"},
            diff_summary=[],
            transcript_excerpt=[{"kind": "observe", "text": evidence_text}],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def _cluster(
    locus: str = "src/dazzle_ui/templates/form.html",
    sample_id: str = "f_001",
    cluster_size: int = 3,
) -> Cluster:
    return Cluster(
        cluster_id="CL-deadbeef",
        locus=locus,
        axis="coverage",
        canonical_summary="aria-describedby missing",
        persona="admin",
        severity="high",
        cluster_size=cluster_size,
        first_seen=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        last_seen=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        sample_id=sample_id,
    )


def test_build_case_file_happy_path(tmp_path: Path) -> None:
    # Arrange: create a fake dazzle_root with a backlog and a small locus file
    (tmp_path / "dev_docs").mkdir()
    backlog_path = tmp_path / "dev_docs" / "fitness-backlog.md"
    upsert_findings(
        backlog_path,
        [
            _finding("f_001", summary_observed="describedby missing on control"),
            _finding("f_002", persona="admin", summary_observed="describedby missing (variant 2)"),
        ],
    )

    locus_dir = tmp_path / "src" / "dazzle_ui" / "templates"
    locus_dir.mkdir(parents=True)
    locus_file = locus_dir / "form.html"
    locus_file.write_text(
        "\n".join(f"<div>line {i}</div>" for i in range(1, 21))
    )

    # Act
    case_file = build_case_file(_cluster(), tmp_path)

    # Assert
    assert case_file.cluster.cluster_id == "CL-deadbeef"
    assert case_file.sample_finding.id == "f_001"
    assert len(case_file.siblings) == 1
    assert case_file.siblings[0].id == "f_002"
    assert case_file.locus is not None
    assert case_file.locus.mode == "full"
    assert case_file.locus.total_lines == 20
    assert case_file.dazzle_root == tmp_path


def test_build_case_file_missing_sample(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    # Empty backlog
    (tmp_path / "dev_docs" / "fitness-backlog.md").write_text("# empty\n")

    with pytest.raises(CaseFileBuildError, match="sample"):
        build_case_file(_cluster(), tmp_path)


def test_build_case_file_missing_locus_file_is_not_error(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001")],
    )
    # Locus file does not exist on disk; builder must not raise
    case_file = build_case_file(_cluster(locus="does/not/exist.html"), tmp_path)
    assert case_file.locus is None


def test_build_case_file_traversal_guard(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001")],
    )
    with pytest.raises(CaseFileTraversalError):
        build_case_file(_cluster(locus="../../../etc/passwd"), tmp_path)


def test_build_case_file_example_root_detection(tmp_path: Path) -> None:
    """When locus starts with examples/<name>/, example_root is set."""
    example_dir = tmp_path / "examples" / "support_tickets" / "dev_docs"
    example_dir.mkdir(parents=True)
    upsert_findings(
        example_dir / "fitness-backlog.md",
        [_finding("f_001")],
    )
    locus_file = tmp_path / "examples" / "support_tickets" / "dsl" / "entities" / "ticket.dsl"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("entity Ticket: id uuid pk\n")

    case_file = build_case_file(
        _cluster(locus="examples/support_tickets/dsl/entities/ticket.dsl"),
        tmp_path,
    )
    assert case_file.example_root == tmp_path / "examples" / "support_tickets"
    assert case_file.sample_finding.id == "f_001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.fitness.investigator.case_file'`

- [ ] **Step 3: Implement `case_file.py`**

Create `src/dazzle/fitness/investigator/case_file.py`:

```python
"""CaseFile — deterministic seed context for one investigator mission run.

Given a Cluster and the repo root, build_case_file produces a CaseFile
containing: the sample Finding, up to 5 siblings, and the locus file
(full content if ≤ 500 lines, windowed otherwise). No LLM calls, no
mutation — pure function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal, Protocol

from dazzle.fitness.backlog import read_backlog_findings
from dazzle.fitness.models import Finding
from dazzle.fitness.triage import Cluster, canonicalize_summary

LOCUS_FULL_MAX_LINES = 500
LOCUS_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOCUS_BINARY_SNIFF_BYTES = 1024
SIBLING_LIMIT = 5


class CaseFileBuildError(Exception):
    """Raised when the case file cannot be built."""


class CaseFileTraversalError(CaseFileBuildError):
    """Raised specifically when cluster.locus escapes dazzle_root."""


class BacklogReader(Protocol):
    """Test seam — tests inject a fake to avoid writing real backlog files."""

    def findings_in(self, path: Path) -> list[Finding]: ...


class _DefaultBacklogReader:
    def findings_in(self, path: Path) -> list[Finding]:
        return read_backlog_findings(path)


@dataclass(frozen=True)
class LocusExcerpt:
    file_path: str  # repo-relative
    total_lines: int
    mode: Literal["full", "windowed"]
    chunks: tuple[tuple[int, int, str], ...]  # (start_line, end_line, text), 1-indexed inclusive


@dataclass(frozen=True)
class CaseFile:
    cluster: Cluster
    sample_finding: Finding
    siblings: tuple[Finding, ...]
    locus: LocusExcerpt | None
    dazzle_root: Path
    example_root: Path | None
    built_at: datetime  # informational only, NOT used for determinism

    def to_prompt_text(self) -> str:
        """Render the case file as a single text block for the system prompt.

        Full implementation added in Task 8.
        """
        return ""  # stub — overridden in Task 8


def build_case_file(
    cluster: Cluster,
    dazzle_root: Path,
    *,
    backlog_reader: BacklogReader | None = None,
) -> CaseFile:
    """Deterministic case file builder. Pure function; no LLM, no mutation."""
    reader = backlog_reader or _DefaultBacklogReader()
    root_resolved = dazzle_root.resolve()

    # 1. Resolve example root
    example_root = _resolve_example_root(cluster.locus, dazzle_root)

    # 2. Load the sample finding
    sample, sample_source = _load_sample(cluster, dazzle_root, example_root, reader)
    if sample is None:
        raise CaseFileBuildError(
            f"sample finding {cluster.sample_id!r} not in any backlog"
        )

    # 3. Load sibling candidates from the same backlog file
    all_findings = reader.findings_in(sample_source)
    siblings = _pick_siblings(cluster, sample, all_findings)

    # 4. Load locus file (traversal-guarded)
    locus = _load_locus(cluster.locus, dazzle_root, root_resolved, sample, siblings)

    return CaseFile(
        cluster=cluster,
        sample_finding=sample,
        siblings=tuple(siblings),
        locus=locus,
        dazzle_root=dazzle_root,
        example_root=example_root,
        built_at=datetime.now(UTC),
    )


def _resolve_example_root(locus: str, dazzle_root: Path) -> Path | None:
    parts = locus.split("/", 2)
    if len(parts) >= 2 and parts[0] == "examples":
        return dazzle_root / "examples" / parts[1]
    return None


def _load_sample(
    cluster: Cluster,
    dazzle_root: Path,
    example_root: Path | None,
    reader: BacklogReader,
) -> tuple[Finding | None, Path]:
    """Try example-scoped backlog first, then repo-scoped. Returns (finding, source_path)."""
    candidate_sources: list[Path] = []
    if example_root is not None:
        candidate_sources.append(example_root / "dev_docs" / "fitness-backlog.md")
    candidate_sources.append(dazzle_root / "dev_docs" / "fitness-backlog.md")

    for source in candidate_sources:
        findings = reader.findings_in(source)
        for f in findings:
            if f.id == cluster.sample_id:
                return f, source
    # Return the first candidate source path even on miss so callers have
    # something to report; the caller will raise anyway.
    return None, candidate_sources[0]


def _pick_siblings(
    cluster: Cluster,
    sample: Finding,
    all_findings: list[Finding],
) -> list[Finding]:
    """Stable sort-order picker. Diversity scoring is added in Task 6."""
    pool = [
        f
        for f in all_findings
        if f.id != sample.id
        and f.locus == cluster.locus
        and f.axis == cluster.axis
        and f.persona == cluster.persona
        and canonicalize_summary(_summary_text(f)) == cluster.canonical_summary
    ]
    pool.sort(key=lambda f: (f.persona, f.id))
    return pool[:SIBLING_LIMIT]


def _summary_text(f: Finding) -> str:
    """The finding's summary is derived from its observed text for clustering purposes."""
    return f.observed


def _load_locus(
    locus_rel: str,
    dazzle_root: Path,
    root_resolved: Path,
    sample: Finding,
    siblings: list[Finding],
) -> LocusExcerpt | None:
    target = dazzle_root / locus_rel
    try:
        resolved = target.resolve()
    except (OSError, RuntimeError):
        return None

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise CaseFileTraversalError(
            f"locus {locus_rel!r} escapes dazzle_root {dazzle_root}"
        )

    if not resolved.exists() or not resolved.is_file():
        return None

    try:
        stat = resolved.stat()
    except OSError:
        return None
    if stat.st_size >= LOCUS_MAX_BYTES:
        return None

    try:
        head = resolved.read_bytes()[:LOCUS_BINARY_SNIFF_BYTES]
    except OSError:
        return None
    if b"\x00" in head:
        return None

    try:
        content = resolved.read_text()
    except (OSError, UnicodeDecodeError):
        return None

    lines = content.splitlines()
    total_lines = len(lines)

    if total_lines <= LOCUS_FULL_MAX_LINES:
        return LocusExcerpt(
            file_path=locus_rel,
            total_lines=total_lines,
            mode="full",
            chunks=((1, total_lines, content),),
        )

    # Windowed mode: Task 7 implements the chunk builder.
    # For now, return a stub single-chunk with the first 200 lines.
    head_text = "\n".join(lines[:200])
    return LocusExcerpt(
        file_path=locus_rel,
        total_lines=total_lines,
        mode="windowed",
        chunks=((1, min(200, total_lines), head_text),),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Type-check**

Run: `mypy src/dazzle/fitness/investigator/case_file.py --ignore-missing-imports`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/fitness/investigator/case_file.py tests/unit/fitness/investigator/test_case_file.py
git commit -m "feat(investigator): CaseFile dataclasses + build_case_file happy path"
```

---

## Task 6: Sibling diversity picker (Levenshtein-based)

**Files:**
- Modify: `src/dazzle/fitness/investigator/case_file.py` (`_pick_siblings`)
- Test: `tests/unit/fitness/investigator/test_case_file.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/fitness/investigator/test_case_file.py`:

```python
def test_sibling_picker_prefers_diverse_observed_text(tmp_path: Path) -> None:
    """Given 6 siblings with 3 identical observed texts and 3 distinct,
    the picker should return the 3 distinct first (after the initial sort-order pick)."""
    (tmp_path / "dev_docs").mkdir()
    findings = [
        _finding("f_000", summary_observed="describedby missing"),
        _finding("f_001", summary_observed="describedby missing"),  # dup of f_000
        _finding("f_002", summary_observed="describedby missing"),  # dup of f_000
        _finding("f_003", summary_observed="describedby absent from form control"),  # distinct
        _finding("f_004", summary_observed="no describedby wiring to error paragraph"),  # distinct
        _finding("f_005", summary_observed="error rendered as div role alert no describedby"),  # distinct
    ]
    upsert_findings(tmp_path / "dev_docs" / "fitness-backlog.md", findings)

    cluster = _cluster(cluster_size=6, sample_id="f_000")
    # Override the cluster's canonical_summary to match the raw observed texts.
    # (In real usage the canonicalizer handles this; tests may need a fake if
    # the real canonicalizer doesn't merge these — adjust accordingly in impl.)
    case_file = build_case_file(cluster, tmp_path)

    # sample is f_000; siblings picked from f_001..f_005
    # After sort-order baseline, diversity picker should prefer distinct observed
    sibling_ids = [s.id for s in case_file.siblings]
    assert "f_003" in sibling_ids or "f_004" in sibling_ids or "f_005" in sibling_ids
    # And should NOT return only the duplicates
    assert set(sibling_ids) != {"f_001", "f_002"}
```

Note: the diversity picker only kicks in when sample-id-order would pick duplicates. The assertion is deliberately loose — we're checking the picker reached diversity, not the exact permutation. This keeps the test robust to minor algorithm tweaks.

- [ ] **Step 2: Run test to verify it fails (or, more likely, passes trivially since canonicalize_summary collapses the variants)**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py::test_sibling_picker_prefers_diverse_observed_text -v`

The existing implementation's `canonicalize_summary` merges observed texts into the cluster — if all 6 test findings canonicalize to the same summary, the pool will be all 5 siblings and the sort-order pick will deterministically return f_001..f_005 (the distinct ones are at the end). That's already correct. If the test *passes* without modification, the diversity picker may not be needed — but implement it anyway for robustness on real data where texts have minor whitespace differences that survive canonicalization.

- [ ] **Step 3: Implement the Levenshtein picker**

Replace the `_pick_siblings` function in `src/dazzle/fitness/investigator/case_file.py`:

```python
def _pick_siblings(
    cluster: Cluster,
    sample: Finding,
    all_findings: list[Finding],
) -> list[Finding]:
    """Pick up to SIBLING_LIMIT siblings, preferring evidence-text diversity.

    Algorithm:
      1. Filter the pool to findings in the same cluster.
      2. Stable-sort by (persona, id) — baseline order.
      3. Pick the first as the seed.
      4. For each subsequent pick: score each remaining candidate by its
         minimum Levenshtein distance from any already-picked sibling's
         observed text. Pick the candidate with the highest minimum distance
         (most different from everything already picked). Ties break by
         baseline sort order.
    """
    pool = [
        f
        for f in all_findings
        if f.id != sample.id
        and f.locus == cluster.locus
        and f.axis == cluster.axis
        and f.persona == cluster.persona
        and canonicalize_summary(_summary_text(f)) == cluster.canonical_summary
    ]
    pool.sort(key=lambda f: (f.persona, f.id))
    if len(pool) <= SIBLING_LIMIT:
        return pool

    picked: list[Finding] = [pool[0]]
    remaining = pool[1:]
    while len(picked) < SIBLING_LIMIT and remaining:
        def min_distance(candidate: Finding) -> int:
            return min(_levenshtein(candidate.observed, p.observed) for p in picked)

        remaining.sort(key=lambda f: (-min_distance(f), (f.persona, f.id)))
        picked.append(remaining.pop(0))
    return picked


def _levenshtein(a: str, b: str) -> int:
    """Classic Wagner-Fischer edit distance. O(len(a)*len(b)) time and memory."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(
                curr[j - 1] + 1,       # insertion
                prev[j] + 1,           # deletion
                prev[j - 1] + cost,    # substitution
            )
        prev = curr
    return prev[-1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v`
Expected: PASS (all case_file tests, including existing ones)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/investigator/case_file.py tests/unit/fitness/investigator/test_case_file.py
git commit -m "feat(investigator): sibling diversity picker via Levenshtein distance"
```

---

## Task 7: Locus windowing (evidence line numbers → ±20 windows)

**Files:**
- Modify: `src/dazzle/fitness/investigator/case_file.py` (`_load_locus`)
- Test: `tests/unit/fitness/investigator/test_case_file.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/fitness/investigator/test_case_file.py`:

```python
def test_locus_windowing_large_file_with_evidence_lines(tmp_path: Path) -> None:
    """A large file (>500 lines) produces a windowed excerpt containing the
    first 200 lines plus ±20 windows around evidence-referenced line numbers."""
    (tmp_path / "dev_docs").mkdir()
    # Evidence references line 750 — windowing should include ~730..770
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", evidence_text="form.html:750 — missing describedby")],
    )

    locus_file = tmp_path / "src" / "ui" / "large.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1001)))

    cluster = _cluster(locus="src/ui/large.html")
    case_file = build_case_file(cluster, tmp_path)

    assert case_file.locus is not None
    assert case_file.locus.mode == "windowed"
    assert case_file.locus.total_lines == 1000

    # First chunk is the head
    head_chunk = case_file.locus.chunks[0]
    assert head_chunk[0] == 1
    assert head_chunk[1] == 200

    # Second chunk should cover ~730..770 (±20 around 750)
    window_chunks = [c for c in case_file.locus.chunks if c[0] > 200]
    assert window_chunks, "expected at least one evidence window beyond the head"
    assert any(c[0] <= 750 <= c[1] for c in window_chunks)


def test_locus_windowing_merges_overlapping_windows(tmp_path: Path) -> None:
    """Two evidence line numbers within ±20 of each other should merge into one chunk."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [
            _finding("f_001", evidence_text="form.html:750 here"),
            _finding("f_002", evidence_text="form.html:755 and here", summary_observed="describedby missing"),
        ],
    )

    locus_file = tmp_path / "src" / "ui" / "large.html"
    locus_file.parent.mkdir(parents=True)
    locus_file.write_text("\n".join(f"line {i}" for i in range(1, 1001)))

    case_file = build_case_file(_cluster(locus="src/ui/large.html"), tmp_path)
    assert case_file.locus is not None

    # Exactly one merged chunk covering both 750 and 755 (plus head chunk = 2 total)
    windows = [c for c in case_file.locus.chunks if c[0] > 200]
    assert len(windows) == 1
    assert windows[0][0] <= 750 <= windows[0][1]
    assert windows[0][0] <= 755 <= windows[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v -k windowing`
Expected: FAIL — the stub windowing returns only a single head chunk.

- [ ] **Step 3: Implement windowing**

At the top of `src/dazzle/fitness/investigator/case_file.py`, add:

```python
import re

_EVIDENCE_LINE_RE = re.compile(r"(?:line\s+|:)(\d+)")
LOCUS_HEAD_LINES = 200
LOCUS_WINDOW_RADIUS = 20
```

Replace the end of `_load_locus` (the "windowed mode" block at the bottom of the function) with:

```python
    # Windowed mode: head + ±20 windows around evidence-referenced line numbers.
    lines = content.splitlines()  # re-split for safety
    head_end = min(LOCUS_HEAD_LINES, total_lines)
    head_chunk = (1, head_end, "\n".join(lines[:head_end]))

    evidence_lines = _extract_evidence_lines(sample, siblings)
    raw_windows: list[tuple[int, int]] = []
    for line_no in evidence_lines:
        if line_no < 1 or line_no > total_lines:
            continue
        start = max(1, line_no - LOCUS_WINDOW_RADIUS)
        end = min(total_lines, line_no + LOCUS_WINDOW_RADIUS)
        raw_windows.append((start, end))

    merged = _merge_and_trim_windows(raw_windows, exclude_upto=head_end)

    chunks: list[tuple[int, int, str]] = [head_chunk]
    for start, end in merged:
        chunk_text = "\n".join(lines[start - 1 : end])
        chunks.append((start, end, chunk_text))

    return LocusExcerpt(
        file_path=locus_rel,
        total_lines=total_lines,
        mode="windowed",
        chunks=tuple(chunks),
    )
```

And add the helper functions at the bottom of the file:

```python
def _extract_evidence_lines(sample: Finding, siblings: list[Finding]) -> list[int]:
    """Pull line numbers out of evidence_embedded transcript excerpts.

    Matches patterns like 'line 47' and 'form.html:47'. Returns sorted unique ints.
    """
    seen: set[int] = set()
    for finding in [sample, *siblings]:
        for step in finding.evidence_embedded.transcript_excerpt:
            for value in step.values() if isinstance(step, dict) else []:
                if isinstance(value, str):
                    for match in _EVIDENCE_LINE_RE.finditer(value):
                        try:
                            seen.add(int(match.group(1)))
                        except ValueError:
                            continue
    return sorted(seen)


def _merge_and_trim_windows(
    raw: list[tuple[int, int]],
    *,
    exclude_upto: int,
) -> list[tuple[int, int]]:
    """Sort, clip to >exclude_upto, merge overlapping/adjacent windows."""
    # Trim to lines strictly after the head chunk
    trimmed = [(max(start, exclude_upto + 1), end) for start, end in raw if end > exclude_upto]
    trimmed = [(s, e) for s, e in trimmed if s <= e]
    if not trimmed:
        return []
    trimmed.sort()

    merged: list[tuple[int, int]] = [trimmed[0]]
    for start, end in trimmed[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v`
Expected: PASS (all case_file tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/investigator/case_file.py tests/unit/fitness/investigator/test_case_file.py
git commit -m "feat(investigator): locus windowing for large files"
```

---

## Task 8: `CaseFile.to_prompt_text`

**Files:**
- Modify: `src/dazzle/fitness/investigator/case_file.py` (`CaseFile.to_prompt_text`)
- Test: `tests/unit/fitness/investigator/test_case_file.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/fitness/investigator/test_case_file.py`:

```python
def test_to_prompt_text_structure(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001", summary_observed="describedby missing on control")],
    )
    locus_dir = tmp_path / "src" / "ui"
    locus_dir.mkdir(parents=True)
    (locus_dir / "form.html").write_text("<div>hello</div>\n<div>world</div>\n")

    case_file = build_case_file(_cluster(locus="src/ui/form.html"), tmp_path)
    text = case_file.to_prompt_text()

    # Section headers
    assert "# Case File" in text
    assert "## Cluster" in text
    assert "## Sample Finding" in text
    assert "## Locus File" in text

    # Cluster fields
    assert "CL-deadbeef" in text
    assert "src/ui/form.html" in text
    assert "persona: admin" in text
    assert "severity: high" in text

    # Sample finding shape
    assert "f_001" in text
    assert "describedby missing on control" in text

    # Locus content with line-number prefixes
    assert "  1: <div>hello</div>" in text
    assert "  2: <div>world</div>" in text


def test_to_prompt_text_locus_none_shows_note(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(
        tmp_path / "dev_docs" / "fitness-backlog.md",
        [_finding("f_001")],
    )
    # Missing locus file
    case_file = build_case_file(_cluster(locus="does/not/exist.html"), tmp_path)
    text = case_file.to_prompt_text()
    assert "Locus File" in text
    assert "file not found" in text or "not available" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v -k to_prompt_text`
Expected: FAIL — `to_prompt_text` returns empty string stub.

- [ ] **Step 3: Implement `to_prompt_text`**

Replace the `to_prompt_text` method on `CaseFile` in `src/dazzle/fitness/investigator/case_file.py`:

```python
    def to_prompt_text(self) -> str:
        lines: list[str] = ["# Case File", ""]

        # Cluster section
        lines += [
            "## Cluster",
            f"id: {self.cluster.cluster_id}",
            f"locus: {self.cluster.locus}",
            f"axis: {self.cluster.axis}",
            f"severity: {self.cluster.severity}",
            f"persona: {self.cluster.persona}",
            f"summary: \"{self.cluster.canonical_summary}\"",
            f"size: {self.cluster.cluster_size} findings",
            f"first_seen: {self.cluster.first_seen.isoformat()}",
            f"last_seen: {self.cluster.last_seen.isoformat()}",
            "",
        ]

        # Sample finding section
        lines += _render_finding_block(self.sample_finding, title_prefix="## Sample Finding")
        lines.append("")

        # Sibling findings section
        lines.append(f"## Sibling Findings ({len(self.siblings)} shown; cluster_size={self.cluster.cluster_size})")
        lines.append("")
        for sibling in self.siblings:
            lines += _render_finding_block(sibling, title_prefix="###")
            lines.append("")

        # Locus section
        if self.locus is None:
            lines += [
                f"## Locus File: {self.cluster.locus} (file not found / not available)",
                "",
            ]
        else:
            lines += [
                f"## Locus File: {self.locus.file_path} ({self.locus.total_lines} lines, mode={self.locus.mode})",
                "",
            ]
            prev_end = 0
            for start, end, text in self.locus.chunks:
                if prev_end and start > prev_end + 1:
                    lines.append(f"... (lines {prev_end + 1}..{start - 1} omitted)")
                    lines.append("")
                for offset, line_text in enumerate(text.splitlines(), start=start):
                    lines.append(f"  {offset}: {line_text}")
                prev_end = end
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"


def _render_finding_block(finding: Finding, *, title_prefix: str) -> list[str]:
    """Render one finding as prompt lines."""
    title = (
        f"{title_prefix} ({finding.id})"
        if title_prefix.startswith("##")
        else f"{title_prefix} {finding.id} (persona={finding.persona})"
    )
    evidence = _render_evidence(finding)
    return [
        title,
        f"created: {finding.created.isoformat()}",
        f"expected: \"{finding.expected}\"",
        f"observed: \"{finding.observed}\"",
        "evidence:",
        f"  {evidence}",
    ]


def _render_evidence(finding: Finding) -> str:
    """Flatten the evidence transcript excerpt into a short multi-line string."""
    parts: list[str] = []
    for step in finding.evidence_embedded.transcript_excerpt:
        if isinstance(step, dict):
            for k, v in step.items():
                if isinstance(v, str) and v:
                    parts.append(f"{k}: {v}")
    return "\n  ".join(parts) if parts else "(no evidence)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/fitness/investigator/test_case_file.py -v`
Expected: PASS (all case_file tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/investigator/case_file.py tests/unit/fitness/investigator/test_case_file.py
git commit -m "feat(investigator): CaseFile.to_prompt_text renderer"
```

---

*(Batches 3–5 continue below, appended in subsequent edits.)*
