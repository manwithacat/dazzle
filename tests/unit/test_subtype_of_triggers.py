"""#1217 Phase 3e.iii — plpgsql trigger emitters for subtype kind consistency.

A row in a TPT child table must match a base-table row whose `kind` column
equals the snake_case discriminator for that child. Postgres CHECK constraints
can't reference another row, so a BEFORE INSERT OR UPDATE trigger enforces it.
"""

from __future__ import annotations


def test_assert_subtype_kind_function_emits_postgres_function() -> None:
    from dazzle.http.runtime.triggers import build_assert_subtype_kind_function

    sql = build_assert_subtype_kind_function()
    assert "CREATE OR REPLACE FUNCTION assert_subtype_kind" in sql
    assert "LANGUAGE plpgsql" in sql
    assert "TG_ARGV[0]" in sql  # expected kind passed as trigger arg
    assert "TG_ARGV[1]" in sql  # base table name passed as trigger arg
    assert "RAISE EXCEPTION" in sql
    # No SQL injection vectors in the literal SQL.
    assert "format(" in sql  # uses format() with %I for safe identifier interpolation


def test_child_kind_trigger_emits_per_table_trigger() -> None:
    from dazzle.http.runtime.triggers import build_child_kind_trigger

    sql = build_child_kind_trigger(
        child_table="Vehicle", base_table="Asset", expected_kind="vehicle"
    )
    assert "CREATE TRIGGER" in sql
    assert "Vehicle_kind_consistency" in sql  # trigger named after child table
    assert "BEFORE INSERT OR UPDATE ON" in sql
    assert "Vehicle" in sql  # target table
    assert "assert_subtype_kind" in sql  # function invocation
    assert "'vehicle'" in sql  # expected kind value
    assert "'Asset'" in sql  # base table name


def test_child_kind_trigger_uses_pascal_case_table_names() -> None:
    """build_metadata keys tables by PascalCase entity name; the trigger must
    target the same identifiers."""
    from dazzle.http.runtime.triggers import build_child_kind_trigger

    sql = build_child_kind_trigger(
        child_table="Vehicle", base_table="Asset", expected_kind="vehicle"
    )
    # The trigger must reference the actual table identifier (PascalCase),
    # quoted appropriately for Postgres if needed.
    assert "Vehicle" in sql  # not "vehicle" as a table-name token
    assert "Asset" in sql
