# src/dazzle/db/sql.py
"""SQL helpers shared by the runtime and the ``dazzle db`` commands.

The one identifier-quoting rule lives here: ``dazzle.db`` depends only on
``dazzle.core``, so the HTTP runtime's query builder and the db CLI helpers
both import it without either pulling in the other.
"""


def quote_identifier(name: str) -> str:
    """Quote a SQL identifier (table or column name) to handle reserved words.

    Uses double quotes, the SQL standard. Dazzle uses PascalCase entity names
    as table names, so every table reference goes through here.

    Examples:
        quote_identifier("Order") -> '"Order"'
        quote_identifier('a"b') -> '"a""b"'   (embedded quotes are doubled)
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'
