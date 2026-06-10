"""#1357: framework-table registry, autogenerate exclusions, constraint pipeline.

`dazzle db revision --autogenerate` against a live DB proposed dropping every
framework table (users, sessions, _dazzle_audit_log, …) because env.py only
excluded `_dazzle_params`; and entity-level `unique a, b` / `index x`
constraints were silently dropped at the converter boundary (the #1302 bug
class), reaching neither create_all nor the alembic metadata.
"""

import re
from pathlib import Path

from dazzle.back.alembic.framework_tables import include_object as _include_object
from dazzle.back.alembic.framework_tables import is_framework_table

REPO_ROOT = Path(__file__).resolve().parents[2]
BACK_DIR = REPO_ROOT / "src" / "dazzle" / "back"

# Table name followed by an opening paren (possibly on the next line) — the
# paren requirement excludes prose mentions in comments.
_CREATE_TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([a-z_]+)\s*\(")


def _scraped_runtime_tables() -> set[str]:
    names: set[str] = set()
    for path in BACK_DIR.rglob("*.py"):
        names.update(_CREATE_TABLE_RE.findall(path.read_text(encoding="utf-8")))
    return names


def test_every_runtime_created_table_is_registered() -> None:
    scraped = _scraped_runtime_tables()
    assert len(scraped) > 20, f"scrape looks broken: {sorted(scraped)}"
    unregistered = {t for t in scraped if not is_framework_table(t)}
    assert not unregistered, (
        f"Runtime-created tables missing from the framework-table registry: "
        f"{sorted(unregistered)}.\nAdd them to "
        f"src/dazzle/back/alembic/framework_tables.py — otherwise "
        f"`dazzle db revision --autogenerate` will propose DROPPING them "
        f"against a live database (#1357)."
    )


def test_include_object_excludes_framework_tables() -> None:
    for name in ("users", "sessions", "_dazzle_audit_log", "_grants", "alembic_version"):
        assert _include_object(None, name, "table", True, None) is False, name


def test_include_object_keeps_project_tables() -> None:
    for name in ("invoice", "ticket", "line_item"):
        assert _include_object(None, name, "table", True, None) is True, name


def test_include_object_skips_reflected_runtime_indexes() -> None:
    # Runtime DDL (FTS GIN, framework-table indexes) uses the idx_ prefix.
    assert _include_object(None, "idx_ticket_fts", "index", True, None) is False
    assert _include_object(None, "idx_audit_entity", "index", True, None) is False
    # Metadata-emitted indexes (ix_ prefix) and non-reflected ones stay.
    assert _include_object(None, "ix_list_ticket_status_created", "index", True, None) is True
    assert _include_object(None, "idx_anything", "index", False, None) is True


def test_entity_constraints_reach_sqlalchemy_metadata(tmp_path: Path) -> None:
    # End-to-end: DSL `unique`/`index` constraint lines → IR → converter →
    # back EntitySpec → build_metadata table args.
    from dazzle.back.converters.entity_converter import convert_entities
    from dazzle.back.runtime.sa_schema import build_metadata
    from dazzle.core.parser import parse_modules

    dsl = (
        "module c1357\n\n"
        'app c1357 "C"\n\n'
        'entity Product "Product":\n'
        "  id: uuid pk\n"
        "  tenant: str(40) required\n"
        "  code: str(40) required\n"
        "  status: str(20) required\n"
        "  unique tenant, code\n"
        "  index status\n"
    )
    f = tmp_path / "app.dsl"
    f.write_text(dsl, encoding="utf-8")
    (module,) = parse_modules([f])
    (ir_entity,) = module.fragment.entities
    assert len(ir_entity.constraints) == 2, "DSL constraints did not parse"

    (back_entity,) = convert_entities([ir_entity])
    assert len(back_entity.constraints) == 2, "converter dropped entity.constraints (#1357)"

    metadata = build_metadata([back_entity])
    table = metadata.tables["Product"]
    unique_names = {c.name for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"}
    index_names = {i.name for i in table.indexes}
    assert "uq_Product_tenant_code" in unique_names
    assert "ix_Product_status" in index_names
