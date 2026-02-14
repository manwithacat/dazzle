"""
File-based JSON store for Sentinel scan results.

Persists scan results to `.dazzle/sentinel/` following the same pattern
as `.dazzle/discovery/`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .models import Finding, FindingStatus, ScanResult


class FindingStore:
    """Persist and retrieve Sentinel scan results as JSON files."""

    def __init__(self, project_path: Path) -> None:
        self._dir = project_path / ".dazzle" / "sentinel"

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_scan(self, result: ScanResult) -> Path:
        """Write a scan result to disk. Returns the file path."""
        self._ensure_dir()
        filename = f"sentinel_{int(time.time())}_{result.scan_id}.json"
        path = self._dir / filename
        path.write_text(json.dumps(result.model_dump(), indent=2))
        return path

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _scan_files(self) -> list[Path]:
        """Return scan files sorted newest-first."""
        if not self._dir.exists():
            return []
        files = sorted(self._dir.glob("sentinel_*.json"), reverse=True)
        return files

    def load_latest_findings(self) -> list[Finding]:
        """Return findings from the most recent scan, or []."""
        files = self._scan_files()
        if not files:
            return []
        return self._load_findings(files[0])

    def load_scan(self, scan_id: str) -> ScanResult | None:
        """Load a specific scan by ID."""
        for path in self._scan_files():
            data = self._read_json(path)
            if data and data.get("scan_id") == scan_id:
                return ScanResult.model_validate(data)
        return None

    def list_scans(self, limit: int = 10) -> list[dict[str, object]]:
        """Return summaries of recent scans (newest first)."""
        summaries: list[dict[str, object]] = []
        for path in self._scan_files()[:limit]:
            data = self._read_json(path)
            if data:
                summaries.append(
                    {
                        "scan_id": data.get("scan_id", ""),
                        "timestamp": data.get("timestamp", ""),
                        "trigger": data.get("trigger", ""),
                        "total_findings": data.get("summary", {}).get("total_findings", 0),
                        "file": path.name,
                    }
                )
        return summaries

    # ------------------------------------------------------------------
    # Mutate
    # ------------------------------------------------------------------

    def suppress_finding(self, finding_id: str, reason: str) -> bool:
        """Mark a finding as false_positive in the latest scan. Returns True on success."""
        files = self._scan_files()
        if not files:
            return False

        path = files[0]
        data = self._read_json(path)
        if not data:
            return False

        mutated = False
        for f in data.get("findings", []):
            if f.get("finding_id") == finding_id:
                f["status"] = FindingStatus.FALSE_POSITIVE.value
                f["suppression_reason"] = reason
                mutated = True
                break

        if mutated:
            path.write_text(json.dumps(data, indent=2))
        return mutated

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_json(self, path: Path) -> dict | None:  # type: ignore[type-arg]
        try:
            return json.loads(path.read_text())  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            return None

    def _load_findings(self, path: Path) -> list[Finding]:
        data = self._read_json(path)
        if not data:
            return []
        return [Finding.model_validate(f) for f in data.get("findings", [])]
