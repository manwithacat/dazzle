"""Proposal dataclasses and on-disk serialisation.

A Proposal is the investigator's terminal output — one per cluster per run.
Serialised as markdown with YAML frontmatter to
.dazzle/fitness-proposals/<cluster_id>-<proposal_id[:8]>.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

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
    diff: str  # unified diff anchored to file_path; empty ("") when loaded from disk via load_proposal
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
    verification_plan: str  # ≥20 chars, what the actor should re-run and expect
    evidence_paths: tuple[str, ...]  # repo-relative
    tool_calls_summary: tuple[str, ...]  # ordered
    status: ProposalStatus


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
    if not _CLUSTER_ID_RE.match(proposal.cluster_id):
        raise ProposalValidationError(
            f"cluster_id must match ^CL-[0-9a-f]{{8,}}$, got {proposal.cluster_id!r}"
        )
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

    body = _serialise_proposal(
        proposal,
        case_file_text=case_file_text,
        investigation_log=investigation_log,
    )

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
                line_range=tuple(f["line_range"]) if f.get("line_range") else None,
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


def list_proposals(dazzle_root: Path, *, cluster_id: str | None = None) -> list[Proposal]:
    """Return all Proposal objects written to .dazzle/fitness-proposals/.

    If cluster_id is given, filter to proposals whose filename starts with that
    cluster_id. Proposals are returned sorted by filename (which encodes
    creation order via the UUID prefix). Files that fail to parse are silently
    skipped.
    """
    directory = _proposals_dir(dazzle_root)
    if not directory.exists():
        return []

    pattern = f"{cluster_id}-*.md" if cluster_id else "CL-*.md"
    proposals: list[Proposal] = []
    for path in sorted(directory.glob(pattern)):
        try:
            proposals.append(load_proposal(path))
        except ProposalParseError:
            continue
    return proposals


def write_blocked_artefact(
    cluster_id: str,
    dazzle_root: Path,
    *,
    reason: str,
    case_file_text: str,
    transcript: str,
) -> Path:
    """Write a .dazzle/fitness-proposals/_blocked/<cluster_id>.md artefact.

    Overwrites any existing blocked artefact for this cluster — the file
    represents the latest attempt, not a history. This is intentional:
    a cluster that blocks twice in a row should show the most recent
    transcript, not leave a stale record from an earlier run.
    """
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
