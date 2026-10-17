"""
List column vocabulary shared by workspace regions and list surfaces (#1792).

One shape — :class:`ColumnSpec` — says which field a list column shows and how
it is sized. A region names its columns with ``columns:``; a list surface's
``field`` lines carry the same ``width:`` / ``truncate`` modifiers. Both reach
the renderer as the same data.

The list page-size vocabulary lives here too: one framework default and one
upper bound, imported by every page-size site (API query default, region
fetch, pager fallback) so the defaults cannot drift apart again.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

# Rows per page when neither the request nor the DSL says otherwise.
DEFAULT_PAGE_SIZE = 20
# Upper bound for a declared `page_size:` and for the list API's `page_size` query.
MAX_PAGE_SIZE = 100

# `width:` accepts a positive number followed by one of these units.
COLUMN_WIDTH_UNITS: tuple[str, ...] = ("%", "rem", "ch")

_WIDTH_RE = re.compile(r"^(\d+(?:\.\d+)?)(%|rem|ch)$")


def column_width_error(width: str) -> str | None:
    """Return why ``width`` is not a valid column width, or ``None`` when it is.

    Valid: ``34%``, ``12rem``, ``20ch`` (decimals allowed). A percentage must be
    above 0 and at most 100; rem/ch must be above 0.
    """
    m = _WIDTH_RE.match(width)
    if m is None:
        return (
            f"column width {width!r} must be a number followed by "
            f"{', '.join(COLUMN_WIDTH_UNITS)} (e.g. 34%, 12rem, 20ch)"
        )
    value = float(m.group(1))
    if value <= 0:
        return f"column width {width!r} must be greater than 0"
    if m.group(2) == "%" and value > 100:
        return f"column width {width!r} cannot exceed 100%"
    return None


class ColumnSpec(BaseModel):
    """One list column: the field it shows and optional sizing hints.

    Attributes:
        field: Field name on the list's entity (a ref field shows the related
            record's display name). Dotted paths are not supported.
        width: Width hint for the column — ``<n>%``, ``<n>rem`` or ``<n>ch``.
            ``None`` = the column takes an equal share of the remaining width.
        truncate: ``True`` forces the one-line ellipsis wrapper, ``False``
            lets the cell wrap; ``None`` keeps the list's default for the cell
            type.
    """

    field: str
    width: str | None = None
    truncate: bool | None = None

    model_config = ConfigDict(frozen=True)

    @field_validator("width")
    @classmethod
    def _check_width(cls, v: str | None) -> str | None:
        if v is None:
            return v
        err = column_width_error(v)
        if err is not None:
            raise ValueError(err)
        return v

    @property
    def has_hints(self) -> bool:
        """True when the column carries a width or truncate hint."""
        return self.width is not None or self.truncate is not None
