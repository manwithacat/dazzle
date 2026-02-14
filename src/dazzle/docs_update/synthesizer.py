"""LLM-powered classification and documentation patch generation."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from dazzle.docs_update.models import (
    ClosedIssue,
    DocPatch,
    IssueCategory,
)
from dazzle.docs_update.updater import (
    build_changelog_entries,
    ensure_unreleased_section,
    find_section,
    insert_after_header,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 1: classify issues
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """\
You are a release-notes assistant for the DAZZLE project, a DSL-first app framework.

Given a list of closed GitHub issues, classify each one and decide which documentation \
targets it affects.

Return ONLY valid JSON — an array of objects, one per issue:

[
  {
    "number": 123,
    "category": "feature|enhancement|bug_fix|deprecation|internal",
    "summary": "One-line changelog entry (imperative mood, no issue number)",
    "affected_docs": ["changelog", "readme", "mkdocs"]
  }
]

Categories:
- feature: wholly new capability (→ ### Added)
- enhancement: improvement to existing capability (→ ### Changed)
- bug_fix: defect correction (→ ### Fixed)
- deprecation: something marked for removal (→ ### Deprecated)
- internal: CI, refactoring, docs-only — skip from changelog

Rules:
- Every non-internal issue affects "changelog".
- Only issues that change user-facing behavior or add major features affect "readme".
- Issues that add new DSL constructs, CLI commands, or architecture changes affect "mkdocs".
- Summaries should be concise (< 100 chars), start with a verb, and describe the user impact.
"""


def _build_classify_prompt(issues: list[ClosedIssue]) -> str:
    items = []
    for issue in issues:
        body_preview = issue.body[:500] if issue.body else ""
        items.append(
            f"#{issue.number} — {issue.title}\n"
            f"Labels: {', '.join(issue.labels) or 'none'}\n"
            f"Body: {body_preview}\n"
        )
    return "Issues to classify:\n\n" + "\n---\n".join(items)


def classify_issues(
    issues: list[ClosedIssue],
    llm_complete: Callable[[str, str], str],
) -> list[ClosedIssue]:
    """Classify issues using the LLM and update their metadata in-place.

    Args:
        issues: List of :class:`ClosedIssue` to classify.
        llm_complete: A callable ``(system_prompt, user_prompt) -> str``.

    Returns:
        The same list, with ``category``, ``summary``, and ``affected_docs`` populated.
    """
    if not issues:
        return issues

    prompt = _build_classify_prompt(issues)
    raw = llm_complete(_CLASSIFY_SYSTEM, prompt)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]
    raw = raw.strip()

    try:
        classifications = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for classification: %s", raw[:300])
        return issues

    # Index issues by number for fast lookup
    by_number = {issue.number: issue for issue in issues}

    for item in classifications:
        number = item.get("number")
        issue = by_number.get(number)
        if issue is None:
            continue
        try:
            issue.category = IssueCategory(item.get("category", "internal"))
        except ValueError:
            issue.category = IssueCategory.INTERNAL
        issue.summary = item.get("summary", issue.title)
        issue.affected_docs = item.get("affected_docs", [])

    return issues


# ---------------------------------------------------------------------------
# Phase 2: generate patches
# ---------------------------------------------------------------------------

_CHANGELOG_SYSTEM = """\
You are a changelog writer for the DAZZLE project.

Given a set of classified issues and the current CHANGELOG.md content, generate the \
updated content for the ## [Unreleased] section ONLY.

Follow Keep a Changelog format with subsections: ### Added, ### Changed, ### Fixed, ### Deprecated.
Each entry should be: "- Summary text ([#N](url))"
Only include subsections that have entries.
Return ONLY the subsection text (no ## [Unreleased] header).
"""

_README_SYSTEM = """\
You are a technical writer for the DAZZLE project.

Given a specific section of README.md and a list of changes, update the section to \
reflect the new capabilities. Preserve the existing style, tone, and formatting.

Return ONLY the updated section body (not the header line).
"""

_MKDOCS_SYSTEM = """\
You are a documentation writer for the DAZZLE project.

Given a specific mkdocs page and a list of changes, update the page to reflect the \
new capabilities. Preserve the existing style and formatting.

Return ONLY the updated page content.
"""


def generate_patches(
    issues: list[ClosedIssue],
    targets: list[str],
    project_root: Path,
    llm_complete: Callable[[str, str], str],
) -> list[DocPatch]:
    """Generate documentation patches for classified issues.

    Args:
        issues: Classified issues (with ``category`` set).
        targets: Which targets to update (``changelog``, ``readme``, ``mkdocs``).
        project_root: Project root directory.
        llm_complete: A callable ``(system_prompt, user_prompt) -> str``.

    Returns:
        List of :class:`DocPatch` objects.
    """
    relevant = [i for i in issues if i.category and i.category != IssueCategory.INTERNAL]
    if not relevant:
        return []

    patches: list[DocPatch] = []

    if "changelog" in targets:
        patch = _patch_changelog(relevant, project_root, llm_complete)
        if patch:
            patches.append(patch)

    if "readme" in targets:
        readme_patches = _patch_readme(relevant, project_root, llm_complete)
        patches.extend(readme_patches)

    if "mkdocs" in targets:
        mkdocs_patches = _patch_mkdocs(relevant, project_root, llm_complete)
        patches.extend(mkdocs_patches)

    return patches


def _issue_list_prompt(issues: list[ClosedIssue]) -> str:
    """Format classified issues as context for the LLM."""
    lines = []
    for issue in issues:
        cat = issue.category.value if issue.category else "unknown"
        lines.append(f"- [{cat}] #{issue.number}: {issue.summary or issue.title} ({issue.url})")
    return "\n".join(lines)


def _patch_changelog(
    issues: list[ClosedIssue],
    project_root: Path,
    llm_complete: Callable[[str, str], str],
) -> DocPatch | None:
    changelog_path = project_root / "CHANGELOG.md"
    if not changelog_path.exists():
        return None

    original = changelog_path.read_text()
    content = ensure_unreleased_section(original)

    # Build deterministic entries as a fallback / seed
    issue_dicts = [
        {
            "category": i.category.value if i.category else "internal",
            "summary": i.summary or i.title,
            "number": str(i.number),
            "url": i.url,
        }
        for i in issues
    ]
    entries = build_changelog_entries(issue_dicts)

    if not entries.strip():
        return None

    # Use LLM to polish the entries
    user_prompt = (
        f"Current CHANGELOG (first 2000 chars):\n{content[:2000]}\n\n"
        f"Issues to add:\n{_issue_list_prompt(issues)}\n\n"
        f"Draft entries:\n{entries}\n\n"
        f"Polish these entries and return ONLY the subsection text for ## [Unreleased]."
    )

    try:
        polished = llm_complete(_CHANGELOG_SYSTEM, user_prompt).strip()
    except Exception:
        logger.warning("LLM polish failed for CHANGELOG, using deterministic entries")
        polished = entries

    # Strip markdown fences if present
    if polished.startswith("```"):
        polished = polished.split("\n", 1)[1] if "\n" in polished else polished[3:]
    if polished.endswith("```"):
        polished = polished[: polished.rfind("```")]
    polished = polished.strip()

    proposed = insert_after_header(content, "## [Unreleased]", "\n" + polished + "\n")

    return DocPatch(
        target="changelog",
        file_path=str(changelog_path),
        section="## [Unreleased]",
        original=original,
        proposed=proposed,
        issues=[i.number for i in issues],
        reason="Add entries for recently closed issues",
    )


def _patch_readme(
    issues: list[ClosedIssue],
    project_root: Path,
    llm_complete: Callable[[str, str], str],
) -> list[DocPatch]:
    readme_path = project_root / "README.md"
    if not readme_path.exists():
        return []

    readme_issues = [i for i in issues if "readme" in i.affected_docs]
    if not readme_issues:
        return []

    original = readme_path.read_text()

    user_prompt = (
        f"Current README.md:\n{original[:4000]}\n\n"
        f"Changes to reflect:\n{_issue_list_prompt(readme_issues)}\n\n"
        f"Identify which sections need updating and return a JSON array:\n"
        f'[{{"section": "Section Header", "updated_body": "new section body"}}]\n'
        f"Only include sections that genuinely need changes."
    )

    try:
        raw = llm_complete(_README_SYSTEM, user_prompt).strip()
    except Exception:
        logger.warning("LLM failed for README patches")
        return []

    # Strip markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]
    raw = raw.strip()

    try:
        updates = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for README patches: %s", raw[:300])
        return []

    patches: list[DocPatch] = []
    current = original
    for update in updates:
        section_header = update.get("section", "")
        new_body = update.get("updated_body", "")
        if not section_header or not new_body:
            continue

        sec = find_section(current, section_header)
        if sec is None:
            continue

        from dazzle.docs_update.updater import replace_section

        proposed = replace_section(current, section_header, new_body)
        patches.append(
            DocPatch(
                target="readme",
                file_path=str(readme_path),
                section=section_header,
                original=current,
                proposed=proposed,
                issues=[i.number for i in readme_issues],
                reason=f"Update '{section_header}' section for new features",
            )
        )
        current = proposed  # Chain patches

    return patches


def _patch_mkdocs(
    issues: list[ClosedIssue],
    project_root: Path,
    llm_complete: Callable[[str, str], str],
) -> list[DocPatch]:
    mkdocs_issues = [i for i in issues if "mkdocs" in i.affected_docs]
    if not mkdocs_issues:
        return []

    docs_dir = project_root / "docs"
    if not docs_dir.exists():
        return []

    # Collect existing page list
    pages = sorted(str(p.relative_to(docs_dir)) for p in docs_dir.rglob("*.md"))
    page_list = "\n".join(f"- {p}" for p in pages[:50])

    user_prompt = (
        f"Available mkdocs pages:\n{page_list}\n\n"
        f"Changes to document:\n{_issue_list_prompt(mkdocs_issues)}\n\n"
        f"Return a JSON array of pages that need updating:\n"
        f'[{{"page": "relative/path.md", "summary": "what to add"}}]\n'
        f"Only include pages that genuinely need changes. Max 5 pages."
    )

    try:
        raw = llm_complete(_MKDOCS_SYSTEM, user_prompt).strip()
    except Exception:
        logger.warning("LLM failed for mkdocs patches")
        return []

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]
    raw = raw.strip()

    try:
        page_updates = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for mkdocs patches: %s", raw[:300])
        return []

    patches: list[DocPatch] = []

    for item in page_updates[:5]:
        page_path = docs_dir / item.get("page", "")
        if not page_path.exists():
            logger.info("Skipping non-existent mkdocs page: %s", page_path)
            continue

        original = page_path.read_text()
        change_summary = item.get("summary", "")

        page_prompt = (
            f"Current page content:\n{original[:4000]}\n\n"
            f"Changes to apply: {change_summary}\n\n"
            f"Issue details:\n{_issue_list_prompt(mkdocs_issues)}\n\n"
            f"Return the FULL updated page content."
        )

        try:
            proposed = llm_complete(_MKDOCS_SYSTEM, page_prompt).strip()
        except Exception:
            logger.warning("LLM failed for mkdocs page %s", page_path)
            continue

        if proposed.startswith("```"):
            proposed = proposed.split("\n", 1)[1] if "\n" in proposed else proposed[3:]
        if proposed.endswith("```"):
            proposed = proposed[: proposed.rfind("```")]
        proposed = proposed.strip()

        if proposed and proposed != original.strip():
            patches.append(
                DocPatch(
                    target="mkdocs",
                    file_path=str(page_path),
                    section="full page",
                    original=original,
                    proposed=proposed + "\n",
                    issues=[i.number for i in mkdocs_issues],
                    reason=f"Update {item.get('page', '')} for: {change_summary}",
                )
            )

    return patches
