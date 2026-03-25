"""
Demo Data Loader.

Loads seed CSV/JSONL files into a running Dazzle instance via the REST API.
Handles entity dependency ordering, authentication, and conflict detection.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any

import httpx

from dazzle.core.strings import to_api_plural

logger = logging.getLogger("dazzle.demo_data")


@dataclass
class LoadResult:
    """Result of loading demo data for one entity."""

    entity: str
    created: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class LoadReport:
    """Aggregate report for a full demo data load."""

    results: list[LoadResult] = field(default_factory=list)
    total_created: int = 0
    total_skipped: int = 0
    total_failed: int = 0

    def add(self, result: LoadResult) -> None:
        self.results.append(result)
        self.total_created += result.created
        self.total_skipped += result.skipped
        self.total_failed += result.failed

    def summary(self) -> str:
        lines = [
            f"Demo data load: {self.total_created} created, {self.total_skipped} skipped, {self.total_failed} failed"
        ]
        for r in self.results:
            status = "ok" if not r.failed else "ERRORS"
            lines.append(
                f"  {r.entity}: {r.created} created, {r.skipped} skipped, {r.failed} failed [{status}]"
            )
            for err in r.errors[:3]:
                lines.append(f"    - {err}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_created": self.total_created,
            "total_skipped": self.total_skipped,
            "total_failed": self.total_failed,
            "entities": [
                {
                    "entity": r.entity,
                    "created": r.created,
                    "skipped": r.skipped,
                    "failed": r.failed,
                    "errors": r.errors[:5],
                }
                for r in self.results
            ],
        }


def topological_sort_entities(entities: list[Any]) -> list[str]:
    """Sort entity names by FK dependency order (parents first).

    Uses graphlib.TopologicalSorter instead of SQLAlchemy to avoid the
    optional dependency.

    Args:
        entities: List of EntitySpec objects from the IR.

    Returns:
        Entity names in dependency order (referenced entities first).
    """
    graph: dict[str, set[str]] = {}
    entity_names = {e.name for e in entities}

    for entity in entities:
        deps: set[str] = set()
        for f in entity.fields:
            if f.type and f.type.ref_entity and f.type.ref_entity in entity_names:
                # Skip self-references
                if f.type.ref_entity != entity.name:
                    deps.add(f.type.ref_entity)
        graph[entity.name] = deps

    sorter = TopologicalSorter(graph)
    try:
        return list(sorter.static_order())
    except Exception:
        # Circular refs — fall back to alphabetical
        logger.warning("Circular FK references detected, falling back to alphabetical order")
        return sorted(entity_names)


def read_seed_file(path: Path) -> list[dict[str, Any]]:
    """Read a CSV or JSONL seed file.

    Args:
        path: Path to the seed file (.csv or .jsonl).

    Returns:
        List of row dictionaries.
    """
    if path.suffix == ".jsonl":
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    elif path.suffix == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    else:
        raise ValueError(f"Unsupported seed file format: {path.suffix}")


def find_seed_files(data_dir: Path) -> dict[str, Path]:
    """Find all seed files in a directory.

    Looks for CSV and JSONL files. If both exist for the same entity,
    JSONL takes precedence.

    Args:
        data_dir: Directory containing seed files.

    Returns:
        Mapping of entity name to seed file path.
    """
    files: dict[str, Path] = {}

    # CSV first (lower precedence)
    for p in sorted(data_dir.glob("*.csv")):
        files[p.stem] = p

    # JSONL overrides CSV
    for p in sorted(data_dir.glob("*.jsonl")):
        files[p.stem] = p

    return files


class DemoDataLoader:
    """Loads demo data seed files into a running Dazzle instance."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        email: str | None = None,
        password: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._client: httpx.Client | None = None
        self._token: str | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=30.0)
        return self._client

    def authenticate(self) -> None:
        """Authenticate against the target instance.

        Raises:
            RuntimeError: If authentication fails.
        """
        if not self.email or not self.password:
            raise RuntimeError("Email and password required for authentication")

        client = self._get_client()
        resp = client.post(
            "/auth/login",
            json={"email": self.email, "password": self.password},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Authentication failed: {resp.status_code} {resp.text}")

        data = resp.json()
        self._token = data.get("access_token") or data.get("token")
        if not self._token:
            # Session-based auth — cookies are stored by httpx
            logger.info("Authenticated via session cookies")
        else:
            logger.info("Authenticated via access token")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def load_entity(self, entity_name: str, rows: list[dict[str, Any]]) -> LoadResult:
        """Load rows for a single entity via POST.

        Args:
            entity_name: Entity name (PascalCase).
            rows: List of row dicts to create.

        Returns:
            LoadResult with counts.
        """
        result = LoadResult(entity=entity_name)
        endpoint = f"/{to_api_plural(entity_name)}"
        client = self._get_client()

        for row in rows:
            try:
                resp = client.post(endpoint, json=row, headers=self._headers())
                if resp.status_code in (200, 201):
                    result.created += 1
                elif resp.status_code == 409:
                    # Conflict — record already exists
                    result.skipped += 1
                elif resp.status_code == 422:
                    # Validation error — try without read-only fields
                    result.failed += 1
                    detail = resp.json().get("detail", resp.text)
                    result.errors.append(f"Validation error for {row.get('id', '?')}: {detail}")
                else:
                    result.failed += 1
                    result.errors.append(
                        f"HTTP {resp.status_code} for {row.get('id', '?')}: {resp.text[:200]}"
                    )
            except httpx.HTTPError as e:
                result.failed += 1
                result.errors.append(f"Network error for {row.get('id', '?')}: {e}")

        return result

    def load_all(
        self,
        data_dir: Path,
        entity_order: list[str],
        *,
        entities_filter: list[str] | None = None,
    ) -> LoadReport:
        """Load all seed data in dependency order.

        Args:
            data_dir: Directory containing seed files.
            entity_order: Entity names in topological order (parents first).
            entities_filter: If provided, only load these entities.

        Returns:
            LoadReport with per-entity results.
        """
        report = LoadReport()
        seed_files = find_seed_files(data_dir)

        for entity_name in entity_order:
            if entities_filter and entity_name not in entities_filter:
                continue

            if entity_name not in seed_files:
                continue

            logger.info("Loading %s from %s", entity_name, seed_files[entity_name].name)
            rows = read_seed_file(seed_files[entity_name])
            if not rows:
                continue

            result = self.load_entity(entity_name, rows)
            report.add(result)
            logger.info(
                "  %s: %d created, %d skipped, %d failed",
                entity_name,
                result.created,
                result.skipped,
                result.failed,
            )

        return report

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> DemoDataLoader:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def validate_seed_data(
    data_dir: Path,
    entities: list[Any],
) -> list[str]:
    """Validate seed files against the DSL entity definitions.

    Checks:
    - All seed file columns match entity fields
    - FK references point to existing seed IDs
    - Enum values are valid
    - Required fields are present

    Args:
        data_dir: Directory containing seed files.
        entities: List of EntitySpec objects from the IR.

    Returns:
        List of validation error messages (empty = valid).
    """
    errors: list[str] = []
    entity_map = {e.name: e for e in entities}
    seed_files = find_seed_files(data_dir)

    # Collect all IDs per entity for FK validation
    entity_ids: dict[str, set[str]] = {}
    for name, path in seed_files.items():
        try:
            rows = read_seed_file(path)
            entity_ids[name] = {str(r.get("id", "")) for r in rows if r.get("id")}
        except Exception as e:
            logger.warning("Seed validation error: %s", e, exc_info=True)
            errors.append(f"{name}: Failed to read seed file: {e}")

    for name, path in seed_files.items():
        if name not in entity_map:
            errors.append(f"{name}: No matching entity in DSL")
            continue

        entity = entity_map[name]
        field_map = {f.name: f for f in entity.fields}

        try:
            rows = read_seed_file(path)
        except Exception as e:
            logger.warning("Seed validation error: %s", e, exc_info=True)
            errors.append(f"{name}: Failed to read: {e}")
            continue

        if not rows:
            continue

        # Check columns match fields
        seed_columns = set(rows[0].keys())
        entity_fields = set(field_map.keys())
        unknown_cols = seed_columns - entity_fields
        if unknown_cols:
            errors.append(f"{name}: Unknown columns: {', '.join(sorted(unknown_cols))}")

        # Check required fields
        for f in entity.fields:
            if getattr(f, "required", False) and f.name not in seed_columns and f.name != "id":
                errors.append(f"{name}: Missing required field '{f.name}'")

        # Check FK references and enum values per row
        for i, row in enumerate(rows):
            for col, value in row.items():
                if col not in field_map:
                    continue
                fld = field_map[col]

                # FK reference check
                if fld.type and fld.type.ref_entity and value:
                    ref_entity = fld.type.ref_entity
                    if ref_entity in entity_ids:
                        if str(value) not in entity_ids[ref_entity]:
                            errors.append(
                                f"{name} row {i}: {col}='{value}' references "
                                f"missing {ref_entity} ID"
                            )

                # Enum value check
                if fld.type and fld.type.enum_values and value:
                    if str(value) not in fld.type.enum_values:
                        errors.append(
                            f"{name} row {i}: {col}='{value}' not in enum {fld.type.enum_values}"
                        )

    return errors
