"""DSL-driven database operations.

Layer A (zero-config, DSL-derived):
  - status: row counts per entity, database size
  - verify: FK integrity checks, orphan detection
  - reset: truncate entity tables in dependency order
  - cleanup: find and remove FK orphans

Layer B (provider-pluggable backup/restore) lives in dazzle.cli.backup.
"""

from .cleanup import db_cleanup_impl
from .connection import get_connection, resolve_db_url
from .graph import build_dependency_graph, get_ref_fields, leaves_first, parents_first
from .reset import db_reset_impl
from .sql import quote_id
from .status import db_status_impl
from .verify import db_verify_impl

__all__ = [
    "build_dependency_graph",
    "db_cleanup_impl",
    "db_reset_impl",
    "db_status_impl",
    "db_verify_impl",
    "get_connection",
    "get_ref_fields",
    "leaves_first",
    "parents_first",
    "quote_id",
    "resolve_db_url",
]
