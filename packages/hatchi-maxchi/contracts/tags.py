"""HYPERPART: tags — comma-joined native input, chips progressive enhancement."""

from __future__ import annotations

import html

from pydantic import BaseModel, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tags",
    root="[data-dz-tags]",
    nodes=(Node("[data-dz-tags]", attrs={"name": Present()}),),
)


class TagsField(BaseModel):
    name: str
    field_id: str
    label: str
    tags: list[str] = []
    placeholder: str = ""

    @field_validator("tags", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


EXEMPLARS: list[TagsField] = [
    TagsField(
        name="labels",
        field_id="tags-labels",
        label="Labels",
        tags=["urgent", "backend"],
        placeholder="Add a label…",
    ),
    TagsField(name="skills", field_id="tags-skills", label="Skills", tags="python,rust"),
]


def render(field: TagsField) -> str:
    joined = ",".join(field.tags)
    return (
        f'<label class="dz-field" for="{html.escape(field.field_id, quote=True)}">'
        f'<span class="dz-field__label">{html.escape(field.label)}</span>'
        f'<input id="{html.escape(field.field_id, quote=True)}" '
        f'name="{html.escape(field.name, quote=True)}" type="text" data-dz-tags '
        f'class="dz-form-input" value="{html.escape(joined, quote=True)}" '
        f'placeholder="{html.escape(field.placeholder, quote=True)}"></label>'
    )


__all__ = ["DOM_CONTRACT", "TagsField", "EXEMPLARS", "render"]
