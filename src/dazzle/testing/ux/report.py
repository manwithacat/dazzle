"""UX verification report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.testing.ux.inventory import Interaction
from dazzle.testing.ux.structural import StructuralResult


@dataclass
class UXReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    coverage: float = 0.0
    summary: str = ""
    failures: list[Interaction] = field(default_factory=list)
    structural_results: list[StructuralResult] = field(default_factory=list)
    structural_passed: int = 0
    structural_failed: int = 0

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# UX Verification Report\n")
        lines.append(f"**Coverage:** {self.coverage:.1f}%\n")
        lines.append(
            f"**Interactions:** {self.total} tested, "
            f"{self.passed} passed, {self.failed} failed, "
            f"{self.skipped} skipped\n"
        )

        if self.structural_results:
            lines.append(
                f"**Structural:** {self.structural_passed + self.structural_failed} checked, "
                f"{self.structural_passed} passed, {self.structural_failed} failed\n"
            )

        if self.failures:
            lines.append("## Failures\n")
            for f in self.failures:
                lines.append(f"### {f.cls.value}({f.entity}, {f.persona})\n")
                lines.append(f"**Description:** {f.description}\n")
                if f.error:
                    lines.append(f"**Error:** {f.error}\n")
                if f.screenshot:
                    lines.append(f"**Screenshot:** {f.screenshot}\n")

        failed_structural = [r for r in self.structural_results if not r.passed]
        if failed_structural:
            lines.append("## Structural Failures\n")
            for r in failed_structural:
                lines.append(f"- **{r.check_name}**: {r.message}\n")

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "coverage": self.coverage,
            "structural_passed": self.structural_passed,
            "structural_failed": self.structural_failed,
            "failures": [
                {
                    "cls": f.cls.value,
                    "entity": f.entity,
                    "persona": f.persona,
                    "description": f.description,
                    "error": f.error,
                    "screenshot": f.screenshot,
                }
                for f in self.failures
            ],
        }


def generate_report(
    interactions: list[Interaction],
    structural_results: list[StructuralResult],
) -> UXReport:
    """Generate a UX verification report from test results."""
    total = len(interactions)
    passed = sum(1 for i in interactions if i.status == "passed")
    failed = sum(1 for i in interactions if i.status == "failed")
    skipped = sum(1 for i in interactions if i.status == "skipped")
    coverage = (passed / total * 100) if total > 0 else 0.0
    failures = [i for i in interactions if i.status == "failed"]

    s_passed = sum(1 for r in structural_results if r.passed)
    s_failed = sum(1 for r in structural_results if not r.passed)

    summary = f"{total} tested, {passed} passed, {failed} failed, {skipped} skipped"

    return UXReport(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        coverage=coverage,
        summary=summary,
        failures=failures,
        structural_results=structural_results,
        structural_passed=s_passed,
        structural_failed=s_failed,
    )
