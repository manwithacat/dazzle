"""Ratchet baseline for UX contract verification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Baseline:
    total: int = 0
    passed: int = 0
    failed: int = 0
    contracts: dict[str, str] = field(default_factory=dict)  # contract_id -> "passed"|"failed"
    timestamp: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": self.timestamp or datetime.now(UTC).isoformat(),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "contracts": self.contracts,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> Baseline:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls(
                total=data.get("total", 0),
                passed=data.get("passed", 0),
                failed=data.get("failed", 0),
                contracts=data.get("contracts", {}),
                timestamp=data.get("timestamp", ""),
            )
        except Exception:
            return cls()


@dataclass
class BaselineDiff:
    regressions: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    new_failures: list[str] = field(default_factory=list)


def compare_results(old: Baseline, new: Baseline) -> BaselineDiff:
    regressions, fixed, new_failures = [], [], []
    for contract_id, new_status in new.contracts.items():
        old_status = old.contracts.get(contract_id)
        if old_status is None and new_status == "failed":
            new_failures.append(contract_id)
        elif old_status == "passed" and new_status == "failed":
            regressions.append(contract_id)
        elif old_status == "failed" and new_status == "passed":
            fixed.append(contract_id)
    return BaselineDiff(regressions=regressions, fixed=fixed, new_failures=new_failures)
