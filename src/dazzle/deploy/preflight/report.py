"""
Report generation for preflight validation.

Generates JSON and Markdown reports from preflight results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PreflightReport


class ReportGenerator:
    """Generates reports from preflight results."""

    def __init__(self, report: PreflightReport, output_dir: Path | None = None):
        """
        Initialize the report generator.

        Args:
            report: The preflight report to generate from
            output_dir: Directory to write reports to
        """
        self.report = report
        self.output_dir = output_dir

    def generate_json(self, path: Path | None = None) -> str:
        """
        Generate JSON report.

        Args:
            path: Optional path to write the report to

        Returns:
            JSON string of the report
        """
        report_dict = self.report.to_dict()
        json_str = json.dumps(report_dict, indent=2)

        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json_str)

        return json_str

    def generate_markdown(self, path: Path | None = None) -> str:
        """
        Generate Markdown report.

        Args:
            path: Optional path to write the report to

        Returns:
            Markdown string of the report
        """
        lines: list[str] = []

        # Header
        lines.append("# Pre-Flight Validation Report\n")

        # Summary badge
        summary = self.report.summary
        if summary:
            status_emoji = {
                "passed": "✅",
                "blocked": "⚠️",
                "failed": "❌",
            }.get(summary.status, "❓")
            lines.append(f"**Status:** {status_emoji} {summary.status.upper()}\n")

        # Metadata
        lines.append("## Metadata\n")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Run ID | `{self.report.run_id}` |")
        lines.append(f"| Timestamp | {self.report.timestamp_utc} |")
        lines.append(f"| App | {self.report.app_name} v{self.report.app_version} |")
        if self.report.commit_sha:
            lines.append(f"| Commit | `{self.report.commit_sha}` |")
        lines.append(f"| Environment | {self.report.env_name} |")
        lines.append(f"| Region | {self.report.region} |")
        lines.append(f"| Mode | {self.report.mode.value} |")
        lines.append("")

        # Toolchain
        if self.report.toolchain:
            lines.append("### Toolchain\n")
            for tool, version in self.report.toolchain.items():
                lines.append(f"- **{tool}**: {version}")
            lines.append("")

        # Summary section
        if summary:
            lines.append("## Summary\n")
            lines.append("| Severity | Count |")
            lines.append("|----------|-------|")
            lines.append(f"| 🔴 Critical | {summary.critical_count} |")
            lines.append(f"| 🟠 High | {summary.high_count} |")
            lines.append(f"| 🟡 Warning | {summary.warn_count} |")
            lines.append(f"| 🔵 Info | {summary.info_count} |")
            lines.append(f"| **Total** | **{summary.total_findings}** |")
            lines.append("")

            lines.append(
                f"**Stages:** {summary.stages_passed} passed, "
                f"{summary.stages_failed} failed, "
                f"{summary.stages_skipped} skipped\n"
            )

            if summary.next_actions:
                lines.append("### Next Actions\n")
                for action in summary.next_actions:
                    lines.append(f"- {action}")
                lines.append("")

        # Stage results
        lines.append("## Stage Results\n")

        for stage in self.report.stages:
            status_icon = {
                "passed": "✅",
                "failed": "❌",
                "skipped": "⏭️",
                "pending": "⏳",
                "running": "🔄",
            }.get(stage.status.value, "❓")

            lines.append(f"### {status_icon} {stage.name}\n")
            lines.append(
                f"**Status:** {stage.status.value} | **Duration:** {stage.duration_ms}ms\n"
            )

            if stage.error_message:
                lines.append(f"> ⚠️ {stage.error_message}\n")

            # Findings for this stage
            if stage.findings:
                lines.append("#### Findings\n")
                lines.append("| Severity | Code | Message | Resource |")
                lines.append("|----------|------|---------|----------|")

                for finding in stage.findings:
                    severity_icon = {
                        "critical": "🔴",
                        "high": "🟠",
                        "warn": "🟡",
                        "info": "🔵",
                    }.get(finding.severity.value, "⚪")

                    resource = finding.resource or "-"
                    message = (
                        finding.message[:80] + "..."
                        if len(finding.message) > 80
                        else finding.message
                    )

                    lines.append(
                        f"| {severity_icon} {finding.severity.value} | "
                        f"`{finding.code}` | {message} | {resource} |"
                    )

                lines.append("")

            # Artifacts
            if stage.artifacts:
                lines.append("#### Artifacts\n")
                for artifact in stage.artifacts:
                    lines.append(f"- **{artifact['type']}**: `{artifact['path']}`")
                lines.append("")

        # Critical findings detail
        critical_findings = [
            f for s in self.report.stages for f in s.findings if f.severity.value == "critical"
        ]

        if critical_findings:
            lines.append("## Critical Findings Detail\n")
            for finding in critical_findings:
                lines.append(f"### `{finding.code}`\n")
                lines.append(f"**Message:** {finding.message}\n")
                if finding.resource:
                    lines.append(f"**Resource:** `{finding.resource}`\n")
                if finding.file_path:
                    loc = finding.file_path
                    if finding.line_number:
                        loc += f":{finding.line_number}"
                    lines.append(f"**Location:** `{loc}`\n")
                if finding.remediation:
                    lines.append(f"**Remediation:** {finding.remediation}\n")
                lines.append("")

        # Footer
        lines.append("---\n")
        lines.append("*Generated by Dazzle Pre-Flight v1.0.0*")

        markdown = "\n".join(lines)

        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown)

        return markdown


def generate_report(
    report: PreflightReport,
    output_dir: Path,
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """
    Generate reports in specified formats.

    Args:
        report: The preflight report
        output_dir: Directory to write reports to
        formats: List of formats ("json", "md"). Defaults to both.

    Returns:
        Dictionary mapping format to output path
    """
    if formats is None:
        formats = ["json", "md"]

    generator = ReportGenerator(report, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Path] = {}

    if "json" in formats:
        json_path = output_dir / f"preflight-{report.run_id}.json"
        generator.generate_json(json_path)
        result["json"] = json_path

    if "md" in formats:
        md_path = output_dir / f"preflight-{report.run_id}.md"
        generator.generate_markdown(md_path)
        result["md"] = md_path

    return result
