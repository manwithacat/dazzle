from pathlib import Path
from typing import List

from . import ir
from .dsl_parser import parse_dsl


def parse_modules(files: List[Path]) -> List[ir.ModuleIR]:
    """
    Parse DSL files into ModuleIR structures.

    Uses the full DSL parser to extract:
    - Module name and use declarations
    - App name and title
    - All DSL constructs (entities, surfaces, experiences, etc.)

    Args:
        files: List of .dsl file paths to parse

    Returns:
        List of ModuleIR objects with complete parsed IR fragments
    """
    modules: List[ir.ModuleIR] = []

    for f in files:
        text = f.read_text(encoding="utf-8")

        # Parse DSL file
        module_name, app_name, app_title, uses, fragment = parse_dsl(text, f)

        # Use filename as fallback module name
        if module_name is None:
            module_name = f.stem

        modules.append(
            ir.ModuleIR(
                name=module_name,
                file=f,
                app_name=app_name,
                app_title=app_title,
                uses=uses,
                fragment=fragment,
            )
        )

    return modules