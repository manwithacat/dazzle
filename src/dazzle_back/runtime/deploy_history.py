"""
Deployment History Store.

Tracks deployment records in the ops database for the Founder Console.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger("dazzle.deploy_history")


class DeployStatus(StrEnum):
    """Deployment status."""

    PENDING = "pending"
    PREFLIGHT = "preflight"
    GENERATING = "generating"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class DeploymentRecord:
    """A deployment record."""

    id: str
    spec_version_id: str | None
    status: DeployStatus
    environment: str
    stacks: list[str]
    preflight_result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    initiated_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "spec_version_id": self.spec_version_id,
            "status": self.status.value,
            "environment": self.environment,
            "stacks": self.stacks,
            "preflight_result": self.preflight_result,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "initiated_by": self.initiated_by,
        }


class DeployHistoryStore:
    """
    Stores deployment records in the ops database.
    """

    def __init__(self, ops_db: Any) -> None:
        self.ops_db = ops_db
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create deployment_history table if it doesn't exist."""
        with self.ops_db.connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deployment_history (
                    id TEXT PRIMARY KEY,
                    spec_version_id TEXT,
                    status TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    stacks TEXT,
                    preflight_result TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    initiated_by TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_deploy_history_started
                ON deployment_history(started_at DESC)
            """)

    def create_deployment(
        self,
        environment: str,
        initiated_by: str,
        spec_version_id: str | None = None,
    ) -> DeploymentRecord:
        """Create a new deployment record."""
        record = DeploymentRecord(
            id=str(uuid4()),
            spec_version_id=spec_version_id,
            status=DeployStatus.PENDING,
            environment=environment,
            stacks=[],
            preflight_result=None,
            error_message=None,
            started_at=datetime.now(UTC),
            completed_at=None,
            initiated_by=initiated_by,
        )
        self._save(record)
        return record

    def update_status(
        self,
        deploy_id: str,
        status: DeployStatus,
        error_message: str | None = None,
        stacks: list[str] | None = None,
        preflight_result: dict[str, Any] | None = None,
    ) -> None:
        """Update deployment status."""
        completed_at = (
            datetime.now(UTC).isoformat()
            if status in (DeployStatus.COMPLETED, DeployStatus.FAILED, DeployStatus.ROLLED_BACK)
            else None
        )

        with self.ops_db.connection() as conn:
            updates = ["status = ?"]
            params: list[Any] = [status.value]

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            if stacks is not None:
                updates.append("stacks = ?")
                params.append(json.dumps(stacks))
            if preflight_result is not None:
                updates.append("preflight_result = ?")
                params.append(json.dumps(preflight_result))
            if completed_at:
                updates.append("completed_at = ?")
                params.append(completed_at)

            params.append(deploy_id)
            conn.execute(
                f"UPDATE deployment_history SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    def list_deployments(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent deployments."""
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM deployment_history
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "id": row["id"],
                        "spec_version_id": row["spec_version_id"],
                        "status": row["status"],
                        "environment": row["environment"],
                        "stacks": json.loads(row["stacks"]) if row["stacks"] else [],
                        "error_message": row["error_message"],
                        "started_at": row["started_at"],
                        "completed_at": row["completed_at"],
                        "initiated_by": row["initiated_by"],
                    }
                )
            return results

    def get_deployment(self, deploy_id: str) -> dict[str, Any] | None:
        """Get a single deployment record."""
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM deployment_history WHERE id = ?",
                (deploy_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "spec_version_id": row["spec_version_id"],
                "status": row["status"],
                "environment": row["environment"],
                "stacks": json.loads(row["stacks"]) if row["stacks"] else [],
                "preflight_result": json.loads(row["preflight_result"])
                if row["preflight_result"]
                else None,
                "error_message": row["error_message"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "initiated_by": row["initiated_by"],
            }

    def _save(self, record: DeploymentRecord) -> None:
        """Save a deployment record."""
        with self.ops_db.connection() as conn:
            conn.execute(
                """
                INSERT INTO deployment_history
                (id, spec_version_id, status, environment, stacks, preflight_result,
                 error_message, started_at, completed_at, initiated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.spec_version_id,
                    record.status.value,
                    record.environment,
                    json.dumps(record.stacks),
                    json.dumps(record.preflight_result) if record.preflight_result else None,
                    record.error_message,
                    record.started_at.isoformat(),
                    record.completed_at.isoformat() if record.completed_at else None,
                    record.initiated_by,
                ),
            )
