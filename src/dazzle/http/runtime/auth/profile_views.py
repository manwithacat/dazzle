"""Typed-Fragment view for the member's own profile (auth Plan 3c.ii)."""

from typing import Any, cast

from dazzle.render.fragment import (
    URL,
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    Text,
)

_CSS = ("/static/dist/dazzle.min.css",)
_JS = ("/static/dist/dazzle.min.js",)

# Map the editable string-valued field kinds → Fragment Field input kinds. (The
# route only offers str/text/enum until typed-field form coercion lands.)
_KIND = {
    "str": "text",
    "text": "textarea",
    "enum": "text",
}


def build_my_profile_view(
    *,
    product_name: str,
    org_name: str,
    fields: list[dict[str, Any]],
    current: dict[str, Any],
) -> Page:
    """``fields``: [{name, label, kind}]; ``current``: the existing profile values (or {})."""
    body: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=f"Your profile in {org_name}", level=1),
        Text(body="Update your member profile.", tone="muted"),
    ]
    form_fields = tuple(
        Field(
            name=f["name"],
            label=f["label"],
            # _KIND only maps to valid Field input kinds; cast for the Literal type.
            kind=cast(Any, _KIND.get(f["kind"], "text")),
            initial_value=str(current.get(f["name"], "") or ""),
        )
        for f in fields
    )
    if form_fields:
        body.append(
            FormStack(
                action=URL("/me/profile"),
                method="POST",
                fields=form_fields,
                submit=Submit(label="Save profile", variant="primary"),
            )
        )
    else:
        body.append(Text(body="This profile has no editable fields.", tone="muted"))
    return Page(
        title=f"Your profile — {product_name}",
        body=Stack(children=tuple(body)),
        css_links=_CSS,
        js_scripts=_JS,
    )
