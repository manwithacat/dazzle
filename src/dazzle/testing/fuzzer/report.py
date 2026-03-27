"""Markdown report generator for fuzzer results."""

from __future__ import annotations

from collections import Counter

from dazzle.testing.fuzzer.oracle import Classification, FuzzResult


def generate_report(results: list[FuzzResult]) -> str:
    """Generate a markdown report from fuzz results."""
    counts = Counter(r.classification for r in results)
    total = len(results)

    all_constructs: set[str] = set()
    for r in results:
        all_constructs.update(r.constructs_hit)

    bugs = [r for r in results if r.classification in (Classification.HANG, Classification.CRASH)]
    bad_errors = [r for r in results if r.classification == Classification.BAD_ERROR]

    lines: list[str] = []
    lines.append("# DSL Parser Fuzz Report\n")
    lines.append(f"**{total} samples** tested\n")
    lines.append("## Summary\n")
    lines.append("| Classification | Count | % |")
    lines.append("|---|---|---|")
    for cls in Classification:
        c = counts.get(cls, 0)
        pct = f"{c / total * 100:.1f}" if total > 0 else "0.0"
        lines.append(f"| {cls.value} | {c} | {pct}% |")
    lines.append("")

    lines.append("## Construct Coverage\n")
    if all_constructs:
        for construct in sorted(all_constructs):
            lines.append(f"- {construct}")
    else:
        lines.append("No constructs hit (all inputs failed to parse).")
    lines.append("")

    if bugs:
        lines.append(f"## Bugs ({len(bugs)})\n")
        for i, bug in enumerate(bugs, 1):
            lines.append(f"### Bug {i}: {bug.classification.value.upper()}\n")
            if bug.error_type:
                lines.append(f"**Error type:** {bug.error_type}\n")
            if bug.error_message:
                lines.append(f"**Message:** {bug.error_message}\n")
            lines.append("**Input:**\n")
            lines.append(f"```dsl\n{bug.dsl_input[:500]}\n```\n")

    if bad_errors:
        lines.append(f"## Poor Error Messages ({len(bad_errors)})\n")
        for i, be in enumerate(bad_errors, 1):
            lines.append(f"### Bad Error {i}\n")
            lines.append(f"**Message:** {be.error_message}\n")
            lines.append(f"**Input:**\n```dsl\n{be.dsl_input[:500]}\n```\n")

    return "\n".join(lines)
