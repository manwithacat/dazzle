"""CaseFile — deterministic seed context for one investigator mission run.

Given a Cluster and the repo root, build_case_file produces a CaseFile
containing: the sample Finding, up to 5 siblings, and a best-effort locus
file extracted from the sample's evidence transcript. No LLM calls, no
mutation — pure function.

Design note: ``Cluster.locus`` is the Finding.Locus enum kind
("implementation" / "story_drift" / "spec_stale" / "lifecycle"), NOT a
file path. To find the file the investigator should read, we extract a
candidate path from the sample finding's evidence_embedded transcript
excerpts using a regex. If no path is found or the path doesn't resolve
on disk, CaseFile.locus is None and the investigator's agent uses its
read_file / query_dsl tools to find files on its own.

Task 5: dataclasses + happy-path builder (sort-order sibling picker, full locus only).
Task 6: Levenshtein diversity picker.
Task 7: locus windowing for large files.
Task 8: to_prompt_text renderer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from dazzle.fitness.backlog import read_backlog_findings
from dazzle.fitness.models import Finding
from dazzle.fitness.triage import Cluster, canonicalize_summary

LOCUS_FULL_MAX_LINES = 500
LOCUS_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOCUS_BINARY_SNIFF_BYTES = 1024
SIBLING_LIMIT = 5

# Matches any path-like token starting with one or more ../ segments.
# Used by _check_evidence_for_traversal to eagerly detect escape attempts
# before the extension-filtered _FILE_PATH_RE even runs.
_TRAVERSAL_RE = re.compile(r"(?:(?<=[\s(\"'`])|^)(\.\./[\S]+)", re.MULTILINE)

# Matches a repo-relative path ending in a recognised extension, optionally
# followed by :line-number. First match in evidence text wins.
_FILE_PATH_RE = re.compile(
    r"(?:(?<=[\s(\"'`])|^)"  # boundary — start of line or whitespace/quote/paren
    r"(?P<path>"
    r"(?:\.\./|[a-zA-Z][\w./-]*/)"  # at least one directory segment (or leading ../)
    r"[\w._-]+"  # final filename segment (no slash)
    r"\.(?:py|html|js|ts|tsx|jsx|dsl|toml|md|yaml|yml|json|css|scss|j2|jinja|jinja2|sh)"
    r")"
    r"(?::\d+)?",  # optional :line-number (non-capturing, not part of path group)
    re.MULTILINE,
)


class CaseFileBuildError(Exception):
    """Raised when the case file cannot be built."""


class CaseFileTraversalError(CaseFileBuildError):
    """Raised specifically when the extracted locus path escapes dazzle_root."""


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
    chunks: tuple[tuple[int, int, str], ...]  # (start_line, end_line, text) 1-indexed inclusive


@dataclass(frozen=True)
class CaseFile:
    cluster: Cluster
    sample_finding: Finding
    siblings: tuple[Finding, ...]
    locus: LocusExcerpt | None
    dazzle_root: Path
    example_root: Path | None
    built_at: datetime  # informational only; NOT used for determinism

    def to_prompt_text(self) -> str:
        """Render the case file as a single text block for the system prompt.

        Full implementation added in Task 8. Stub for now.
        """
        return ""


def build_case_file(
    cluster: Cluster,
    dazzle_root: Path,
    *,
    backlog_reader: BacklogReader | None = None,
) -> CaseFile:
    """Deterministic case file builder. Pure function; no LLM, no mutation."""
    reader = backlog_reader or _DefaultBacklogReader()
    root_resolved = dazzle_root.resolve()

    # 1. Load the sample finding from either example-scoped or repo-scoped backlog
    sample, sample_source = _load_sample(cluster, dazzle_root, reader)
    if sample is None:
        raise CaseFileBuildError(f"sample finding {cluster.sample_id!r} not in any backlog")

    # 2. Eagerly reject any evidence containing path traversal sequences
    _check_evidence_for_traversal(sample, dazzle_root, root_resolved)

    # 3. Extract a candidate file path from the sample's evidence
    extracted_path = _extract_file_path(sample)

    # 4. Resolve example root from the extracted path (if any)
    example_root = _resolve_example_root(extracted_path, dazzle_root) if extracted_path else None

    # 5. Load siblings from the same backlog file the sample came from
    all_findings = reader.findings_in(sample_source)
    siblings = _pick_siblings(cluster, sample, all_findings)

    # 6. Load locus file (traversal-guarded)
    locus = _load_locus(extracted_path, dazzle_root, root_resolved) if extracted_path else None

    return CaseFile(
        cluster=cluster,
        sample_finding=sample,
        siblings=tuple(siblings),
        locus=locus,
        dazzle_root=dazzle_root,
        example_root=example_root,
        built_at=datetime.now(UTC),
    )


def _load_sample(
    cluster: Cluster,
    dazzle_root: Path,
    reader: BacklogReader,
) -> tuple[Finding | None, Path]:
    """Try repo-scoped backlog first, then every example's backlog.

    Since we don't yet know which example (if any) the finding belongs to,
    we search the repo-level backlog first, then fall back to scanning
    every example under examples/*/dev_docs/fitness-backlog.md.
    """
    repo_backlog = dazzle_root / "dev_docs" / "fitness-backlog.md"
    candidates: list[Path] = [repo_backlog]

    examples_dir = dazzle_root / "examples"
    if examples_dir.exists():
        for example in sorted(examples_dir.iterdir()):
            if example.is_dir():
                candidates.append(example / "dev_docs" / "fitness-backlog.md")

    for source in candidates:
        findings = reader.findings_in(source)
        for f in findings:
            if f.id == cluster.sample_id:
                return f, source
    return None, candidates[0]


def _check_evidence_for_traversal(
    finding: Finding,
    dazzle_root: Path,
    root_resolved: Path,
) -> None:
    """Scan all evidence text for ``../``-prefixed path tokens.

    If any such token resolves outside dazzle_root, raise CaseFileTraversalError
    immediately — before _extract_file_path's extension filter runs — so that
    traversal attempts with unknown extensions are still caught.
    """
    for step in finding.evidence_embedded.transcript_excerpt:
        if not isinstance(step, dict):
            continue
        for value in step.values():
            if not isinstance(value, str):
                continue
            for m in _TRAVERSAL_RE.finditer(value):
                # Strip any trailing :line-number for the path check
                raw = m.group(1).split(":")[0]
                target = dazzle_root / raw
                try:
                    resolved = target.resolve()
                    resolved.relative_to(root_resolved)
                except ValueError:
                    raise CaseFileTraversalError(
                        f"evidence contains traversal path {raw!r} that escapes dazzle_root"
                    )
                except (OSError, RuntimeError):
                    pass


def _extract_file_path(finding: Finding) -> str | None:
    """Heuristic: pull the first file-path-looking string from evidence_embedded text.

    Matches repo-relative paths with recognised extensions (py/html/js/dsl/etc.)
    optionally followed by :line-number. Returns the path portion only.
    """
    for step in finding.evidence_embedded.transcript_excerpt:
        if not isinstance(step, dict):
            continue
        for value in step.values():
            if not isinstance(value, str):
                continue
            m = _FILE_PATH_RE.search(value)
            if m:
                return m.group("path")
    return None


def _resolve_example_root(locus_rel: str, dazzle_root: Path) -> Path | None:
    parts = locus_rel.split("/", 2)
    if len(parts) >= 2 and parts[0] == "examples":
        return dazzle_root / "examples" / parts[1]
    return None


def _pick_siblings(
    cluster: Cluster,
    sample: Finding,
    all_findings: list[Finding],
) -> list[Finding]:
    """Simple stable sort-order picker. Diversity scoring is added in Task 6."""
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
    return f.observed


def _load_locus(
    locus_rel: str,
    dazzle_root: Path,
    root_resolved: Path,
) -> LocusExcerpt | None:
    target = dazzle_root / locus_rel
    try:
        resolved = target.resolve()
    except (OSError, RuntimeError):
        return None

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise CaseFileTraversalError(f"locus {locus_rel!r} escapes dazzle_root {dazzle_root}")

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

    # Task 7 implements windowed mode. For now, return a stub single-chunk.
    head_text = "\n".join(lines[:200])
    return LocusExcerpt(
        file_path=locus_rel,
        total_lines=total_lines,
        mode="windowed",
        chunks=((1, min(200, total_lines), head_text),),
    )
