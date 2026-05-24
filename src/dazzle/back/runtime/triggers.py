"""Polymorphic-subtype cross-row consistency triggers (#1217 Phase 3e.iii).

Postgres CHECK constraints cannot reference another row, so we enforce
"the matching base row's `kind` equals this subtype's discriminator" via
a BEFORE INSERT OR UPDATE trigger on each child table.

Two emitters:
- ``build_assert_subtype_kind_function()`` — declares the shared plpgsql
  function (called once, e.g. from an Alembic revision).
- ``build_child_kind_trigger(child, base, kind)`` — declares the per-child
  trigger that invokes the function with two args.

Postgres identifiers are case-sensitive when quoted. ``build_metadata`` keys
tables by PascalCase entity name (e.g. ``Asset``, ``Vehicle``), so the
trigger references the same identifiers and double-quotes them defensively
in case the table-name token would otherwise be lowercased by Postgres.
"""

from __future__ import annotations


def build_assert_subtype_kind_function() -> str:
    """Postgres function body that fires from the per-child trigger."""
    return """\
CREATE OR REPLACE FUNCTION assert_subtype_kind() RETURNS trigger AS $$
DECLARE
    expected_kind text := TG_ARGV[0];
    base_table text := TG_ARGV[1];
    base_kind text;
BEGIN
    EXECUTE format(
        'SELECT kind::text FROM %I WHERE id = $1', base_table
    ) INTO base_kind USING NEW.id;
    IF base_kind IS DISTINCT FROM expected_kind THEN
        RAISE EXCEPTION
            'Subtype kind mismatch on %: base row kind is %, expected %',
            TG_TABLE_NAME, base_kind, expected_kind;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def build_child_kind_trigger(*, child_table: str, base_table: str, expected_kind: str) -> str:
    """Per-child BEFORE INSERT OR UPDATE trigger that calls the shared function.

    Postgres double-quotes preserve case on the identifiers. The string args
    to assert_subtype_kind() are passed as ordinary text literals (single-
    quoted) since they're plpgsql function arguments, not identifiers.
    """
    return (
        f'CREATE TRIGGER "{child_table}_kind_consistency"\n'
        f'  BEFORE INSERT OR UPDATE ON "{child_table}"\n'
        f"  FOR EACH ROW\n"
        f"  EXECUTE FUNCTION assert_subtype_kind('{expected_kind}', '{base_table}');\n"
    )
