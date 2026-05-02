"""Full-text search IR types (#954 cycle 1).

Surfaces Postgres FTS via a per-entity ``search`` DSL block. Cycle 1
parses + propagates the spec; cycle 2 adds the Alembic migration that
creates the tsvector + GIN index; cycle 3 adds the
``/api/search/<entity>?q=...`` endpoint; cycle 4 wires
``display: search_box`` regions.

DSL shape::

    search on Manuscript:
      fields: title, content, author.name
      ranking:
        title: 4
        content: 1
      highlight: true
      tokenizer: english
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchField(BaseModel):
    """One indexed field in a :class:`SearchSpec`.

    Attributes:
        path: Dotted field path. Single-segment (``title``) for fields
            on the search entity itself, dotted (``author.name``) for
            traversal through a foreign-key reference. Cycle 2's
            migration walks the FK graph to expand these into the
            generated tsvector concatenation.
        weight: Postgres tsvector weight letter — A (highest), B, C,
            or D (lowest). Cycle 1 stores the integer the user typed
            (1..4); the migration in cycle 2 maps to the letter
            (4 → 'A', 3 → 'B', 2 → 'C', 1 → 'D').
    """

    path: str
    weight: int = Field(default=1, ge=1, le=4)

    model_config = ConfigDict(frozen=True)


class SearchSpec(BaseModel):
    """Per-entity full-text-search definition.

    Attributes:
        entity: Entity name being indexed (e.g. ``"Manuscript"``).
        fields: List of indexed fields with weights. Order is
            preserved — useful for the migration's column order.
        highlight: When True, the cycle-3 search endpoint returns
            ``ts_headline`` snippets alongside each hit.
        tokenizer: Postgres FTS configuration name
            (``"english"`` / ``"french"`` / ``"simple"`` / etc).
            Cycle 2 validates against the project's database catalogue.
    """

    entity: str
    fields: list[SearchField] = Field(default_factory=list)
    highlight: bool = False
    tokenizer: str = "english"

    model_config = ConfigDict(frozen=True)
