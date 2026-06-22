"""Test-data generation for the agent-E2E harness (#1446).

Extracted from ``DazzleClient`` (which had accreted HTTP transport, auth, CRUD,
cleanup, schema and data-generation onto one object). ``DataGenerator`` is the
data-generation collaborator: given an entity name it builds a valid payload from
the entity's schema, recursively materialising required ``ref`` parents. It needs a
client for the two capabilities it doesn't own — schema lookup and entity creation —
which are injected via the constructor.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from dazzle.testing.field_value_gen import generate_field_value_from_str

if TYPE_CHECKING:
    from dazzle.testing.test_runner import DazzleClient


class DataGenerator:
    """Generate valid test data for an entity from its schema.

    ``client`` supplies ``get_entity_schema`` (to read the field list) and
    ``create_entity`` (to materialise required ref parents).
    """

    MAX_REF_DEPTH = 3

    def __init__(self, client: DazzleClient):
        self._client = client

    def generate(
        self,
        entity_name: str,
        overrides: dict[str, Any] | None = None,
        create_refs: bool = True,
        _ref_depth: int = 0,
    ) -> dict[str, Any]:
        """Generate valid test data for an entity based on its schema.

        Args:
            entity_name: The entity type to generate data for
            overrides: Field values to override the generated ones
            create_refs: If True, create referenced entities and include their IDs
            _ref_depth: Internal recursion depth counter (max 3 levels)
        """
        schema = self._client.get_entity_schema(entity_name)
        if not schema:
            return overrides or {}

        data: dict[str, Any] = {}
        for fld in schema.get("fields", []):
            name = fld.get("name", "")
            field_type_orig = fld.get("type", "")  # Preserve original case
            field_type = field_type_orig.lower()
            required = fld.get("required", False)
            unique = fld.get("unique", False)
            max_length = fld.get("max_length")
            # Fallback: parse max_length from type string like "str(8)"
            if max_length is None and "str" in field_type:
                ml_match = re.search(r"str\((\d+)\)", field_type)
                if ml_match:
                    max_length = int(ml_match.group(1))

            # Skip auto-generated fields
            if name in ("id", "created_at", "updated_at"):
                continue

            # Handle reference fields
            if "ref" in field_type:
                if required and create_refs and _ref_depth < self.MAX_REF_DEPTH:
                    # Extract the referenced entity name from "ref(EntityName)"
                    # Use original case field_type to preserve entity name case
                    ref_match = re.search(r"ref\((\w+)\)", field_type_orig)
                    if ref_match:
                        ref_entity = ref_match.group(1)
                        # Create the referenced entity (with depth-limited recursion)
                        ref_data = self.generate(
                            ref_entity, create_refs=True, _ref_depth=_ref_depth + 1
                        )
                        ref_result = self._client.create_entity(ref_entity, ref_data)
                        if ref_result and "id" in ref_result:
                            # Use the field name directly (the ref stores the ID)
                            data[name] = ref_result["id"]
                continue

            if required:
                data[name] = generate_field_value_from_str(
                    name, field_type, unique=unique, max_length=max_length
                )

        # Apply overrides
        if overrides:
            data.update(overrides)

        # Regenerate unique fields after overrides — design-time values
        # from test JSON files are generated once and become stale across
        # runs, causing unique-constraint collisions in the database.
        # Skip ref fields: their override values are $ref:-resolved UUIDs
        # pointing to real parent entities, not stale strings.
        if overrides:
            for fld in schema.get("fields", []):
                fname = fld.get("name", "")
                ftype = fld.get("type", "").lower()
                if fld.get("unique", False) and fname in overrides and fname not in ("id",):
                    if "ref" in ftype:
                        continue
                    ml = fld.get("max_length")
                    if ml is None and "str" in ftype:
                        ml_m = re.search(r"str\((\d+)\)", ftype)
                        if ml_m:
                            ml = int(ml_m.group(1))
                    data[fname] = generate_field_value_from_str(
                        fname, ftype, unique=True, max_length=ml
                    )

        return data
