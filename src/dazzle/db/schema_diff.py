"""Schema diff operations for DSL-snapshot migrations.

Defines frozen dataclasses representing atomic schema changes,
used to compute and apply migrations between DSL snapshots.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AddTable:
    """Add a new table with columns, foreign keys, indexes, and unique constraints."""

    table: str
    columns: dict[str, Any]
    fks: list[str]
    indexes: list[str]
    uniques: list[str]


@dataclass(frozen=True)
class DropTable:
    """Drop a table. Carries prior table snapshot for downgrade."""

    table: str
    snap: dict[str, Any]


@dataclass(frozen=True)
class RenameTable:
    """Rename a table."""

    old: str
    new: str


@dataclass(frozen=True)
class AddColumn:
    """Add a column to a table."""

    table: str
    name: str
    col: dict[str, Any]


@dataclass(frozen=True)
class DropColumn:
    """Drop a column. Carries prior column snapshot for downgrade."""

    table: str
    name: str
    col: dict[str, Any]


@dataclass(frozen=True)
class RenameColumn:
    """Rename a column."""

    table: str
    old: str
    new: str


@dataclass(frozen=True)
class AlterColumn:
    """Alter a column's specification."""

    table: str
    name: str
    old: dict[str, Any]
    new: dict[str, Any]


@dataclass(frozen=True)
class AddForeignKey:
    """Add a foreign key constraint."""

    table: str
    column: str
    ref_table: str


@dataclass(frozen=True)
class DropForeignKey:
    """Drop a foreign key constraint."""

    table: str
    column: str
    ref_table: str


@dataclass(frozen=True)
class AddIndex:
    """Add an index on a column."""

    table: str
    column: str


@dataclass(frozen=True)
class DropIndex:
    """Drop an index on a column."""

    table: str
    column: str


@dataclass(frozen=True)
class AddUnique:
    """Add a unique constraint on a column."""

    table: str
    column: str


@dataclass(frozen=True)
class DropUnique:
    """Drop a unique constraint on a column."""

    table: str
    column: str


SchemaOp = (
    AddTable
    | DropTable
    | RenameTable
    | AddColumn
    | DropColumn
    | RenameColumn
    | AlterColumn
    | AddForeignKey
    | DropForeignKey
    | AddIndex
    | DropIndex
    | AddUnique
    | DropUnique
)
