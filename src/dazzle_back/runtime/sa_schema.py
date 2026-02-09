"""
SQLAlchemy MetaData bridge for EntitySpec.

Converts DSL EntitySpec objects into SQLAlchemy Table objects on a shared
MetaData instance.  This gives us:

* Topologically-sorted DDL via ``metadata.create_all()``
* Automatic cycle handling for self-referencing FKs (``use_alter=True``)
* A single source of truth that Alembic can diff against a live database

The module deliberately uses **SQLAlchemy Core only** — no ORM, no Session.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

if TYPE_CHECKING:
    import sqlalchemy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — sqlalchemy is an optional dependency (postgres extra)
# ---------------------------------------------------------------------------

_sa_imported = False
_sa: Any = None  # sqlalchemy module


def _ensure_sa() -> Any:
    """Import sqlalchemy on first use and return the module."""
    global _sa_imported, _sa
    if not _sa_imported:
        try:
            import sqlalchemy

            _sa = sqlalchemy
        except ImportError as exc:
            raise RuntimeError(
                "sqlalchemy is required for the SA schema bridge.  "
                "Install it with:  pip install dazzle[postgres]"
            ) from exc
        _sa_imported = True
    return _sa


# ---------------------------------------------------------------------------
# Type mapping  (mirrors pg_backend._scalar_type_to_postgres)
# ---------------------------------------------------------------------------


def _scalar_type_to_sa(scalar_type: ScalarType) -> Any:
    """Map a DSL ScalarType to a SQLAlchemy column type instance."""
    sa = _ensure_sa()
    mapping: dict[ScalarType, Any] = {
        ScalarType.STR: sa.Text(),
        ScalarType.TEXT: sa.Text(),
        ScalarType.INT: sa.Integer(),
        ScalarType.DECIMAL: sa.Float(),
        ScalarType.BOOL: sa.Boolean(),
        ScalarType.DATE: sa.Text(),
        ScalarType.DATETIME: sa.Text(),
        ScalarType.UUID: sa.Text(),
        ScalarType.EMAIL: sa.Text(),
        ScalarType.URL: sa.Text(),
        ScalarType.JSON: sa.Text(),
    }
    return mapping.get(scalar_type, sa.Text())


def _field_type_to_sa(field_type: FieldType) -> Any:
    """Convert a DSL FieldType to a SQLAlchemy column type instance."""
    sa = _ensure_sa()
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_sa(field_type.scalar_type)
    # enum and ref both store as TEXT in the current implementation
    return sa.Text()


# ---------------------------------------------------------------------------
# Column builder
# ---------------------------------------------------------------------------


def _field_to_column(
    field: FieldSpec,
    entity_name: str,
    entity_names: set[str],
) -> Any:
    """Convert a single FieldSpec into a SQLAlchemy ``Column``."""
    sa = _ensure_sa()
    col_type = _field_type_to_sa(field.type)

    kwargs: dict[str, Any] = {}

    # Primary key
    if field.name == "id":
        kwargs["primary_key"] = True

    # Nullable / required
    if field.name != "id":
        kwargs["nullable"] = not field.required

    # Unique
    if field.unique:
        kwargs["unique"] = True

    # Default
    if field.default is not None:
        kwargs["server_default"] = sa.text(repr(field.default))

    # Foreign key for ref fields
    fk_args: list[Any] = []
    if field.type.kind == "ref" and field.type.ref_entity:
        ref_entity = field.type.ref_entity
        if ref_entity in entity_names:
            # Self-reference needs use_alter to break circular DDL dependency
            is_self_ref = ref_entity == entity_name
            fk_args.append(
                sa.ForeignKey(
                    f"{ref_entity}.id",
                    use_alter=is_self_ref,
                    name=f"fk_{entity_name}_{field.name}_{ref_entity}" if is_self_ref else None,
                )
            )

    return sa.Column(field.name, col_type, *fk_args, **kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_metadata(entities: list[EntitySpec]) -> sqlalchemy.MetaData:
    """Convert a list of EntitySpec into a SQLAlchemy ``MetaData``.

    Each entity becomes a ``Table`` with columns derived from its fields.
    Foreign-key relationships are expressed via ``ForeignKey`` so that
    ``metadata.sorted_tables`` returns tables in dependency order and
    ``metadata.create_all()`` emits DDL in the correct order.

    Args:
        entities: DSL entity specifications.

    Returns:
        A populated ``sqlalchemy.MetaData`` instance.
    """
    sa = _ensure_sa()
    metadata: sqlalchemy.MetaData = cast("sqlalchemy.MetaData", sa.MetaData())
    entity_names = {e.name for e in entities}

    for entity in entities:
        columns = []

        # Ensure an 'id' column exists
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append(sa.Column("id", sa.Text(), primary_key=True))

        for field in entity.fields:
            columns.append(_field_to_column(field, entity.name, entity_names))

        sa.Table(entity.name, metadata, *columns)

    return metadata


def get_sorted_table_names(entities: list[EntitySpec]) -> list[str]:
    """Return entity/table names in topological (FK-dependency) order.

    Tables that are depended upon come first.

    Args:
        entities: DSL entity specifications.

    Returns:
        List of table names sorted so that referenced tables precede
        referencing tables.
    """
    metadata = build_metadata(entities)
    return [t.name for t in metadata.sorted_tables]
