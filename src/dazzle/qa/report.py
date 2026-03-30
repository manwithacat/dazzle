"""Findings aggregation, deduplication, severity sorting, and report formatting."""

import json

from dazzle.qa.models import Finding, QAReport

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Remove duplicates by (category, location) key, keeping the first occurrence."""
    seen: set[tuple[str, str]] = set()
    result: list[Finding] = []
    for f in findings:
        key = (f.category, f.location)
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def sort_by_severity(findings: list[Finding]) -> list[Finding]:
    """Return findings sorted high → medium → low."""
    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 99))


def format_table(report: QAReport) -> str:
    """Format a QAReport as a human-readable text table."""
    lines: list[str] = []
    lines.append(f"Visual QA: {report.app} — {report.total} findings")
    lines.append(
        f"High: {report.high_count}  Medium: {report.medium_count}  Low: {report.low_count}"
    )

    if not report.findings:
        lines.append("No findings — page looks good.")
        return "\n".join(lines)

    # Column widths
    col_sev = max(3, max(len(f.severity) for f in report.findings))
    col_cat = max(8, max(len(f.category) for f in report.findings))
    col_loc = max(8, max(len(f.location) for f in report.findings))
    col_desc = max(11, max(len(f.description) for f in report.findings))

    header = f"{'Sev':<{col_sev}}  {'Category':<{col_cat}}  {'Location':<{col_loc}}  {'Description':<{col_desc}}"
    separator = "-" * len(header)
    lines.append(separator)
    lines.append(header)
    lines.append(separator)

    for f in sort_by_severity(report.findings):
        lines.append(
            f"{f.severity:<{col_sev}}  {f.category:<{col_cat}}  {f.location:<{col_loc}}  {f.description:<{col_desc}}"
        )

    lines.append(separator)
    return "\n".join(lines)


def format_json(report: QAReport) -> str:
    """Serialise a QAReport to JSON with severity-sorted findings."""
    sorted_findings = sort_by_severity(report.findings)
    payload = {
        "app": report.app,
        "total": report.total,
        "high": report.high_count,
        "medium": report.medium_count,
        "low": report.low_count,
        "findings": [
            {
                "category": f.category,
                "severity": f.severity,
                "location": f.location,
                "description": f.description,
                "suggestion": f.suggestion,
            }
            for f in sorted_findings
        ],
    }
    return json.dumps(payload, indent=2)
