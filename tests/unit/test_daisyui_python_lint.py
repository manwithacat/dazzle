"""DaisyUI token lint for Python-embedded HTML strings — 5th horizontal-discipline.

Cycle 318 — Axis A3 of cycle 317's silent-drift gap doc. Templates have
been DaisyUI-free since cycle 17's sweep, but Python files emitting
HTML strings slipped through that scope (cycle 316 found 6 sites in
fragment_routes.py + route_generator.py).

This lint closes the gap: any Python file under `src/dazzle_{back,ui}/`
that embeds a DaisyUI token in a string literal must appear in
`INDIVIDUAL_ALLOWLIST` with a reason. Cycle 316 left 4 intentional sites
(documented below); this lint pins them.

## Detected tokens

Typography + semantic colour classes known to be DaisyUI-specific (not
canonical Tailwind): `text-error`, `text-primary`, `text-secondary`,
`text-base-content`, `bg-error`, `bg-primary`, `btn-primary`, `btn-error`,
`badge-{error,success,warning,info,ghost}`, `alert-{error,warning,info,success}`.

## Intentional deferrals (cycle 316)

- `template_renderer.py:201-207` — `badge-*` tone→class dispatch table.
  Grammar-level; migration needs redesign of the tone vocabulary.
- `template_renderer.py:214` — X-mark helper emitting `text-base-content/30`.
  Tiny unicode glyph; low priority.
- `htmx.py:168` — `alert alert-error` fallback only hit when
  template_renderer import fails (dev-only, unreachable in production).

## Not detected

- `converters/__init__.py:200` — `"text-secondary": "#6c757d"` is a
  Python dict literal mapping CLASS NAME → COLOR. It consumes DaisyUI
  names (for migration); it does not EMIT them as HTML. Lint allows
  dict-value positions.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DAZZLE_BACK_ROOT = REPO_ROOT / "src" / "dazzle_back"
DAZZLE_UI_ROOT = REPO_ROOT / "src" / "dazzle_ui"

# Tokens flagged. Word-boundary regex to avoid matching e.g. "non-error".
_DAISYUI_TOKENS: tuple[str, ...] = (
    "text-error",
    "text-primary",
    "text-secondary",
    "text-base-content",
    "bg-error",
    "bg-primary",
    "btn-primary",
    "btn-error",
    "badge-error",
    "badge-success",
    "badge-warning",
    "badge-info",
    "badge-ghost",
    "alert-error",
    "alert-warning",
    "alert-info",
    "alert-success",
)

# Match a DaisyUI token anywhere a class would appear — inside a string
# literal, with word-boundary-ish delimiters on both sides. We don't try
# to parse Python: instead we require the token be surrounded by
# space/quote/end-of-string, which catches HTML class="..." usage and
# skips `"text-error": "#xxx"` dict keys because the "#" after the value
# is not one of our boundary chars. We then post-filter dict-key positions.
_TOKEN_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(t) for t in _DAISYUI_TOKENS) + r")(?![\w-])"
)

# Dict-key heuristic: a line like `"text-secondary": "#6c757d"` has the
# token in a dict key position, which means it's being used as data, not
# emitted. Skip those.
_DICT_KEY_RE = re.compile(
    r'["\'](?:' + "|".join(re.escape(t) for t in _DAISYUI_TOKENS) + r')["\']\s*:\s*'
)


INDIVIDUAL_ALLOWLIST: dict[str, str] = {
    # Tone-vocabulary grammar — migrating requires redesigning every
    # caller's tone strings. Deferred cycle 316; warrants contract_audit.
    "src/dazzle_ui/runtime/template_renderer.py": (
        "badge-* tone dispatch table (lines 201-207) + text-base-content/30 "
        "X-mark helper (line 214). Grammar + helper; migration requires "
        "redesign of tone vocabulary. Deferred cycle 316; candidate contract_audit."
    ),
    # Fallback alert — only reachable when template_renderer fails to
    # import. Dev-only; migrating has no user-visible benefit.
    "src/dazzle_ui/runtime/htmx.py": (
        "alert alert-error fallback (line 168) only reached when "
        "template_renderer import fails — dev-only, unreachable in production. "
        "Deferred cycle 316."
    ),
}


def _collect_token_hits() -> dict[str, list[tuple[int, str]]]:
    """Return {rel_path: [(line_number, matched_token), ...]}.

    Excludes:
    - Dict-key positions (e.g. `"text-secondary": "..."` — data, not emission)
    - Test files (conftest etc. may exercise these tokens for coverage)
    - Cache / generated files
    """
    result: dict[str, list[tuple[int, str]]] = {}
    for root in (DAZZLE_BACK_ROOT, DAZZLE_UI_ROOT):
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(REPO_ROOT).as_posix()
            hits: list[tuple[int, str]] = []
            for lineno, line in enumerate(p.read_text().splitlines(), start=1):
                dict_key_match = _DICT_KEY_RE.search(line)
                for m in _TOKEN_RE.finditer(line):
                    # Skip if this match falls inside a dict-key position —
                    # token appears as a data lookup key, not as HTML-class
                    # emission (e.g. `"text-secondary": "#6c757d"`).
                    if (
                        dict_key_match
                        and dict_key_match.start() <= m.start() < dict_key_match.end()
                    ):
                        continue
                    hits.append((lineno, m.group(1)))
            if hits:
                result[rel] = hits
    return result


class TestDaisyUIPythonLint:
    """Every DaisyUI token in Python source must be allowlisted with a reason.

    Adds a 5th horizontal-discipline lint to the stack (after cycles 284,
    302, 306-308, 310). Closes Class 5 of cycle 317's silent-drift gap doc.
    """

    def test_daisyui_tokens_are_allowlisted(self) -> None:
        """New DaisyUI drift in Python requires an allowlist entry."""
        hits = _collect_token_hits()
        unallowed = {path: rows for path, rows in hits.items() if path not in INDIVIDUAL_ALLOWLIST}
        assert not unallowed, (
            "\n\nDaisyUI token(s) found in Python source outside the allowlist:\n"
            + "\n".join(
                f"  - {path}:\n" + "\n".join(f"      L{lineno}: {token}" for lineno, token in rows)
                for path, rows in sorted(unallowed.items())
            )
            + "\n\nEither (a) migrate to canonical HSL Tailwind tokens "
            "(`text-[hsl(var(--destructive))]`, `bg-[hsl(var(--primary))]`, etc.) "
            "— see cycle 316 migration — OR (b) add to INDIVIDUAL_ALLOWLIST "
            "with a reason citing a gap doc, deferred-cycle note, or constraint."
        )

    def test_every_allowlist_entry_has_hits(self) -> None:
        """Stale allowlist entries (file no longer has DaisyUI) must be removed."""
        hits = _collect_token_hits()
        stale = [path for path in INDIVIDUAL_ALLOWLIST if path not in hits]
        assert not stale, (
            "\n\nAllowlist entries with no DaisyUI hits (migration complete — remove):\n"
            + "\n".join(f"  - {path}" for path in sorted(stale))
        )

    def test_allowlist_entries_are_real_files(self) -> None:
        """Allowlist must point at existing files."""
        nonexistent = [path for path in INDIVIDUAL_ALLOWLIST if not (REPO_ROOT / path).exists()]
        assert not nonexistent, "\n\nAllowlist entries that don't exist on disk:\n" + "\n".join(
            f"  - {path}" for path in sorted(nonexistent)
        )

    def test_every_allowlist_entry_has_non_empty_reason(self) -> None:
        """Governance: reasons must cite evidence."""
        for path, reason in INDIVIDUAL_ALLOWLIST.items():
            assert reason.strip(), f"Empty reason for {path}"
            assert len(reason) > 30, (
                f"Reason for {path} is too short ({len(reason)} chars) — "
                "cite a cycle, gap doc, or constraint."
            )


def print_hits_report() -> None:
    """Manual debugging helper."""
    hits = _collect_token_hits()
    total = sum(len(rows) for rows in hits.values())
    print(f"Python files with DaisyUI tokens: {len(hits)} ({total} hits total)")
    for path in sorted(hits):
        allowed = "ALLOWED" if path in INDIVIDUAL_ALLOWLIST else "NOT ALLOWED"
        print(f"  {path}  [{allowed}]")
        for lineno, token in hits[path]:
            print(f"      L{lineno}: {token}")


if __name__ == "__main__":
    print_hits_report()
