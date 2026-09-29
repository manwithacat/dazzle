"""A composing workspace makes its referenced module an actual dependency."""

from pathlib import Path

from dazzle.core.linker_impl import (
    build_symbol_table,
    check_unused_imports,
    resolve_dependencies,
)
from dazzle.core.parser import parse_modules


def test_workspace_region_source_counts_as_module_use(tmp_path: Path) -> None:
    core = tmp_path / "core.dsl"
    core.write_text(
        "module example.core\n"
        'app example "Example"\n'
        'entity Ticket "Ticket":\n'
        "  id: uuid pk\n"
        'surface ticket_list "Tickets":\n'
        "  uses entity Ticket\n"
        "  mode: list\n"
        "  section main:\n"
        '    field id "ID"\n'
    )
    views = tmp_path / "views.dsl"
    views.write_text(
        "module example.views\n"
        "use example.core\n"
        'workspace home "Home":\n'
        "  tickets:\n"
        "    source: Ticket\n"
        "    display: list\n"
        "    action: ticket_list\n"
    )

    modules = resolve_dependencies(parse_modules([core, views]))
    warnings = check_unused_imports(modules, build_symbol_table(modules))

    assert not any("example.views" in warning for warning in warnings)
