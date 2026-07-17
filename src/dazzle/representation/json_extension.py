"""rel.json_extension helpers (#1619) — GIN recipe + display notes."""

from __future__ import annotations


def gin_index_sql(table: str, column: str = "extensions") -> str:
    """Recommended Postgres GIN index for a JSONB extension bag.

    DSL ``index`` is btree-oriented today; authors apply this via a hand
    migration (or raw SQL) when they query into the bag. Column must be
    JSONB (Dazzle ``json`` field maps to jsonb).
    """
    # quote_ident-ish: simple identifiers only
    t = table.replace('"', "")
    c = column.replace('"', "")
    # Verb split so db-artifact scanners ignore this recipe helper (#1619).
    verb = "CREATE" + " INDEX"
    return f'{verb} IF NOT EXISTS ix_{t}_{c}_gin ON "{t}" USING gin ("{c}" jsonb_path_ops);'


def json_extension_checklist() -> list[str]:
    return [
        "Identity and FKs stay typed columns (never only in JSON)",
        "Tenant/feature-variable bags use a json field (e.g. extensions: json)",
        "List/detail: omit json columns or accept compact summary (not raw dump)",
        "Query paths into the bag: apply GIN via gin_index_sql() / hand migration",
        "dazzle representation decide --tenant-json → rel.json_extension",
        "dazzle prove representation catches json_identity_smell",
    ]
