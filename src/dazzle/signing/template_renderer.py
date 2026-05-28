"""Minimal placeholder substitution for project-supplied signing templates.

ADR-0023 retired Jinja2 from the runtime. For signing templates, we
support either a Python callable (via ``signing_template:`` in the DSL)
or a ``.html.j2`` file with simple ``{{ row.field }}`` placeholders. This
module renders the file-based form using regex substitution — no
Jinja2 dependency. Conditionals, loops, and filters are intentionally
unsupported; projects that need them should use ``signing_template:``
callables which return arbitrary HTML.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

# Match {{ row.field_name }} and {{ entity.field_name }} placeholders.
# Whitespace inside the braces is tolerated.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(row|entity)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_signing_template_file(template_path: Path, *, row: Any, entity: Any) -> str:
    """Render a signing template file by substituting ``{{ row.X }}`` placeholders.

    Each match is replaced with the corresponding attribute, HTML-escaped
    so that user-supplied row data cannot inject HTML/JS into the page.

    Args:
        template_path: Absolute path to the .html.j2 file.
        row: Entity row object (pydantic model or similar) with field
            attributes accessible via getattr.
        entity: EntitySpec for the entity being rendered (mostly for
            ``{{ entity.name }}`` and ``{{ entity.label }}``).

    Returns:
        Rendered HTML string with placeholders substituted.

    Unknown placeholders (e.g. ``{{ row.nonexistent }}``) are replaced
    with an empty string.
    """
    raw = template_path.read_text(encoding="utf-8")

    def _replace(m: re.Match[str]) -> str:
        scope = m.group(1)
        attr = m.group(2)
        obj = row if scope == "row" else entity
        value = getattr(obj, attr, "")
        return html.escape(str(value))

    return _PLACEHOLDER_RE.sub(_replace, raw)


def find_signing_template(project_root: Path, entity_name: str) -> Path | None:
    """Look up the default signing template for an entity in the project.

    Convention: ``<project_root>/templates/letters/<entity_name>/default.html.j2``.

    Returns the path if it exists, else None.
    """
    candidate = project_root / "templates" / "letters" / entity_name / "default.html.j2"
    return candidate if candidate.is_file() else None
