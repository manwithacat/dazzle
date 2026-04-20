"""Canonical contract-pointer lint — prevents pointer-comment drift.

Cycle 310 — 4th horizontal-discipline lint in the stack (after cycle 302's
`orphan_lint_rule`, cycle 306's `page_route_coverage`, cycle 284's
`none_vs_default_guard`). Extends the pattern cycle 309 endorsed:
continuously-running lints over manual `missing_contracts` breadth-scans.

## What this lints

Templates that declare governance by a ux-architect contract do so via a
Jinja comment at (or near) the top of the file:

    {# Contract: ~/.claude/skills/ux-architect/components/<slug>.md (UX-NNN) #}

Cycles 290-298 grew this convention from 0 → 19 templates. The lint pins
the shape so future additions follow the same grammar + catches drift
(stale slugs, duplicate UX IDs, typos, malformed whitespace).

## Gates

1. **Shape** — every `{# Contract: ... #}` line matches the canonical regex.
   Catches typos / misspelt paths / whitespace corruption.

2. **Internal slug/ID consistency** — two templates pointing at the same
   contract slug (e.g. `slide-over.md`) must agree on the UX-NNN (or both
   omit it). Catches half-renames where one template updates the pointer
   but its sibling doesn't.

3. **UX-NNN uniqueness** — no two distinct slugs claim the same UX-NNN.
   Catches accidental ID reuse when a contract gets renumbered.

4. **Slug shape** — every slug is kebab-case lowercase (no underscores,
   no camelCase). Matches the filesystem convention of
   `~/.claude/skills/ux-architect/components/*.md`.

The lint does NOT verify that pointer targets exist on the filesystem —
contract files live under `~/.claude/` which is per-user, not repo-local.
Existence would fail falsely in CI. Shape + consistency is enough to
catch real drift.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "dazzle_ui" / "templates"

# Canonical shape. Spec:
# - Literal prefix `{# Contract: ~/.claude/skills/ux-architect/components/`
# - Slug: lowercase kebab-case, `[a-z][a-z0-9-]+`, ends in `.md`
# - Optional `(UX-NNN)` suffix, where NNN is 1-4 digits
# - Any inter-token whitespace permitted (`\s+`)
# - Closing `#}` with any inter-token whitespace
_CANONICAL_POINTER_RE = re.compile(
    r"""
    \{\#
    \s*Contract:\s*
    ~/\.claude/skills/ux-architect/components/
    (?P<slug>[a-z][a-z0-9-]*)\.md
    (?:\s+\(UX-(?P<ux_id>\d{1,4})\))?
    \s*\#\}
    """,
    re.VERBOSE,
)

# Looser pattern used to DETECT pointer-like lines regardless of shape. If
# a template has `{# Contract:` at all, the strict regex must match — any
# structural corruption fails the shape gate rather than going unnoticed.
_POINTER_DETECT_RE = re.compile(r"\{#\s*Contract:")


def _collect_pointers() -> dict[str, list[tuple[str, str | None]]]:
    """Return {template_relpath: [(slug, ux_id_or_None), ...]}.

    Each .html under templates/ is scanned for pointer-like lines. A line
    that LOOKS like a pointer (matches _POINTER_DETECT_RE) but doesn't
    match the canonical shape gets a sentinel `(MALFORMED, line)` tuple
    so gate 1 can surface it with context.
    """
    result: dict[str, list[tuple[str, str | None]]] = {}
    for p in TEMPLATES_ROOT.rglob("*.html"):
        rel = p.relative_to(TEMPLATES_ROOT).as_posix()
        text = p.read_text()
        hits: list[tuple[str, str | None]] = []
        for line in text.splitlines():
            if not _POINTER_DETECT_RE.search(line):
                continue
            m = _CANONICAL_POINTER_RE.search(line)
            if m:
                hits.append((m.group("slug"), m.group("ux_id")))
            else:
                # Detected-but-malformed: record as sentinel
                hits.append(("__MALFORMED__", line.strip()))
        if hits:
            result[rel] = hits
    return result


class TestCanonicalPointerLint:
    """Shape + consistency gates on `{# Contract: ... #}` pointers.

    Purely forward-looking when introduced — all 19 existing pointers
    pass at cycle 310. The lint's value is preventing future drift.
    """

    def test_pointer_shape_is_canonical(self) -> None:
        """Every pointer-like line matches the canonical regex."""
        malformed: list[tuple[str, str]] = []
        for relpath, pointers in _collect_pointers().items():
            for slug, extra in pointers:
                if slug == "__MALFORMED__":
                    # extra holds the raw line for diagnostics
                    malformed.append((relpath, extra or "<empty>"))
        assert not malformed, (
            "\n\nMalformed `{# Contract: ... #}` pointer(s):\n"
            + "\n".join(f"  - {path}: {line}" for path, line in malformed)
            + "\n\nCanonical shape:\n"
            + "  {# Contract: ~/.claude/skills/ux-architect/components/<slug>.md (UX-NNN) #}\n"
            + "where <slug> is kebab-case and (UX-NNN) is optional."
        )

    def test_slug_ux_id_agreement_across_templates(self) -> None:
        """Templates citing the same contract slug must agree on UX-NNN."""
        # slug -> set of ux_ids seen (None if omitted)
        slug_to_ids: dict[str, set[str | None]] = defaultdict(set)
        # For error reporting: slug -> [(template, ux_id), ...]
        slug_citations: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for relpath, pointers in _collect_pointers().items():
            for slug, ux_id in pointers:
                if slug == "__MALFORMED__":
                    continue  # covered by test_pointer_shape_is_canonical
                slug_to_ids[slug].add(ux_id)
                slug_citations[slug].append((relpath, ux_id))
        conflicts = {slug: ids for slug, ids in slug_to_ids.items() if len(ids) > 1}
        assert not conflicts, (
            "\n\nContract slug(s) with disagreeing UX-NNN across templates:\n"
            + "\n".join(
                f"  - {slug}:\n"
                + "\n".join(
                    f"      {path} → {'UX-' + uid if uid else '(no UX-NNN)'}"
                    for path, uid in slug_citations[slug]
                )
                for slug in sorted(conflicts)
            )
            + "\n\nEither align the UX-NNN across all citations, or remove "
            "it from all of them if the contract isn't numbered yet."
        )

    def test_ux_id_uniqueness(self) -> None:
        """Two distinct slugs must not claim the same UX-NNN."""
        ux_id_to_slugs: dict[str, set[str]] = defaultdict(set)
        for pointers in _collect_pointers().values():
            for slug, ux_id in pointers:
                if slug == "__MALFORMED__" or ux_id is None:
                    continue
                ux_id_to_slugs[ux_id].add(slug)
        collisions = {uid: slugs for uid, slugs in ux_id_to_slugs.items() if len(slugs) > 1}
        assert not collisions, (
            "\n\nUX-NNN ID(s) claimed by multiple contract slugs:\n"
            + "\n".join(
                f"  - UX-{uid}: {', '.join(sorted(slugs))}"
                for uid, slugs in sorted(collisions.items())
            )
            + "\n\nRenumber one of them — UX-NNN IDs must be unique."
        )

    def test_slug_is_kebab_case(self) -> None:
        """Contract slugs use lowercase kebab-case (matches filesystem)."""
        bad: list[tuple[str, str]] = []
        for relpath, pointers in _collect_pointers().items():
            for slug, _ in pointers:
                if slug == "__MALFORMED__":
                    continue
                if "_" in slug or slug.lower() != slug:
                    bad.append((relpath, slug))
        assert not bad, (
            "\n\nSlug(s) not in lowercase kebab-case:\n"
            + "\n".join(f"  - {path}: {slug}" for path, slug in bad)
            + "\n\nSlugs must match the filesystem convention — all lowercase, "
            "hyphen-separated (`slide-over`, not `slide_over` or `SlideOver`)."
        )


def print_pointer_report() -> None:
    """Manual debugging helper — list all pointers by template."""
    pointers = _collect_pointers()
    print(f"templates with pointers: {len(pointers)}")
    for relpath in sorted(pointers):
        for slug, ux_id in pointers[relpath]:
            label = f"UX-{ux_id}" if ux_id else "(no ID)"
            tag = slug if slug != "__MALFORMED__" else "MALFORMED"
            print(f"  {relpath}  →  {tag}  {label}")
    print()
    # Aggregate
    slug_to_ids: dict[str, set[str | None]] = defaultdict(set)
    for plist in pointers.values():
        for slug, uid in plist:
            if slug != "__MALFORMED__":
                slug_to_ids[slug].add(uid)
    print(f"distinct slugs: {len(slug_to_ids)}")
    print(f"distinct UX-NNN IDs: {sum(1 for ids in slug_to_ids.values() for i in ids if i)}")


if __name__ == "__main__":
    print_pointer_report()
