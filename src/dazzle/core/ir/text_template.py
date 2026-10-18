"""Row-interpolating text templates (#1815, #1810).

One small template type shared by a view surface's ``title:`` and the labels
of a surface's ``ux: breadcrumb:`` trail::

    title: "{agreement_type|upper} — {school.name}"

A placeholder names a field of the surface's entity, or an FK path of at most
:data:`MAX_TEMPLATE_HOPS` hops (``ref_field.field``,
``ref_field.ref_field.field`` — #1825), optionally followed by ``|filter``
steps from :data:`TEXT_TEMPLATE_FILTERS`. ``{{`` and ``}}`` are literal braces.

The source string is parsed ONCE into segments at DSL parse time; nothing is
evaluated as code at runtime. Field / path resolution against the entity is a
``dazzle validate`` concern (``validate_surface_titles_and_breadcrumbs``);
rendering against a row lives in ``dazzle.render.text_template``.
"""

import re

from pydantic import BaseModel, ConfigDict

TEXT_TEMPLATE_FILTERS: frozenset[str] = frozenset({"upper", "lower", "title", "date", "label"})

#: FK hops a template path may follow (#1825): ``a.b.field`` is two.
MAX_TEMPLATE_HOPS = 2

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class TextTemplateError(ValueError):
    """A malformed template source. The message leads with its ``E_*`` code."""


class TemplatePlaceholder(BaseModel):
    """One ``{path|filter|…}`` slot.

    Attributes:
        path: ``("field",)``, ``("ref_field", "field")`` or
            ``("ref_field", "ref_field", "field")`` — at most
            :data:`MAX_TEMPLATE_HOPS` FK hops (#1825).
        filters: Applied left to right; each is in :data:`TEXT_TEMPLATE_FILTERS`.
    """

    path: tuple[str, ...]
    filters: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


class TemplateSegment(BaseModel):
    """Literal text, or a placeholder (exactly one is meaningful)."""

    text: str = ""
    placeholder: TemplatePlaceholder | None = None

    model_config = ConfigDict(frozen=True)


class TextTemplate(BaseModel):
    """A parsed text template: the authored source plus its segments."""

    source: str
    segments: tuple[TemplateSegment, ...] = ()

    model_config = ConfigDict(frozen=True)

    @property
    def placeholders(self) -> tuple[TemplatePlaceholder, ...]:
        return tuple(s.placeholder for s in self.segments if s.placeholder is not None)

    @property
    def is_static(self) -> bool:
        """True when the template interpolates nothing."""
        return not self.placeholders

    def static_text(self) -> str:
        """The literal text (placeholders contribute nothing)."""
        return "".join(s.text for s in self.segments if s.placeholder is None)


def parse_template_path(path_text: str, source: str) -> tuple[str, ...]:
    """``a.b.c`` → ``("a", "b", "c")``; shared by placeholders and row-bound crumb links.

    Raises :class:`TextTemplateError` (``E_TEMPLATE_BAD_PATH`` /
    ``E_TEMPLATE_PATH_TOO_DEEP``) for a malformed or over-deep path. Whether
    each hop is a ``ref`` is a ``dazzle validate`` concern.
    """
    path = tuple(p.strip() for p in path_text.split("."))
    if any(not _IDENT_RE.fullmatch(p) for p in path):
        raise TextTemplateError(
            f"E_TEMPLATE_BAD_PATH: `{{{path_text}}}` in {source!r} is not a field name "
            f"or a `ref_field.field` path."
        )
    if len(path) > MAX_TEMPLATE_HOPS + 1:
        raise TextTemplateError(
            f"E_TEMPLATE_PATH_TOO_DEEP: `{{{path_text}}}` in {source!r} hops more than "
            f"{MAX_TEMPLATE_HOPS} times; a placeholder is a field or at most "
            f"{MAX_TEMPLATE_HOPS} FK hops (`ref_field.ref_field.field`)."
        )
    return path


def _parse_placeholder(body: str, source: str) -> TemplatePlaceholder:
    parts = [p.strip() for p in body.split("|")]
    path_text, filters = parts[0], tuple(parts[1:])
    if not path_text:
        raise TextTemplateError(f"E_TEMPLATE_EMPTY_PLACEHOLDER: empty `{{}}` in {source!r}.")
    path = parse_template_path(path_text, source)
    for f in filters:
        if f not in TEXT_TEMPLATE_FILTERS:
            raise TextTemplateError(
                f"E_TEMPLATE_UNKNOWN_FILTER: `|{f}` in {source!r}; filters are "
                f"{sorted(TEXT_TEMPLATE_FILTERS)}."
            )
    return TemplatePlaceholder(path=path, filters=filters)


def parse_text_template(source: str) -> TextTemplate:
    """Parse ``source`` into a :class:`TextTemplate` or raise :class:`TextTemplateError`."""
    segments: list[TemplateSegment] = []
    literal: list[str] = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch == "{" and source.startswith("{{", i):
            literal.append("{")
            i += 2
        elif ch == "}" and source.startswith("}}", i):
            literal.append("}")
            i += 2
        elif ch == "{":
            end = source.find("}", i + 1)
            if end == -1:
                raise TextTemplateError(f"E_TEMPLATE_UNCLOSED: unclosed `{{` in {source!r}.")
            if literal:
                segments.append(TemplateSegment(text="".join(literal)))
                literal = []
            segments.append(
                TemplateSegment(placeholder=_parse_placeholder(source[i + 1 : end], source))
            )
            i = end + 1
        elif ch == "}":
            raise TextTemplateError(
                f"E_TEMPLATE_UNOPENED: stray `}}` in {source!r} (write `}}}}` for a literal)."
            )
        else:
            literal.append(ch)
            i += 1
    if literal:
        segments.append(TemplateSegment(text="".join(literal)))
    return TextTemplate(source=source, segments=tuple(segments))
