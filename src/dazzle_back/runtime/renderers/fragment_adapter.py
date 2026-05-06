"""IR-to-Fragment translator for surface rendering.

Takes a SurfaceSpec + render context (rows, columns, etc. — same shape
as the Jinja path's context dict) and produces a Fragment tree. The
FragmentRenderer then emits HTML from the tree.

Plan 3 ships the minimum-viable adapter for `mode: list` only — enough
to render simple_task's task_list surface. Subsequent plans add detail,
form, and dashboard modes.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment import (
    EmptyState,
    Fragment,
    Heading,
    Region,
    Row,
    Stack,
    Surface,
    Table,
    Text,
)


class FragmentSurfaceAdapter:
    """Translate a SurfaceSpec + context into a Fragment tree."""

    def build(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Fragment:
        if surface.mode == SurfaceMode.LIST:
            return self._build_list(surface, ctx)
        if surface.mode == SurfaceMode.VIEW:
            return self._build_view(surface, ctx)
        raise NotImplementedError(
            f"FragmentSurfaceAdapter does not yet support mode {surface.mode.name!r}; "
            f"Plans 3+8 cover LIST and VIEW. CREATE/EDIT/CUSTOM land in Plan 9+."
        )

    def _build_list(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        title = surface.title or surface.name.replace("_", " ").title()
        items: list[dict[str, Any]] = ctx.get("items", [])
        columns: list[dict[str, Any]] = ctx.get("columns", [])

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items yet",
                description="Items will appear here when they are added.",
            )
        else:
            column_labels = tuple(col.get("label", col.get("key", "")) for col in columns)
            rows = tuple(
                tuple(
                    _format_cell(item.get(col["key"]), col.get("type", "text")) for col in columns
                )
                for item in items
            )
            body = Table(columns=column_labels, rows=rows)

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="list", body=body),
        )

    def _build_view(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        """Detail surface — single record's fields as a definition-list-shaped Region.

        Each field renders as a Row of (Heading-level-4 label, Text value).
        Stack groups them. The Region carries kind="detail" so CSS can
        target the layout (definition-list style with label + value columns).
        """
        title = surface.title or surface.name.replace("_", " ").title()
        fields: list[dict[str, Any]] = ctx.get("fields", [])

        body: Fragment
        if not fields:
            body = EmptyState(
                title="No data",
                description="This record has no displayable fields.",
            )
        else:
            rows = tuple(
                Row(
                    children=(
                        Heading(str(f.get("label", f.get("key", ""))), level=4),
                        Text(_format_cell(f.get("value"), str(f.get("kind", "text")))),
                    ),
                    align="start",
                )
                for f in fields
            )
            body = Stack(children=rows, gap="sm")

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="detail", body=body),
        )


def _format_cell(value: Any, kind: str) -> str:
    """Stringify a cell value for the typed Table.

    Plan 3 supports the most basic types only — text, str-coerced. Plan 6
    or later adds badge/bool/date/currency/ref support. Until then, we
    str-coerce everything and lose type-specific formatting; this is
    acceptable because the Jinja path remains the default for any surface
    that needs the richer formatting.
    """
    if value is None:
        return ""
    return str(value)
