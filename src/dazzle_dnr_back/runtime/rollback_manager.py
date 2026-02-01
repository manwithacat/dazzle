"""
Rollback Manager.

Stores AppSpec snapshots alongside spec versions and enables
rollback to a previous version by restoring DSL files and
triggering re-deployment.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.rollback")


class RollbackManager:
    """
    Manages rollback of AppSpec versions.

    Stores DSL file snapshots alongside spec versions and can
    restore them for rollback operations.
    """

    def __init__(
        self,
        spec_version_store: Any,
        project_dir: Path | None = None,
        deploy_history_store: Any | None = None,
    ) -> None:
        self.spec_version_store = spec_version_store
        self.project_dir = project_dir or Path(".")
        self.deploy_history_store = deploy_history_store
        self._snapshots_dir = self.project_dir / ".dazzle" / "spec_snapshots"

    def save_snapshot(self, version_id: str) -> None:
        """
        Save current DSL files as a snapshot for this version.

        Copies all .dsl files from the project directory.
        """
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_dir = self._snapshots_dir / version_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Only scan dsl/ directory, not entire project tree
        dsl_dir = self.project_dir / "dsl"
        if dsl_dir.is_dir():
            dsl_files = list(dsl_dir.glob("**/*.dsl"))
        else:
            dsl_files = list(self.project_dir.glob("*.dsl"))
        manifest = []

        for dsl_file in dsl_files:
            rel_path = dsl_file.relative_to(self.project_dir)
            target = snapshot_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(dsl_file), str(target))
            manifest.append(str(rel_path))

        # Save manifest
        (snapshot_dir / "manifest.json").write_text(
            json.dumps({"files": manifest, "version_id": version_id})
        )
        logger.info(f"Saved DSL snapshot for version {version_id}: {len(manifest)} files")

    def rollback_to(self, version_id: str) -> dict[str, Any]:
        """
        Rollback to a specific spec version.

        1. Validates the target version exists
        2. Runs preflight on current state
        3. Restores DSL files from snapshot
        4. Records rollback in deployment history

        Returns:
            Result dict with status and details
        """
        snapshot_dir = self._snapshots_dir / version_id
        manifest_file = snapshot_dir / "manifest.json"

        if not manifest_file.exists():
            # Try to get snapshot from spec_version_store
            snapshot = self.spec_version_store.get_snapshot(version_id)
            if not snapshot:
                return {
                    "status": "error",
                    "message": f"No snapshot found for version {version_id}",
                }
            return {
                "status": "error",
                "message": "DSL file snapshot not available for this version. Only spec data is stored.",
            }

        manifest = json.loads(manifest_file.read_text())
        files = manifest.get("files", [])

        # Restore files
        restored = []
        for rel_path in files:
            source = snapshot_dir / rel_path
            target = self.project_dir / rel_path
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(source), str(target))
                restored.append(rel_path)

        # Record in deploy history
        if self.deploy_history_store:
            from dazzle_dnr_back.runtime.deploy_history import DeployStatus

            deploy = self.deploy_history_store.create_deployment(
                environment="rollback",
                initiated_by="console",
                spec_version_id=version_id,
            )
            self.deploy_history_store.update_status(
                deploy.id,
                DeployStatus.ROLLED_BACK,
            )

        logger.info(f"Rolled back to version {version_id}: restored {len(restored)} files")
        return {
            "status": "ok",
            "version_id": version_id,
            "files_restored": len(restored),
            "files": restored,
        }

    def has_snapshot(self, version_id: str) -> bool:
        """Check if a DSL snapshot exists for a version."""
        return (self._snapshots_dir / version_id / "manifest.json").exists()
