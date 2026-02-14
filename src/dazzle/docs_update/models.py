"""Pydantic models for the docs-update pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class IssueCategory(StrEnum):
    """Classification of a closed GitHub issue for changelog purposes."""

    FEATURE = "feature"
    ENHANCEMENT = "enhancement"
    BUG_FIX = "bug_fix"
    DEPRECATION = "deprecation"
    INTERNAL = "internal"


# Map categories to Keep-a-Changelog section headers
CATEGORY_SECTIONS: dict[IssueCategory, str] = {
    IssueCategory.FEATURE: "### Added",
    IssueCategory.ENHANCEMENT: "### Changed",
    IssueCategory.BUG_FIX: "### Fixed",
    IssueCategory.DEPRECATION: "### Deprecated",
}


class ClosedIssue(BaseModel):
    """A closed GitHub issue with optional LLM-assigned metadata."""

    number: int
    title: str
    body: str = ""
    labels: list[str] = Field(default_factory=list)
    closed_at: str = ""
    url: str = ""

    # Set by LLM classification
    category: IssueCategory | None = None
    summary: str | None = None
    affected_docs: list[str] = Field(default_factory=list)


class DocPatch(BaseModel):
    """A proposed change to a documentation file."""

    target: str  # "changelog", "readme", "mkdocs"
    file_path: str
    section: str  # header being updated
    original: str
    proposed: str
    issues: list[int] = Field(default_factory=list)
    reason: str = ""


class UpdatePlan(BaseModel):
    """Summary of a docs-update run."""

    issues_scanned: int = 0
    issues_relevant: int = 0
    patches: list[DocPatch] = Field(default_factory=list)
    skipped_issues: list[int] = Field(default_factory=list)
    version: str = ""
