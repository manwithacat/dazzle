from . import ir
from .archetype_expander import expand_archetypes, generate_archetype_surfaces
from .errors import LinkError
from .ir.security import SecurityConfig, SecurityProfile
from .linker_impl import (
    build_symbol_table,
    check_unused_imports,
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

    # Build security config from app config (v0.11.0)
    security_config = _build_security_config(root_module.app_config)

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

    # 5. Expand archetypes (v0.10.3)
    # - Merge fields from extended archetypes
    # - Apply semantic archetype expansions (settings, tenant, tenant_settings)
    # - Inject tenant FK into non-settings entities
    expanded_entities = expand_archetypes(list(symbols.entities.values()), symbols)

    # Update symbol table with expanded entities
    symbols.entities = {e.name: e for e in expanded_entities}

    # 6. Generate auto-surfaces for semantic archetypes
    existing_surfaces = list(symbols.surfaces.values())
    auto_surfaces = generate_archetype_surfaces(expanded_entities, existing_surfaces)

    # Add auto-generated surfaces to symbol table
    for surface in auto_surfaces:
        symbols.surfaces[surface.name] = surface

    # 7. Check for unused imports (v0.14.1)
    unused_import_warnings = check_unused_imports(sorted_modules, symbols)

    # 8. Merge fragments into unified structure
    merged_fragment = merge_fragments(sorted_modules, symbols)

    # 9. Build final AppSpec
    return ir.AppSpec(
        name=app_name,
        title=app_title,
        version="0.1.0",
        domain=ir.DomainSpec(entities=merged_fragment.entities),
        surfaces=merged_fragment.surfaces,
        workspaces=merged_fragment.workspaces,
        experiences=merged_fragment.experiences,
        apis=merged_fragment.apis,
        foreign_models=merged_fragment.foreign_models,
        integrations=merged_fragment.integrations,
        tests=merged_fragment.tests,
        personas=merged_fragment.personas,  # v0.8.5
        scenarios=merged_fragment.scenarios,  # v0.8.5
        stories=merged_fragment.stories,  # v0.22.0 Stories
        security=security_config,  # v0.11.0 Security
        llm_config=merged_fragment.llm_config,  # v0.21.0 LLM Jobs
        llm_models=merged_fragment.llm_models,  # v0.21.0 LLM Jobs
        llm_intents=merged_fragment.llm_intents,  # v0.21.0 LLM Jobs
        processes=merged_fragment.processes,  # v0.23.0 Process Workflows
        schedules=merged_fragment.schedules,  # v0.23.0 Process Workflows
        ledgers=merged_fragment.ledgers,  # v0.24.0 TigerBeetle Ledgers
        transactions=merged_fragment.transactions,  # v0.24.0 TigerBeetle Ledgers
        metadata={
            "modules": [m.name for m in sorted_modules],
            "root_module": root_module_name,
            "link_warnings": unused_import_warnings,  # v0.14.1
        },
    )


def _build_security_config(app_config: ir.AppConfigSpec | None) -> SecurityConfig:
    """
    Build SecurityConfig from app configuration.

    Args:
        app_config: App configuration from root module

    Returns:
        SecurityConfig with profile-based defaults
    """
    if app_config is None:
        return SecurityConfig.from_profile(SecurityProfile.BASIC)

    # Parse security profile
    profile_str = app_config.security_profile.lower()
    try:
        profile = SecurityProfile(profile_str)
    except ValueError:
        # Default to basic if invalid profile
        profile = SecurityProfile.BASIC

    # Build config with profile defaults
    return SecurityConfig.from_profile(
        profile,
        multi_tenant=app_config.multi_tenant,
    )
