"""Documentation update tools — LLM-powered doc sync from GitHub issues."""

from dazzle.docs_update.models import ClosedIssue, DocPatch, IssueCategory, UpdatePlan
from dazzle.docs_update.scanner import scan_closed_issues
from dazzle.docs_update.synthesizer import classify_issues, generate_patches
from dazzle.docs_update.updater import apply_patches, generate_diff

__all__ = [
    "ClosedIssue",
    "DocPatch",
    "IssueCategory",
    "UpdatePlan",
    "apply_patches",
    "classify_issues",
    "generate_diff",
    "generate_patches",
    "scan_closed_issues",
]
