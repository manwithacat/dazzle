"""
Relation loader for nested data fetching.

Handles loading related entities and building nested response objects.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from dazzle_dnr_back.specs.entity import EntitySpec, RelationSpec


@dataclass
class RelationInfo:
    """Information about a relation between entities."""

    name: str
    from_entity: str
    to_entity: str
    kind: str  # "one_to_many", "many_to_one", "many_to_many", "one_to_one"
    foreign_key_field: str  # The FK field on the "many" side
    backref: str | None = None
    on_delete: str = "restrict"  # restrict, cascade, set_null

    @property
    def is_to_one(self) -> bool:
        """Check if this is a to-one relation (FK holder side)."""
        return self.kind in ("many_to_one", "one_to_one")

    @property
    def is_to_many(self) -> bool:
        """Check if this is a to-many relation."""
        return self.kind in ("one_to_many", "many_to_many")


@dataclass
class RelationRegistry:
    """
    Registry of relations between entities.

    Tracks all relations and provides lookup methods.
    """

    _relations: dict[str, list[RelationInfo]] = field(default_factory=dict)
    _by_name: dict[tuple[str, str], RelationInfo] = field(default_factory=dict)

    def register(self, entity_name: str, relation: RelationInfo) -> None:
        """Register a relation for an entity."""
        if entity_name not in self._relations:
            self._relations[entity_name] = []
        self._relations[entity_name].append(relation)
        self._by_name[(entity_name, relation.name)] = relation

    def get_relations(self, entity_name: str) -> list[RelationInfo]:
        """Get all relations for an entity."""
        return self._relations.get(entity_name, [])

    def get_relation(self, entity_name: str, relation_name: str) -> RelationInfo | None:
        """Get a specific relation by name."""
        return self._by_name.get((entity_name, relation_name))

    def has_relation(self, entity_name: str, relation_name: str) -> bool:
        """Check if a relation exists."""
        return (entity_name, relation_name) in self._by_name

    @classmethod
    def from_entities(cls, entities: list["EntitySpec"]) -> "RelationRegistry":
        """
        Build a relation registry from entity specifications.

        Args:
            entities: List of entity specs

        Returns:
            Populated RelationRegistry
        """
        registry = cls()

        # Build entity lookup
        entity_map = {e.name: e for e in entities}

        for entity in entities:
            # Register explicit relations
            for rel in entity.relations:
                info = RelationInfo(
                    name=rel.name,
                    from_entity=entity.name,
                    to_entity=rel.to_entity,
                    kind=rel.kind.value if hasattr(rel.kind, "value") else str(rel.kind),
                    foreign_key_field=_infer_fk_field(rel, entity.name),
                    backref=rel.backref,
                    on_delete=rel.on_delete.value if hasattr(rel.on_delete, "value") else str(rel.on_delete),
                )
                registry.register(entity.name, info)

            # Register implicit relations from ref fields
            for field_spec in entity.fields:
                if field_spec.type.kind == "ref" and field_spec.type.ref_entity:
                    ref_entity = field_spec.type.ref_entity

                    # Check if we already have an explicit relation for this
                    existing = any(
                        r.foreign_key_field == field_spec.name
                        for r in registry.get_relations(entity.name)
                    )
                    if existing:
                        continue

                    # Create implicit relation
                    info = RelationInfo(
                        name=field_spec.name.replace("_id", ""),
                        from_entity=entity.name,
                        to_entity=ref_entity,
                        kind="many_to_one",
                        foreign_key_field=field_spec.name,
                        on_delete="restrict",
                    )
                    registry.register(entity.name, info)

        return registry


def _infer_fk_field(relation: "RelationSpec", entity_name: str) -> str:
    """Infer the foreign key field name from a relation."""
    if relation.kind.value in ("many_to_one", "one_to_one"):
        # FK is on this entity
        return f"{relation.name}_id"
    else:
        # FK is on the other entity
        return f"{entity_name.lower()}_id"


@dataclass
class RelationLoader:
    """
    Loads related entities for nested data fetching.

    Supports eager loading via JOINs or batched loading.
    """

    registry: RelationRegistry
    entity_map: dict[str, "EntitySpec"]
    _conn_factory: Any = None  # Function that returns a connection

    def __init__(
        self,
        registry: RelationRegistry,
        entities: list["EntitySpec"],
        conn_factory: Any = None,
    ):
        """
        Initialize the relation loader.

        Args:
            registry: Relation registry
            entities: List of entity specs
            conn_factory: Function that returns a SQLite connection
        """
        self.registry = registry
        self.entity_map = {e.name: e for e in entities}
        self._conn_factory = conn_factory

    def load_relations(
        self,
        entity_name: str,
        rows: list[dict[str, Any]],
        include: list[str],
        conn: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        """
        Load relations for a list of entity rows.

        Args:
            entity_name: Name of the entity
            rows: List of entity data dicts
            include: List of relation names to include
            conn: Optional SQLite connection

        Returns:
            Rows with nested relation data
        """
        if not include or not rows:
            return rows

        conn = conn or (self._conn_factory() if self._conn_factory else None)
        if not conn:
            return rows

        result = [dict(row) for row in rows]

        for relation_name in include:
            relation = self.registry.get_relation(entity_name, relation_name)
            if not relation:
                continue

            if relation.is_to_one:
                result = self._load_to_one(relation, result, conn)
            else:
                result = self._load_to_many(relation, result, conn)

        return result

    def _load_to_one(
        self,
        relation: RelationInfo,
        rows: list[dict[str, Any]],
        conn: sqlite3.Connection,
    ) -> list[dict[str, Any]]:
        """
        Load a to-one relation (many-to-one or one-to-one).

        Uses batched loading to avoid N+1 queries.
        """
        # Collect all foreign key values
        fk_field = relation.foreign_key_field
        fk_values = {str(row.get(fk_field)) for row in rows if row.get(fk_field)}

        if not fk_values:
            # No FKs to load
            for row in rows:
                row[relation.name] = None
            return rows

        # Batch load related entities
        placeholders = ", ".join("?" * len(fk_values))
        sql = f"SELECT * FROM {relation.to_entity} WHERE id IN ({placeholders})"

        cursor = conn.execute(sql, list(fk_values))
        cursor.row_factory = sqlite3.Row
        related_rows = cursor.fetchall()

        # Build lookup by ID
        related_map = {str(dict(r)["id"]): dict(r) for r in related_rows}

        # Attach to rows
        for row in rows:
            fk_value = row.get(fk_field)
            if fk_value:
                row[relation.name] = related_map.get(str(fk_value))
            else:
                row[relation.name] = None

        return rows

    def _load_to_many(
        self,
        relation: RelationInfo,
        rows: list[dict[str, Any]],
        conn: sqlite3.Connection,
    ) -> list[dict[str, Any]]:
        """
        Load a to-many relation (one-to-many or many-to-many).

        Uses batched loading.
        """
        # Collect all IDs
        ids = {str(row.get("id")) for row in rows if row.get("id")}

        if not ids:
            for row in rows:
                row[relation.name] = []
            return rows

        # The FK on the related entity points back to us
        fk_field = relation.foreign_key_field
        placeholders = ", ".join("?" * len(ids))
        sql = f"SELECT * FROM {relation.to_entity} WHERE {fk_field} IN ({placeholders})"

        cursor = conn.execute(sql, list(ids))
        cursor.row_factory = sqlite3.Row
        related_rows = cursor.fetchall()

        # Group by FK
        related_map: dict[str, list[dict[str, Any]]] = {}
        for r in related_rows:
            r_dict = dict(r)
            fk_value = str(r_dict.get(fk_field))
            if fk_value not in related_map:
                related_map[fk_value] = []
            related_map[fk_value].append(r_dict)

        # Attach to rows
        for row in rows:
            row_id = str(row.get("id"))
            row[relation.name] = related_map.get(row_id, [])

        return rows

    def build_join_sql(
        self,
        entity_name: str,
        include: list[str],
    ) -> tuple[str, list[str]]:
        """
        Build JOIN clauses for eager loading.

        Args:
            entity_name: Base entity name
            include: List of relations to join

        Returns:
            Tuple of (join_sql, select_columns)
        """
        joins = []
        columns = [f"{entity_name}.*"]

        for relation_name in include:
            relation = self.registry.get_relation(entity_name, relation_name)
            if not relation or not relation.is_to_one:
                continue

            alias = f"_{relation_name}"
            fk_field = relation.foreign_key_field

            join = (
                f"LEFT JOIN {relation.to_entity} AS {alias} "
                f"ON {entity_name}.{fk_field} = {alias}.id"
            )
            joins.append(join)

            # Add related columns with alias prefix
            related_entity = self.entity_map.get(relation.to_entity)
            if related_entity:
                for field in related_entity.fields:
                    columns.append(f"{alias}.{field.name} AS {alias}_{field.name}")
                # Add id if not in fields
                if not any(f.name == "id" for f in related_entity.fields):
                    columns.append(f"{alias}.id AS {alias}_id")

        return " ".join(joins), columns

    def parse_joined_row(
        self,
        row: dict[str, Any],
        entity_name: str,
        include: list[str],
    ) -> dict[str, Any]:
        """
        Parse a row from a JOIN query into nested objects.

        Args:
            row: Raw row dict from JOIN query
            entity_name: Base entity name
            include: List of included relations

        Returns:
            Dict with nested relation objects
        """
        result = {}
        nested: dict[str, dict[str, Any]] = {}

        for key, value in row.items():
            if key.startswith("_"):
                # This is a nested field: _owner_name -> owner.name
                parts = key[1:].split("_", 1)
                if len(parts) == 2:
                    relation_name, field_name = parts
                    if relation_name not in nested:
                        nested[relation_name] = {}
                    nested[relation_name][field_name] = value
            else:
                result[key] = value

        # Attach nested objects
        for relation_name in include:
            if relation_name in nested:
                # Check if nested has any non-None values (null join)
                if any(v is not None for v in nested[relation_name].values()):
                    result[relation_name] = nested[relation_name]
                else:
                    result[relation_name] = None
            else:
                result[relation_name] = None

        return result


# =============================================================================
# Foreign Key Management
# =============================================================================


def build_foreign_key_constraint(
    relation: RelationInfo,
    entity_name: str,
) -> str:
    """
    Build a FOREIGN KEY constraint for a relation.

    Args:
        relation: Relation info
        entity_name: Entity that holds the FK

    Returns:
        SQL constraint string
    """
    on_delete_map = {
        "restrict": "RESTRICT",
        "cascade": "CASCADE",
        "nullify": "SET NULL",
        "set_null": "SET NULL",
        "set_default": "SET DEFAULT",
    }

    on_delete = on_delete_map.get(relation.on_delete.lower(), "RESTRICT")

    return (
        f"FOREIGN KEY ({relation.foreign_key_field}) "
        f"REFERENCES {relation.to_entity}(id) ON DELETE {on_delete}"
    )


def get_foreign_key_constraints(
    entity: "EntitySpec",
    registry: RelationRegistry,
) -> list[str]:
    """
    Get all FK constraints for an entity.

    Args:
        entity: Entity spec
        registry: Relation registry

    Returns:
        List of FK constraint SQL strings
    """
    constraints = []

    for relation in registry.get_relations(entity.name):
        if relation.is_to_one:
            constraint = build_foreign_key_constraint(relation, entity.name)
            constraints.append(constraint)

    return constraints


def get_foreign_key_indexes(
    entity: "EntitySpec",
    registry: RelationRegistry,
) -> list[str]:
    """
    Get index creation statements for FK columns.

    Args:
        entity: Entity spec
        registry: Relation registry

    Returns:
        List of CREATE INDEX SQL statements
    """
    indexes = []

    for relation in registry.get_relations(entity.name):
        if relation.is_to_one:
            idx_name = f"idx_{entity.name}_{relation.foreign_key_field}"
            sql = (
                f"CREATE INDEX IF NOT EXISTS {idx_name} "
                f"ON {entity.name}({relation.foreign_key_field})"
            )
            indexes.append(sql)

    return indexes
