from . import ir
from .errors import LinkError
from .linker_impl import (
    build_symbol_table,
    merge_fragments,
    resolve_dependencies,
    validate_module_access,
    validate_references,
)


def build_appspec(modules: list[ir.ModuleIR], root_module_name: str) -> ir.AppSpec:
    """
    Build a complete AppSpec by merging and linking all modules.

    Performs:
    1. Module dependency resolution (topological sort)
    2. Cycle detection
    3. Symbol table building
    4. Duplicate detection
    5. Reference validation
    6. Fragment merging

    Args:
        modules: List of parsed modules
        root_module_name: Name of the root module (from dazzle.toml)

    Returns:
        Complete, linked AppSpec

    Raises:
        LinkError: If linking fails (cycles, duplicates, unresolved refs, etc.)
    """
    if not modules:
        raise LinkError("No modules to link")

    if not root_module_name:
        raise LinkError("project.root must be set in dazzle.toml")

    # Find root module
    root_module = None
    for module in modules:
        if module.name == root_module_name:
            root_module = module
            break

    if not root_module:
        raise LinkError(
            f"Root module '{root_module_name}' not found. "
            f"Available modules: {[m.name for m in modules]}"
        )

    # Extract app name and title from root module
    app_name = root_module.app_name or root_module_name
    app_title = root_module.app_title or app_name

    # Stage 3: Full linking implementation

    # 1. Resolve dependencies and detect cycles
    sorted_modules = resolve_dependencies(modules)

    # 2. Build symbol table (detects duplicates)
    symbols = build_symbol_table(sorted_modules)

    # 3. Validate module access (enforce use declarations)
    access_errors = validate_module_access(sorted_modules, symbols)
    if access_errors:
        error_msg = "Module access validation failed:\n" + "\n".join(
            f"  - {e}" for e in access_errors
        )
        raise LinkError(error_msg)

    # 4. Validate all cross-references
    errors = validate_references(symbols)
    if errors:
        error_msg = "Reference validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise LinkError(error_msg)

    # 5. Merge fragments into unified structure
    merged_fragment = merge_fragments(sorted_modules, symbols)

    # 6. Build final AppSpec
    return ir.AppSpec(
        name=app_name,
        title=app_title,
        version="0.1.0",
        domain=ir.DomainSpec(entities=merged_fragment.entities),
        surfaces=merged_fragment.surfaces,
        experiences=merged_fragment.experiences,
        services=merged_fragment.services,
        foreign_models=merged_fragment.foreign_models,
        integrations=merged_fragment.integrations,
        tests=merged_fragment.tests,
        metadata={
            "modules": [m.name for m in sorted_modules],
            "root_module": root_module_name,
        },
    )
