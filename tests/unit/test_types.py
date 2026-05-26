"""Tests for dazzle.types — NewType re-export."""

from __future__ import annotations

from dazzle.types import NewType


def test_newtype_creates_branded_alias() -> None:
    """NewType creates a callable whose runtime behaviour is the identity function."""
    UserId = NewType("UserId", str)
    assert UserId("x") == "x"


def test_newtype_type_name() -> None:
    """The brand carries the declared name."""
    UserId = NewType("UserId", str)
    assert UserId.__name__ == "UserId"


def test_newtype_supertype() -> None:
    """The brand records its supertype for type-checker use."""
    UserId = NewType("UserId", str)
    assert UserId.__supertype__ is str


def test_public_import_from_dazzle_types() -> None:
    """`from dazzle.types import NewType` works."""
    from typing import NewType as StdNewType

    from dazzle.types import NewType as DazzleNewType

    assert DazzleNewType is StdNewType


def test_public_import_from_dazzle_root() -> None:
    """`from dazzle import NewType` works and is the same object as typing.NewType."""
    from typing import NewType as StdNewType

    from dazzle import NewType as DazzleNewType

    assert DazzleNewType is StdNewType
