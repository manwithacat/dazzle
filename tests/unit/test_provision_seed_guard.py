"""provision_single_org's tenant-root seed guard (auth Plan 1d, review Finding 1).

_seed_values_for_root must read required/auto_add from the IR `modifiers` (via
is_required / FieldModifier), not bare attributes — and raise ProvisionError
(not let a raw NotNullViolation escape) for a non-framework-derivable required
field.
"""

from types import SimpleNamespace

import pytest

from dazzle.core.ir.fields import FieldModifier
from dazzle.db.provision import ProvisionError, _seed_values_for_root


def _field(name: str, *, modifiers=(), default=None):  # noqa: ANN001
    return SimpleNamespace(
        name=name,
        modifiers=list(modifiers),
        is_required=FieldModifier.REQUIRED in modifiers,
        default=default,
        default_expr=None,
        type=SimpleNamespace(kind="str"),
    )


def _root(fields):  # noqa: ANN001
    return SimpleNamespace(name="Workspace", fields=fields)


def test_seeds_name_only_root() -> None:
    root = _root(
        [
            _field("id", modifiers=[FieldModifier.PK]),
            _field("name", modifiers=[FieldModifier.REQUIRED]),
        ]
    )
    vals = _seed_values_for_root(root, "org-1", "Acme")
    assert vals == {"id": "org-1", "name": "Acme"}


def test_required_nondefaulted_field_raises_provision_error() -> None:
    root = _root(
        [
            _field("id", modifiers=[FieldModifier.PK]),
            _field("name", modifiers=[FieldModifier.REQUIRED]),
            _field("billing_email", modifiers=[FieldModifier.REQUIRED]),  # not derivable
        ]
    )
    with pytest.raises(ProvisionError, match="billing_email"):
        _seed_values_for_root(root, "org-1", "Acme")


def test_required_with_default_is_ok() -> None:
    root = _root(
        [
            _field("id", modifiers=[FieldModifier.PK]),
            _field("name", modifiers=[FieldModifier.REQUIRED]),
            _field("region", modifiers=[FieldModifier.REQUIRED], default="us"),
        ]
    )
    vals = _seed_values_for_root(root, "org-1", "Acme")
    assert "region" not in vals  # has a DB default — not force-seeded, no error


def test_auto_add_field_is_ok() -> None:
    root = _root(
        [
            _field("id", modifiers=[FieldModifier.PK]),
            _field("name", modifiers=[FieldModifier.REQUIRED]),
            _field("created_at", modifiers=[FieldModifier.REQUIRED, FieldModifier.AUTO_ADD]),
        ]
    )
    vals = _seed_values_for_root(root, "org-1", "Acme")
    assert "created_at" not in vals  # auto_add — no error
