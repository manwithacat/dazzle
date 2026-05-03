"""Postgres FTS schema generator (#954 cycle 2).

Bridges :class:`~dazzle.core.ir.search.SearchSpec` declarations into
the DDL the runtime needs to make full-text search work:

  * A ``GENERATED ALWAYS AS (... ) STORED`` ``tsvector`` column on
    each searchable entity, concatenating every declared field with
    its weight (A/B/C/D) under the chosen FTS configuration.
  * A GIN index on that generated column, so ``WHERE search_vector
    @@ websearch_to_tsquery(...)`` runs against the index rather
    than scanning the table.

The generator emits raw DDL strings rather than going through
SQLAlchemy's ``Column`` / ``Index`` API because:

  1. Generated columns referencing other columns aren't first-class
     in SQLAlchemy — they need ``Computed(...)`` plus dialect quirks,
     and even then the GIN index path requires raw DDL.
  2. The same migration hatch is needed for the cycle-5 pgvector
     work (``CREATE INDEX … USING ivfflat (embedding vector_cosine_ops)``);
     keeping the path uniform now means no rework when semantic
     search lands.

Cycle 2 scope (this module):
  * Lexical FTS only — single-entity fields with text-shaped types.
  * Dotted-path fields (``author.name``) currently emit a warning
    and skip; cycle 4+ will denormalise via trigger or expand the
    join at materialise-time.
  * Tokenizer validated against a static allow-list (Postgres ships
    the same ten or so configs across versions).

The runtime calls :func:`build_search_index_ddl` after
``metadata.create_all`` so the table exists before the ALTER lands.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from dazzle.core.ir.fields import FieldTypeKind

logger = logging.getLogger(__name__)


# Postgres ships these FTS configurations by default. Adopters who
# install pg_trgm / unaccent / custom dictionaries can extend the
# set via SQL out-of-band. We validate against the static list at
# index-DDL build time so a typo in `tokenizer:` fails loudly rather
# than producing an empty tsvector at query time.
_KNOWN_FTS_CONFIGS: frozenset[str] = frozenset(
    {
        "simple",
        "arabic",
        "armenian",
        "basque",
        "catalan",
        "danish",
        "dutch",
        "english",
        "finnish",
        "french",
        "german",
        "greek",
        "hindi",
        "hungarian",
        "indonesian",
        "irish",
        "italian",
        "lithuanian",
        "nepali",
        "norwegian",
        "portuguese",
        "romanian",
        "russian",
        "serbian",
        "spanish",
        "swedish",
        "tamil",
        "turkish",
        "yiddish",
    }
)

# Which field kinds make sense to drop into a tsvector. JSON could
# work via an expression (``data->>'title'``) but cycle 2 keeps the
# generator straightforward — JSON-targeted FTS is its own primitive.
_SEARCHABLE_KINDS: frozenset[FieldTypeKind] = frozenset(
    {
        FieldTypeKind.STR,
        FieldTypeKind.TEXT,
        FieldTypeKind.EMAIL,
        FieldTypeKind.URL,
    }
)

SEARCH_VECTOR_COLUMN = "search_vector"
"""Conventional name for the generated tsvector column. The cycle-3
endpoint queries against this name directly; the cycle-5 pgvector
column will use a parallel ``search_embedding`` slot to keep both
search modes runnable side-by-side."""


def _weight_letter(weight: int) -> str:
    """Map the user-typed integer weight (1..4) to Postgres letters.

    Postgres tsvector weights are A (highest) → D (lowest). The DSL
    accepts integers because they sort more intuitively (``weight: 4``
    reads as "more important than 1" without needing the operator to
    remember the letter convention).
    """
    if weight >= 4:
        return "A"
    if weight == 3:
        return "B"
    if weight == 2:
        return "C"
    return "D"


def _quote_ident(name: str) -> str:
    """Double-quote a Postgres identifier safely.

    Identifiers come from the AppSpec, not user input — but quoting
    defends against future misuse and keeps mixed-case entity names
    (e.g. ``Manuscript``) working without folding to lowercase.
    """
    return '"' + name.replace('"', '""') + '"'


def _validate_tokenizer(tokenizer: str, entity_name: str) -> str:
    """Return the tokenizer to use, defaulting to ``english`` on miss
    + logging a warning.

    Failing closed (raising) would block boot for a typo; failing
    open (defaulting) keeps the app running with a recoverable
    warning. Cycle 4 may add a CLI lint that surfaces the warning
    at validate-time.
    """
    config = (tokenizer or "english").strip().lower()
    if config not in _KNOWN_FTS_CONFIGS:
        logger.warning(  # nosemgrep
            "Unknown FTS tokenizer %r on entity %r — using default. Known configs: %s",
            tokenizer,
            entity_name,
            ", ".join(sorted(_KNOWN_FTS_CONFIGS)),
        )
        return "english"
    return config


def _resolve_searchable_field(entity: Any, path: str) -> Any | None:
    """Resolve a single-segment field path against *entity*'s fields.

    Returns the IR field when the path resolves to a text-shaped
    field on *entity* itself. Dotted paths (FK traversal) and
    non-text fields return ``None`` so the caller can skip + log.
    """
    if "." in path:
        return None
    for field in entity.fields:
        if field.name == path:
            if field.type.kind in _SEARCHABLE_KINDS:
                return field
            return None
    return None


def _build_concat_expression(
    entity: Any,
    spec: Any,
    config: str,
) -> str | None:
    """Build the inner expression for the GENERATED column.

    ``setweight(to_tsvector(config, coalesce(field, '')), 'X')``
    repeated per field, joined with ``||``. Returns ``None`` when no
    fields resolve to a searchable column on this entity (in which
    case the caller skips the index entirely).

    ``coalesce`` defends against NULL — without it the entire
    tsvector becomes NULL on any NULL field and the index entry
    disappears.
    """
    parts: list[str] = []
    for sf in spec.fields:
        path = sf.path
        field = _resolve_searchable_field(entity, path)
        if field is None:
            if "." in path:
                logger.warning(
                    "Search field %r on entity %r is a dotted path — skipping. "
                    "Cycle 2 only indexes columns on the search entity itself; "
                    "FK traversal lands in a later cycle.",
                    path,
                    spec.entity,
                )
            else:
                logger.warning(
                    "Search field %r on entity %r is not a text-shaped column "
                    "(needs str/text/email/url) — skipping.",
                    path,
                    spec.entity,
                )
            continue
        letter = _weight_letter(sf.weight)
        col = _quote_ident(field.name)
        parts.append(f"setweight(to_tsvector('{config}', coalesce({col}, '')), '{letter}')")
    if not parts:
        return None
    return " || ".join(parts)


def build_search_index_ddl(
    entities: Iterable[Any],
    searches: Iterable[Any],
) -> list[str]:
    """Return the DDL strings required to set up FTS for every SearchSpec.

    Each entity that has a SearchSpec gets two statements:

      1. ``ALTER TABLE … ADD COLUMN IF NOT EXISTS search_vector
         tsvector GENERATED ALWAYS AS (…) STORED``
      2. ``CREATE INDEX IF NOT EXISTS … ON … USING GIN (search_vector)``

    The runtime executes them in order via ``engine.execute()`` after
    ``metadata.create_all`` — the table must exist before the ALTER
    lands. ``IF NOT EXISTS`` makes both statements idempotent so
    repeated boots / migration replays don't error.

    Returns an empty list when ``searches`` is empty or no spec
    references an actual indexable field.
    """
    entity_by_name = {e.name: e for e in entities}
    out: list[str] = []
    for spec in searches:
        entity = entity_by_name.get(spec.entity)
        if entity is None:
            logger.warning(
                "Search spec references unknown entity %r — skipping",
                spec.entity,
            )
            continue
        config = _validate_tokenizer(spec.tokenizer, spec.entity)
        expr = _build_concat_expression(entity, spec, config)
        if expr is None:
            logger.info(
                "Search spec on entity %r has no resolvable searchable fields — "
                "skipping index creation",
                spec.entity,
            )
            continue
        table = _quote_ident(spec.entity)
        column = _quote_ident(SEARCH_VECTOR_COLUMN)
        index_name = _quote_ident(f"ix_{spec.entity.lower()}_{SEARCH_VECTOR_COLUMN}")
        out.append(
            f"ALTER TABLE {table} "
            f"ADD COLUMN IF NOT EXISTS {column} tsvector "
            f"GENERATED ALWAYS AS ({expr}) STORED"
        )
        out.append(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} USING GIN ({column})")
    return out


__all__ = [
    "SEARCH_VECTOR_COLUMN",
    "build_search_index_ddl",
]
