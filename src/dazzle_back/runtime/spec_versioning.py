"""
Spec Versioning and Change Tracking.

Stores AppSpec snapshots on each server start, computes structured diffs
between versions for the Founder Console changes timeline.

Tables: spec_versions (in ops_database)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger("dazzle.spec_versioning")


@dataclass
class FieldChange:
    """A single field-level change."""

    entity: str
    field_name: str
    change_type: str  # added, removed, modified
    old_value: str | None = None
    new_value: str | None = None


@dataclass
class AppSpecDiff:
    """Structured diff between two AppSpec versions."""

    added_entities: list[str] = field(default_factory=list)
    removed_entities: list[str] = field(default_factory=list)
    modified_entities: list[str] = field(default_factory=list)
    added_surfaces: list[str] = field(default_factory=list)
    removed_surfaces: list[str] = field(default_factory=list)
    modified_surfaces: list[str] = field(default_factory=list)
    field_changes: list[FieldChange] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_entities": self.added_entities,
            "removed_entities": self.removed_entities,
            "modified_entities": self.modified_entities,
            "added_surfaces": self.added_surfaces,
            "removed_surfaces": self.removed_surfaces,
            "modified_surfaces": self.modified_surfaces,
            "field_changes": [
                {
                    "entity": fc.entity,
                    "field_name": fc.field_name,
                    "change_type": fc.change_type,
                    "old_value": fc.old_value,
                    "new_value": fc.new_value,
                }
                for fc in self.field_changes
            ],
            "summary": self.summary,
        }


@dataclass
class SpecVersion:
    """A stored AppSpec version."""

    id: str
    version_label: str
    content_hash: str
    spec_snapshot: dict[str, Any]
    diff: AppSpecDiff | None
    created_at: datetime


class SpecVersionStore:
    """
    Stores AppSpec versions in the ops database.

    Uses a spec_versions table for versioned snapshots and diffs.
    """

    def __init__(self, ops_db: Any) -> None:
        self.ops_db = ops_db
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create spec_versions table if it doesn't exist."""
        with self.ops_db.connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spec_versions (
                    id TEXT PRIMARY KEY,
                    version_label TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    spec_snapshot TEXT NOT NULL,
                    diff_data TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_spec_versions_created
                ON spec_versions(created_at DESC)
            """)

    def save_version(self, appspec: Any) -> SpecVersion | None:
        """
        Save a new spec version if the AppSpec has changed.

        Returns the new SpecVersion if saved, None if unchanged.
        """
        snapshot = self._appspec_to_dict(appspec)
        content_hash = self._hash_snapshot(snapshot)

        # Check if this hash already exists
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM spec_versions WHERE content_hash = %s LIMIT 1",
                (content_hash,),
            )
            if cursor.fetchone():
                return None  # No change

        # Compute diff against previous version
        prev = self._get_latest_snapshot()
        diff = self._compute_diff(prev, snapshot) if prev else None

        version_label = getattr(appspec, "version", "0.0.0")
        version_id = str(uuid4())
        now = datetime.now(UTC)

        sv = SpecVersion(
            id=version_id,
            version_label=version_label,
            content_hash=content_hash,
            spec_snapshot=snapshot,
            diff=diff,
            created_at=now,
        )

        with self.ops_db.connection() as conn:
            conn.execute(
                """
                INSERT INTO spec_versions (id, version_label, content_hash, spec_snapshot, diff_data, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    sv.id,
                    sv.version_label,
                    sv.content_hash,
                    json.dumps(sv.spec_snapshot),
                    json.dumps(sv.diff.to_dict()) if sv.diff else None,
                    sv.created_at.isoformat(),
                ),
            )

        logger.info(f"Saved spec version {version_id} (label={version_label})")
        return sv

    def list_versions(self, page: int = 1, per_page: int = 10) -> list[dict[str, Any]]:
        """List spec versions (paginated, newest first)."""
        offset = (page - 1) * per_page
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, version_label, content_hash, created_at, diff_data
                FROM spec_versions
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (per_page, offset),
            )
            results = []
            for row in cursor.fetchall():
                diff_summary = ""
                if row["diff_data"]:
                    try:
                        diff = json.loads(row["diff_data"])
                        diff_summary = diff.get("summary", "")
                    except Exception:
                        logger.debug("Failed to parse diff data", exc_info=True)
                results.append(
                    {
                        "id": row["id"],
                        "version_label": row["version_label"],
                        "content_hash": row["content_hash"][:12],
                        "created_at": row["created_at"],
                        "diff_summary": diff_summary,
                    }
                )
            return results

    def count_versions(self) -> int:
        """Count total spec versions."""
        with self.ops_db.connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM spec_versions")
            row = cursor.fetchone()
            return next(iter(row.values())) if row else 0

    def get_diff(self, version_id: str) -> dict[str, Any]:
        """Get the diff for a specific version."""
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                "SELECT diff_data FROM spec_versions WHERE id = %s",
                (version_id,),
            )
            row = cursor.fetchone()
            if row and row["diff_data"]:
                return json.loads(row["diff_data"])  # type: ignore[no-any-return]
        return {}

    def get_snapshot(self, version_id: str) -> dict[str, Any] | None:
        """Get the full spec snapshot for a version."""
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                "SELECT spec_snapshot FROM spec_versions WHERE id = %s",
                (version_id,),
            )
            row = cursor.fetchone()
            if row and row["spec_snapshot"]:
                return json.loads(row["spec_snapshot"])  # type: ignore[no-any-return]
        return None

    def _get_latest_snapshot(self) -> dict[str, Any] | None:
        """Get the most recent spec snapshot."""
        with self.ops_db.connection() as conn:
            cursor = conn.execute(
                "SELECT spec_snapshot FROM spec_versions ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row and row["spec_snapshot"]:
                return json.loads(row["spec_snapshot"])  # type: ignore[no-any-return]
        return None

    def _appspec_to_dict(self, appspec: Any) -> dict[str, Any]:
        """Convert AppSpec to a serializable dict."""
        if hasattr(appspec, "model_dump"):
            return appspec.model_dump()  # type: ignore[no-any-return]
        # Fallback: extract key properties
        result: dict[str, Any] = {
            "name": getattr(appspec, "name", "unknown"),
            "version": getattr(appspec, "version", "0.0.0"),
            "entities": {},
            "surfaces": {},
        }
        for entity in getattr(appspec, "entities", []):
            name = getattr(entity, "name", "")
            fields_dict = {}
            for f in getattr(entity, "fields", []):
                fname = getattr(f, "name", "")
                fields_dict[fname] = str(getattr(f, "type", getattr(f, "field_type", "")))
            result["entities"][name] = {
                "fields": fields_dict,
                "has_state_machine": bool(getattr(entity, "state_machine", None)),
            }
        for surface in getattr(appspec, "surfaces", []):
            name = getattr(surface, "name", "")
            result["surfaces"][name] = {
                "mode": str(getattr(surface, "mode", "")),
                "entity": str(getattr(surface, "entity", "")),
            }
        return result

    def _hash_snapshot(self, snapshot: dict[str, Any]) -> str:
        """Create a stable hash of a snapshot."""
        canonical = json.dumps(snapshot, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _compute_diff(self, old: dict[str, Any], new: dict[str, Any]) -> AppSpecDiff:
        """Compute structured diff between two snapshots."""
        diff = AppSpecDiff()

        old_entities = set(old.get("entities", {}).keys())
        new_entities = set(new.get("entities", {}).keys())

        diff.added_entities = sorted(new_entities - old_entities)
        diff.removed_entities = sorted(old_entities - new_entities)

        # Check modified entities
        for name in old_entities & new_entities:
            old_e = old["entities"][name]
            new_e = new["entities"][name]
            old_fields = old_e.get("fields", {})
            new_fields = new_e.get("fields", {})

            modified = False
            for fname in set(old_fields) | set(new_fields):
                if fname not in old_fields:
                    diff.field_changes.append(
                        FieldChange(
                            entity=name,
                            field_name=fname,
                            change_type="added",
                            new_value=new_fields[fname],
                        )
                    )
                    modified = True
                elif fname not in new_fields:
                    diff.field_changes.append(
                        FieldChange(
                            entity=name,
                            field_name=fname,
                            change_type="removed",
                            old_value=old_fields[fname],
                        )
                    )
                    modified = True
                elif old_fields[fname] != new_fields[fname]:
                    diff.field_changes.append(
                        FieldChange(
                            entity=name,
                            field_name=fname,
                            change_type="modified",
                            old_value=old_fields[fname],
                            new_value=new_fields[fname],
                        )
                    )
                    modified = True

            if modified:
                diff.modified_entities.append(name)

        # Surfaces
        old_surfaces = set(old.get("surfaces", {}).keys())
        new_surfaces = set(new.get("surfaces", {}).keys())
        diff.added_surfaces = sorted(new_surfaces - old_surfaces)
        diff.removed_surfaces = sorted(old_surfaces - new_surfaces)

        for name in old_surfaces & new_surfaces:
            if old["surfaces"][name] != new["surfaces"][name]:
                diff.modified_surfaces.append(name)

        # Summary
        parts = []
        if diff.added_entities:
            parts.append(f"+{len(diff.added_entities)} entities")
        if diff.removed_entities:
            parts.append(f"-{len(diff.removed_entities)} entities")
        if diff.modified_entities:
            parts.append(f"~{len(diff.modified_entities)} entities")
        if diff.added_surfaces:
            parts.append(f"+{len(diff.added_surfaces)} surfaces")
        if diff.removed_surfaces:
            parts.append(f"-{len(diff.removed_surfaces)} surfaces")
        if diff.modified_surfaces:
            parts.append(f"~{len(diff.modified_surfaces)} surfaces")
        if diff.field_changes:
            parts.append(f"{len(diff.field_changes)} field changes")
        diff.summary = ", ".join(parts) if parts else "No changes"

        return diff
