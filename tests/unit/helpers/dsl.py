"""DSL parse helpers for construct-level parser tests.

``parse_fragment`` parses one module source through the public
``parse_dsl`` entry point and returns its ``ModuleFragment``.
``region_config`` wraps a ``<display>_config:`` block body in the
module/app/entity/workspace boilerplate every typed region config needs and
returns the parsed config object (or raises ``ParseError``). The caller
asserts on what comes back.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment


def parse_fragment(source: str) -> ModuleFragment:
    """Parse a whole module source and return its fragment."""
    return parse_dsl(textwrap.dedent(source), Path("test.dsl"))[5]


def entity_named(source: str, name: str) -> Any:
    """Parse a module source and return the entity called ``name``."""
    for entity in parse_fragment(source).entities:
        if entity.name == name:
            return entity
    raise AssertionError(f"entity {name} not found in parsed fragment")


def region_config(*, entity: str, display: str, body: str) -> Any:
    """Parse a one-region workspace and return ``region.<display>_config``.

    ``entity`` is a full ``entity`` declaration (its name becomes the region
    source); ``body`` is the config block body at any indentation.
    """
    entity_src = textwrap.dedent(entity).strip("\n")
    entity_name = entity_src.split()[1]
    config_body = textwrap.indent(textwrap.dedent(body).strip("\n"), " " * 6)
    source = (
        'module ops\napp demo_app "Demo"\n\n'
        f"{entity_src}\n\n"
        'workspace dash "Dash":\n'
        "  region:\n"
        f"    source: {entity_name}\n"
        f"    display: {display}\n"
        f"    {display}_config:\n"
        f"{config_body}\n"
    )
    region = parse_dsl(source, Path("test.dsl"))[5].workspaces[0].regions[0]
    return getattr(region, f"{display}_config")
