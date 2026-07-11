"""Helpers for drift gates that compare large generated text artefacts.

Plain ``assert a == b`` on multi-KB CSS/markdown dumps the *entire* file into
CI logs via pytest's assertion rewrite — unreadable and noisy. Use a capped
unified diff instead.
"""

from __future__ import annotations

import difflib


def assert_text_matches(
    generated: str,
    committed: str,
    *,
    regenerate_hint: str,
    max_diff_lines: int = 48,
) -> None:
    """Fail with a short unified diff when *generated* ≠ *committed*."""
    if generated == committed:
        return
    gen_lines = generated.splitlines(keepends=True)
    com_lines = committed.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            com_lines,
            gen_lines,
            fromfile="committed",
            tofile="generated",
            n=2,
        )
    )
    # Summary line counts help when the whole file shifted.
    head = (
        f"{regenerate_hint}\n"
        f"(committed={len(com_lines)} lines, generated={len(gen_lines)} lines, "
        f"diff_hunk_lines={len(diff)})\n"
    )
    body = "".join(diff[:max_diff_lines])
    if len(diff) > max_diff_lines:
        body += f"... ({len(diff) - max_diff_lines} more diff lines omitted)\n"
    raise AssertionError(head + body)
