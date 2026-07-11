"""HYPERPART: grid (extension: dz-grid-edit) — contract module.

Single source of truth for the inline-edit seam: the typed ingestion
model (what the server-side producer must supply), the DOM contract (what
controllers/dz-grid-edit.js requires — mirrors its prose header), and an
executable FastAPI exemplar mirroring how Dazzle feeds it. The exemplar
payloads deliberately include the #1573 producer shapes (dict / tuple /
bare-string options) as permanent regression documentation.
"""

import html
import json
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator, model_validator

from contracts._kit import DomContract, JsonPairs, Node, OneOf, Present

Kind = Literal["text", "date", "bool", "select"]


class GridEditCell(BaseModel):
    """One editable cell's seam data — the single canonical ingestion shape."""

    col: str
    kind: Kind
    value: str
    label: str  # a11y label for the editor
    options: list[tuple[str, str]] | None = None  # [(value, label), …] — select only

    @field_validator("options", mode="before")
    @classmethod
    def _normalise_options(cls, v: object) -> object:
        # THE one normalisation boundary (#1573): producers may hold dicts
        # ({"value","label"}), pairs, or bare strings; all become pairs here.
        if v is None:
            return v
        out: list[tuple[str, str]] = []
        for o in v:  # type: ignore[attr-defined]
            if isinstance(o, dict):
                out.append((str(o.get("value", "")), str(o.get("label", ""))))
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append((str(o[0]), str(o[1])))
            else:
                out.append((str(o), str(o)))
        return out

    @model_validator(mode="after")
    def _select_requires_options(self) -> "GridEditCell":
        if self.kind == "select" and not self.options:
            raise ValueError("kind='select' requires options")
        if self.kind != "select" and self.options:
            raise ValueError(f"kind={self.kind!r} must not carry options")
        return self


DOM_CONTRACT = DomContract(
    part="grid-edit",
    root="[data-dz-grid][data-dz-grid-edit-url]",
    nodes=(
        Node(
            "[data-dz-grid-edit]",
            attrs={
                "data-dz-edit-kind": OneOf("text", "date", "bool", "select"),
                "data-dz-edit-value": Present(),
                "data-dz-edit-label": Present(),
                "data-dz-edit-options": JsonPairs(required_when={"data-dz-edit-kind": "select"}),
            },
        ),
    ),
)

EXEMPLARS: list[GridEditCell] = [
    GridEditCell(col="title", kind="text", value="Fix the door", label="Title"),
    GridEditCell(col="due", kind="date", value="2026-07-10", label="Due date"),
    GridEditCell(col="done", kind="bool", value="false", label="Done"),
    # The #1573 producer shapes — permanent, executable regression docs:
    GridEditCell(
        col="status",
        kind="select",
        value="open",
        label="Status",
        options=[{"value": "open", "label": "Open"}],
    ),  # dict producer
    GridEditCell(
        col="severity",
        kind="select",
        value="p1",
        label="Severity",
        options=[("p1", "P1"), ("p2", "P2")],
    ),  # tuple producer
    GridEditCell(
        col="lane",
        kind="select",
        value="triage",
        label="Lane",
        options=["triage", "active", "done"],
    ),  # bare-string producer
]


def render(cell: GridEditCell) -> str:
    """Model → conforming display-span fragment (the seam the controller reads)."""
    opts = ""
    if cell.kind == "select" and cell.options is not None:
        pairs = json.dumps([[v, label] for v, label in cell.options])
        opts = f' data-dz-edit-options="{html.escape(pairs, quote=True)}"'
    return (
        f'<span class="dz-tr-cell-display" '
        f'data-dz-grid-edit="{html.escape(cell.col, quote=True)}" '
        f'data-dz-edit-kind="{cell.kind}" '
        f'data-dz-edit-value="{html.escape(cell.value, quote=True)}" '
        f'data-dz-edit-label="{html.escape(cell.label, quote=True)}"{opts}>'
        f"{html.escape(cell.value)}</span>"
    )


app = FastAPI(title="grid-edit exemplar — how a server feeds the inline-edit seam")


@app.get("/rows", response_class=HTMLResponse)
def rows() -> str:
    """A tbody fragment: what a real endpoint returns to fill the grid.
    Mirrors Dazzle's shape: the grid ROOT (with data-dz-grid-edit-url)
    is page furniture; this endpoint returns rows whose editable cells
    carry the seam spans."""
    cells = "".join(f"<td>{render(c)}</td>" for c in EXEMPLARS[:3])
    return f'<tr id="row-1">{cells}</tr>'
