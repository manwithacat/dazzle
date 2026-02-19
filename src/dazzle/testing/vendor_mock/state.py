"""
In-memory state store for vendor mock servers.

Provides stateful CRUD tracking so that resources created via POST
can be retrieved via GET, matching real vendor API behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from dazzle.testing.vendor_mock.data_generators import DataGenerator


class MockStateStore:
    """Per-vendor in-memory state store with CRUD operations.

    Args:
        foreign_models: Dict mapping model_name -> {fields: {field_name: field_spec}}.
        generator: DataGenerator for populating default field values.
    """

    def __init__(
        self,
        foreign_models: dict[str, dict[str, Any]] | None = None,
        generator: DataGenerator | None = None,
    ) -> None:
        self._store: dict[str, dict[str, dict[str, Any]]] = {}  # model -> {id -> record}
        self._models = foreign_models or {}
        self._generator = generator or DataGenerator()
        self._counters: dict[str, int] = {}

    def _get_model_fields(self, model_name: str) -> dict[str, dict[str, Any]]:
        """Get field definitions for a model."""
        model_def = self._models.get(model_name, {})
        fields: dict[str, dict[str, Any]] = model_def.get("fields", {})
        return fields

    def _find_pk_field(self, model_name: str) -> tuple[str, str]:
        """Find the primary key field name and type for a model.

        Returns:
            (field_name, type_string) — defaults to ("id", "str(50)") if not found.
        """
        fields = self._get_model_fields(model_name)
        for fname, fspec in fields.items():
            if isinstance(fspec, dict) and fspec.get("pk"):
                return fname, fspec.get("type", "str(50)")
        return "id", "str(50)"

    def _generate_id(self, model_name: str) -> Any:
        """Generate a new ID for a model based on its PK field type."""
        _, type_str = self._find_pk_field(model_name)

        if type_str == "uuid":
            return str(uuid.uuid4())
        if type_str == "int":
            self._counters[model_name] = self._counters.get(model_name, 0) + 1
            return self._counters[model_name]
        # String-based: generate prefixed ID
        self._counters[model_name] = self._counters.get(model_name, 0) + 1
        prefix = model_name[:3].lower()
        return f"{prefix}_{self._counters[model_name]:06d}"

    def _ensure_collection(self, model_name: str) -> dict[str, dict[str, Any]]:
        """Ensure the collection for a model exists."""
        if model_name not in self._store:
            self._store[model_name] = {}
        return self._store[model_name]

    def create(self, model_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Store a new resource, auto-generating ID and timestamps.

        Args:
            model_name: The foreign model name.
            data: The request body data.

        Returns:
            The stored record with generated ID and timestamps.
        """
        collection = self._ensure_collection(model_name)
        pk_field, _ = self._find_pk_field(model_name)

        # Generate ID if not provided
        record_id = data.get(pk_field) or self._generate_id(model_name)

        # Build record: start with defaults from model fields, overlay with provided data
        fields = self._get_model_fields(model_name)
        record: dict[str, Any] = {}

        for fname, fspec in fields.items():
            if isinstance(fspec, dict):
                if fname == pk_field:
                    record[fname] = record_id
                elif fname in data:
                    record[fname] = data[fname]
                elif fname in ("created_at",):
                    record[fname] = datetime.now(UTC).isoformat()
                elif fname in ("updated_at",):
                    record[fname] = datetime.now(UTC).isoformat()
                else:
                    # Generate a default value for required fields
                    if fspec.get("required") and not fspec.get("pk"):
                        record[fname] = self._generator.generate_field(fname, fspec)
                    else:
                        record[fname] = None

        # Merge any extra data fields not in the model definition
        for k, v in data.items():
            if k not in record:
                record[k] = v

        # Ensure PK is set
        record[pk_field] = record_id

        # Store using string key
        collection[str(record_id)] = record
        return record

    def get(self, model_name: str, record_id: Any) -> dict[str, Any] | None:
        """Retrieve a resource by primary key.

        Args:
            model_name: The foreign model name.
            record_id: The primary key value.

        Returns:
            The record dict, or None if not found.
        """
        collection = self._store.get(model_name, {})
        return collection.get(str(record_id))

    def list(self, model_name: str, **filters: Any) -> list[dict[str, Any]]:
        """List all resources of a type, optionally filtered.

        Args:
            model_name: The foreign model name.
            **filters: Field=value filters to apply.

        Returns:
            List of matching records.
        """
        collection = self._store.get(model_name, {})
        records = list(collection.values())

        if filters:
            for key, value in filters.items():
                records = [r for r in records if r.get(key) == value]

        return records

    def update(
        self, model_name: str, record_id: Any, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Partially update a resource.

        Args:
            model_name: The foreign model name.
            record_id: The primary key value.
            data: Fields to update.

        Returns:
            The updated record, or None if not found.
        """
        collection = self._store.get(model_name, {})
        record = collection.get(str(record_id))
        if record is None:
            return None

        record.update(data)
        # Update timestamp if the model has one
        fields = self._get_model_fields(model_name)
        if "updated_at" in fields:
            record["updated_at"] = datetime.now(UTC).isoformat()

        return record

    def delete(self, model_name: str, record_id: Any) -> bool:
        """Delete a resource.

        Args:
            model_name: The foreign model name.
            record_id: The primary key value.

        Returns:
            True if the record was found and deleted.
        """
        collection = self._store.get(model_name, {})
        key = str(record_id)
        if key in collection:
            del collection[key]
            return True
        return False

    def clear(self, model_name: str | None = None) -> None:
        """Clear all records, or records for a specific model.

        Args:
            model_name: If given, clear only that model's records.
        """
        if model_name:
            self._store.pop(model_name, None)
        else:
            self._store.clear()
            self._counters.clear()
