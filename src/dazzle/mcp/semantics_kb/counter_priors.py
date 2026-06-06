"""Counter-prior catalogue loader.

Counter-priors are markdown files under `docs/counter-priors/` that document
specific corpus pathologies Dazzle inoculates against. Each file carries
structured YAML frontmatter (id, layer, triggers) plus a body following a
predictable section structure (## The corpus prior / ## Wrong shape /
## Right shape / ## Why this matters here).

The markdown files are the source of truth. This module walks the directory,
parses each file, and returns structured `CounterPrior` records that the KG
seeder ingests at startup. The body markdown is included so MCP queries can
return it without a second filesystem read.

See `docs/counter-priors/INDEX.md` for the catalogue.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

Layer = Literal["grammar", "inference", "filter"]
Status = Literal["active", "deprecated", "draft"]

REQUIRED_SECTIONS = (
    "## The corpus prior",
    "## Wrong shape",
    "## Right shape",
    "## Why this matters here",
)


class CounterPriorRefs(BaseModel):
    """Structured references to related artefacts."""

    adrs: list[str] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)
    pr_review_agents: list[str] = Field(default_factory=list)
    kb_patterns: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)


class DetectorRef(BaseModel):
    """Pointer to a Sentinel heuristic that enforces this counter-prior."""

    id: str  # heuristic_id, e.g. "PA-LLM-07"
    agent: str  # AgentId code, e.g. "PA"
    note: str = ""  # optional clarification when coverage is partial


class CounterPrior(BaseModel):
    """One entry in the counter-prior catalogue."""

    id: str
    name: str
    layer: Layer
    status: Status = "active"
    summary: str
    triggers_text: list[str] = Field(default_factory=list)
    triggers_code: list[str] = Field(default_factory=list)
    refs: CounterPriorRefs = Field(default_factory=CounterPriorRefs)
    detectors: list[DetectorRef] = Field(default_factory=list)
    # Opt-in capability this antipattern is scoped to (#1342). None = always
    # relevant. When set, the proactive flag is suppressed unless the capability
    # is active — don't warn about a SAML pathology in a non-SAML app.
    capability: str | None = None

    file_path: str
    body: str

    @field_validator("id")
    @classmethod
    def _id_is_snake_case(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", v):
            raise ValueError(f"id must be snake_case ASCII: {v!r}")
        return v

    @field_validator("triggers_code")
    @classmethod
    def _code_triggers_are_valid_regex(cls, v: list[str]) -> list[str]:
        for pat in v:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"invalid regex in triggers_code: {pat!r} — {e}") from e
        return v


class CounterPriorParseError(Exception):
    """Raised when a counter-prior file is malformed."""


def counter_priors_dir() -> Path:
    """Resolve the on-disk location of the catalogue."""
    return Path(__file__).resolve().parents[3].parent / "docs" / "counter-priors"


def load_counter_prior(path: Path) -> CounterPrior:
    """Parse one counter-prior markdown file."""
    text = path.read_text()
    if not text.startswith("---\n"):
        raise CounterPriorParseError(f"{path}: no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise CounterPriorParseError(f"{path}: unterminated frontmatter")

    try:
        fm = yaml.safe_load(text[4:end])
    except yaml.YAMLError as e:
        raise CounterPriorParseError(f"{path}: malformed frontmatter — {e}") from e
    if not isinstance(fm, dict):
        raise CounterPriorParseError(f"{path}: frontmatter not a dict")

    body = text[end + len("\n---\n") :].lstrip("\n")

    expected_id = path.stem.replace("-", "_")
    if fm.get("id") != expected_id:
        raise CounterPriorParseError(
            f"{path}: frontmatter id {fm.get('id')!r} does not match filename "
            f"(expected {expected_id!r})"
        )

    missing = [s for s in REQUIRED_SECTIONS if s not in body]
    if missing:
        raise CounterPriorParseError(f"{path}: missing required sections: {', '.join(missing)}")

    try:
        return CounterPrior.model_validate(
            {
                **fm,
                "file_path": str(path),
                "body": body,
            }
        )
    except Exception as e:
        raise CounterPriorParseError(f"{path}: {e}") from e


def load_all_counter_priors(directory: Path | None = None) -> list[CounterPrior]:
    """Walk the catalogue directory and parse every entry.

    INDEX.md and any other non-entry files are skipped.
    """
    base = directory or counter_priors_dir()
    if not base.exists():
        return []

    entries: list[CounterPrior] = []
    for path in sorted(base.glob("*.md")):
        if path.name in ("INDEX.md", "README.md"):
            continue
        entries.append(load_counter_prior(path))
    return entries


def match_text_triggers(entries: list[CounterPrior], query: str) -> list[CounterPrior]:
    """Return entries whose triggers_text contains any case-insensitive fragment of query.

    Uses the same matching shape as #1249's spec_analyze.propose_patterns —
    case-insensitive substring against the trigger fragments.
    """
    q = query.lower()
    return [e for e in entries if any(t.lower() in q for t in e.triggers_text)]


def match_code_triggers(entries: list[CounterPrior], sample: str) -> list[CounterPrior]:
    """Return entries whose triggers_code regex matches the sample text.

    `sample` is typically a short description of what the agent is about to
    write (e.g. "sync handler that loops over related rows") or a fragment of
    code under review. Compiled regexes are cached by the CounterPrior model
    via field_validator; we just re-search here.
    """
    hits: list[CounterPrior] = []
    for entry in entries:
        for pat in entry.triggers_code:
            if re.search(pat, sample):
                hits.append(entry)
                break
    return hits
