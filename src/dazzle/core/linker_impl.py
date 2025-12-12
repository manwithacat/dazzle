"""
Module linker implementation for DAZZLE.

Handles dependency resolution, symbol table building, and reference validation.
"""

from collections import deque
from dataclasses import dataclass, field

from . import ir
from .errors import LinkError


@dataclass
class SymbolTable:
    """
    Symbol table for tracking all named definitions across modules.

    Tracks entities, surfaces, workspaces, experiences, APIs, foreign models,
    integrations, tests, and archetypes to enable cross-module reference resolution.
    """

    entities: dict[str, ir.EntitySpec] = field(default_factory=dict)
    surfaces: dict[str, ir.SurfaceSpec] = field(default_factory=dict)
    workspaces: dict[str, ir.WorkspaceSpec] = field(default_factory=dict)
    experiences: dict[str, ir.ExperienceSpec] = field(default_factory=dict)
    apis: dict[str, ir.APISpec] = field(default_factory=dict)
    foreign_models: dict[str, ir.ForeignModelSpec] = field(default_factory=dict)
    integrations: dict[str, ir.IntegrationSpec] = field(default_factory=dict)
    tests: dict[str, ir.TestSpec] = field(default_factory=dict)
    personas: dict[str, ir.PersonaSpec] = field(default_factory=dict)  # v0.8.5
    scenarios: dict[str, ir.ScenarioSpec] = field(default_factory=dict)  # v0.8.5
    archetypes: dict[str, ir.ArchetypeSpec] = field(default_factory=dict)  # v0.10.3

    # Track which module each symbol came from (for error reporting)
    symbol_sources: dict[str, str] = field(default_factory=dict)

    def add_entity(self, entity: ir.EntitySpec, module_name: str) -> None:
        """Add entity to symbol table, checking for duplicates."""
        if entity.name in self.entities:
            existing_module = self.symbol_sources.get(entity.name, "unknown")
            raise LinkError(
                f"Duplicate entity '{entity.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.entities[entity.name] = entity
        self.symbol_sources[entity.name] = module_name

    def add_surface(self, surface: ir.SurfaceSpec, module_name: str) -> None:
        """Add surface to symbol table, checking for duplicates."""
        if surface.name in self.surfaces:
            existing_module = self.symbol_sources.get(surface.name, "unknown")
            raise LinkError(
                f"Duplicate surface '{surface.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.surfaces[surface.name] = surface
        self.symbol_sources[surface.name] = module_name

    def add_workspace(self, workspace: ir.WorkspaceSpec, module_name: str) -> None:
        """Add workspace to symbol table, checking for duplicates."""
        if workspace.name in self.workspaces:
            existing_module = self.symbol_sources.get(workspace.name, "unknown")
            raise LinkError(
                f"Duplicate workspace '{workspace.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.workspaces[workspace.name] = workspace
        self.symbol_sources[workspace.name] = module_name

    def add_experience(self, experience: ir.ExperienceSpec, module_name: str) -> None:
        """Add experience to symbol table, checking for duplicates."""
        if experience.name in self.experiences:
            existing_module = self.symbol_sources.get(experience.name, "unknown")
            raise LinkError(
                f"Duplicate experience '{experience.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.experiences[experience.name] = experience
        self.symbol_sources[experience.name] = module_name

    def add_api(self, api: ir.APISpec, module_name: str) -> None:
        """Add external API to symbol table, checking for duplicates."""
        if api.name in self.apis:
            existing_module = self.symbol_sources.get(api.name, "unknown")
            raise LinkError(
                f"Duplicate API '{api.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.apis[api.name] = api
        self.symbol_sources[api.name] = module_name

    def add_foreign_model(self, foreign_model: ir.ForeignModelSpec, module_name: str) -> None:
        """Add foreign model to symbol table, checking for duplicates."""
        if foreign_model.name in self.foreign_models:
            existing_module = self.symbol_sources.get(foreign_model.name, "unknown")
            raise LinkError(
                f"Duplicate foreign model '{foreign_model.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.foreign_models[foreign_model.name] = foreign_model
        self.symbol_sources[foreign_model.name] = module_name

    def add_integration(self, integration: ir.IntegrationSpec, module_name: str) -> None:
        """Add integration to symbol table, checking for duplicates."""
        if integration.name in self.integrations:
            existing_module = self.symbol_sources.get(integration.name, "unknown")
            raise LinkError(
                f"Duplicate integration '{integration.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.integrations[integration.name] = integration
        self.symbol_sources[integration.name] = module_name

    def add_test(self, test: ir.TestSpec, module_name: str) -> None:
        """Add test to symbol table, checking for duplicates."""
        if test.name in self.tests:
            existing_module = self.symbol_sources.get(test.name, "unknown")
            raise LinkError(
                f"Duplicate test '{test.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.tests[test.name] = test
        self.symbol_sources[test.name] = module_name

    def add_persona(self, persona: ir.PersonaSpec, module_name: str) -> None:
        """Add persona to symbol table, checking for duplicates (v0.8.5)."""
        if persona.id in self.personas:
            existing_module = self.symbol_sources.get(persona.id, "unknown")
            raise LinkError(
                f"Duplicate persona '{persona.id}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.personas[persona.id] = persona
        self.symbol_sources[persona.id] = module_name

    def add_scenario(self, scenario: ir.ScenarioSpec, module_name: str) -> None:
        """Add scenario to symbol table, checking for duplicates (v0.8.5)."""
        if scenario.id in self.scenarios:
            existing_module = self.symbol_sources.get(scenario.id, "unknown")
            raise LinkError(
                f"Duplicate scenario '{scenario.id}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.scenarios[scenario.id] = scenario
        self.symbol_sources[scenario.id] = module_name

    def add_archetype(self, archetype: ir.ArchetypeSpec, module_name: str) -> None:
        """Add archetype to symbol table, checking for duplicates (v0.10.3)."""
        if archetype.name in self.archetypes:
            existing_module = self.symbol_sources.get(archetype.name, "unknown")
            raise LinkError(
                f"Duplicate archetype '{archetype.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.archetypes[archetype.name] = archetype
        self.symbol_sources[archetype.name] = module_name


def resolve_dependencies(modules: list[ir.ModuleIR]) -> list[ir.ModuleIR]:
    """
    Resolve module dependencies and return modules in dependency order.

    Uses topological sort to order modules such that dependencies come before dependents.
    Detects circular dependencies.

    Args:
        modules: List of modules to resolve

    Returns:
        Modules in dependency order (dependencies first)

    Raises:
        LinkError: If circular dependency detected or missing module
    """
    # Check for duplicate module names before building map
    seen_names: dict[str, ir.ModuleIR] = {}
    for module in modules:
        if module.name in seen_names:
            existing = seen_names[module.name]
            raise LinkError(
                f"Duplicate module name '{module.name}' defined in multiple files:\n"
                f"  - {existing.file}\n"
                f"  - {module.file}\n"
                f"Each DSL file should declare a unique module name, or files with "
                f"the same module should be merged."
            )
        seen_names[module.name] = module

    # Build dependency graph
    module_map = seen_names  # Already built during duplicate check
    dependencies: dict[str, set[str]] = {m.name: set(m.uses) for m in modules}

    # Check for missing dependencies
    for module_name, deps in dependencies.items():
        for dep in deps:
            if dep not in module_map:
                raise LinkError(
                    f"Module '{module_name}' depends on '{dep}', but '{dep}' is not defined. "
                    f"Available modules: {list(module_map.keys())}"
                )

    # Topological sort using Kahn's algorithm
    # in_degree[X] = number of dependencies X has (modules X uses)
    in_degree = {name: len(deps) for name, deps in dependencies.items()}

    # Find modules with no dependencies (can be processed first)
    queue = deque([name for name, degree in in_degree.items() if degree == 0])
    sorted_modules = []

    while queue:
        module_name = queue.popleft()
        sorted_modules.append(module_map[module_name])

        # Find modules that depend on this one and reduce their in-degree
        for other_name, deps in dependencies.items():
            if module_name in deps:
                in_degree[other_name] -= 1
                if in_degree[other_name] == 0:
                    queue.append(other_name)

    # If we haven't processed all modules, there's a cycle
    if len(sorted_modules) != len(modules):
        unprocessed = set(module_map.keys()) - {m.name for m in sorted_modules}
        raise LinkError(f"Circular dependency detected involving modules: {unprocessed}")

    return sorted_modules


def build_symbol_table(modules: list[ir.ModuleIR]) -> SymbolTable:
    """
    Build unified symbol table from all modules.

    Args:
        modules: List of modules in dependency order

    Returns:
        SymbolTable with all definitions

    Raises:
        LinkError: If duplicate definitions found
    """
    symbols = SymbolTable()

    for module in modules:
        # Add entities
        for entity in module.fragment.entities:
            symbols.add_entity(entity, module.name)

        # Add surfaces
        for surface in module.fragment.surfaces:
            symbols.add_surface(surface, module.name)

        # Add workspaces
        for workspace in module.fragment.workspaces:
            symbols.add_workspace(workspace, module.name)

        # Add experiences
        for experience in module.fragment.experiences:
            symbols.add_experience(experience, module.name)

        # Add external APIs
        for api in module.fragment.apis:
            symbols.add_api(api, module.name)

        # Add foreign models
        for foreign_model in module.fragment.foreign_models:
            symbols.add_foreign_model(foreign_model, module.name)

        # Add integrations
        for integration in module.fragment.integrations:
            symbols.add_integration(integration, module.name)

        # Add tests
        for test in module.fragment.tests:
            symbols.add_test(test, module.name)

        # Add personas (v0.8.5)
        for persona in module.fragment.personas:
            symbols.add_persona(persona, module.name)

        # Add scenarios (v0.8.5)
        for scenario in module.fragment.scenarios:
            symbols.add_scenario(scenario, module.name)

        # Add archetypes (v0.10.3)
        for archetype in module.fragment.archetypes:
            symbols.add_archetype(archetype, module.name)

    return symbols


def validate_module_access(modules: list[ir.ModuleIR], symbols: SymbolTable) -> list[str]:
    """
    Validate that modules only reference symbols from modules they've explicitly imported.

    Enforces that modules declare their dependencies via 'use' declarations,
    preventing accidental coupling between modules.

    Args:
        modules: List of all modules
        symbols: Symbol table with all definitions

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    for module in modules:
        # Build set of allowed modules (own module + used modules)
        allowed_modules = {module.name} | set(module.uses)

        # Check entity field references
        for entity in module.fragment.entities:
            for entity_field in entity.fields:
                if entity_field.type.kind == ir.FieldTypeKind.REF:
                    ref_entity = entity_field.type.ref_entity
                    if ref_entity is None:
                        continue
                    owner_module = symbols.symbol_sources.get(ref_entity)
                    if owner_module and owner_module not in allowed_modules:
                        errors.append(
                            f"Module '{module.name}' entity '{entity.name}' field '{entity_field.name}' "
                            f"references entity '{ref_entity}' from module '{owner_module}' "
                            f"without importing it (add: use {owner_module})"
                        )

        # Check surface entity references
        for surface in module.fragment.surfaces:
            if surface.entity_ref:
                owner_module = symbols.symbol_sources.get(surface.entity_ref)
                if owner_module and owner_module not in allowed_modules:
                    errors.append(
                        f"Module '{module.name}' surface '{surface.name}' "
                        f"references entity '{surface.entity_ref}' from module '{owner_module}' "
                        f"without importing it (add: use {owner_module})"
                    )

            # Check surface action outcomes
            for action in surface.actions:
                outcome = action.outcome
                target_module = None

                if outcome.kind == ir.OutcomeKind.SURFACE:
                    target_module = symbols.symbol_sources.get(outcome.target)
                elif outcome.kind == ir.OutcomeKind.EXPERIENCE:
                    target_module = symbols.symbol_sources.get(outcome.target)
                elif outcome.kind == ir.OutcomeKind.INTEGRATION:
                    target_module = symbols.symbol_sources.get(outcome.target)

                if target_module and target_module not in allowed_modules:
                    errors.append(
                        f"Module '{module.name}' surface '{surface.name}' action '{action.name}' "
                        f"references {outcome.kind.value} '{outcome.target}' from module '{target_module}' "
                        f"without importing it (add: use {target_module})"
                    )

        # Check experience step references
        for experience in module.fragment.experiences:
            for step in experience.steps:
                target_module = None

                if step.kind == ir.StepKind.SURFACE and step.surface:
                    target_module = symbols.symbol_sources.get(step.surface)
                elif step.kind == ir.StepKind.INTEGRATION and step.integration:
                    target_module = symbols.symbol_sources.get(step.integration)

                if target_module and target_module not in allowed_modules:
                    errors.append(
                        f"Module '{module.name}' experience '{experience.name}' step '{step.name}' "
                        f"references {step.kind.value} from module '{target_module}' "
                        f"without importing it (add: use {target_module})"
                    )

        # Check foreign model API references
        for foreign_model in module.fragment.foreign_models:
            owner_module = symbols.symbol_sources.get(foreign_model.api_ref)
            if owner_module and owner_module not in allowed_modules:
                errors.append(
                    f"Module '{module.name}' foreign model '{foreign_model.name}' "
                    f"references API '{foreign_model.api_ref}' from module '{owner_module}' "
                    f"without importing it (add: use {owner_module})"
                )

        # Check integration references
        for integration in module.fragment.integrations:
            for api_ref in integration.api_refs:
                owner_module = symbols.symbol_sources.get(api_ref)
                if owner_module and owner_module not in allowed_modules:
                    errors.append(
                        f"Module '{module.name}' integration '{integration.name}' "
                        f"references API '{api_ref}' from module '{owner_module}' "
                        f"without importing it (add: use {owner_module})"
                    )

            for fm_ref in integration.foreign_model_refs:
                owner_module = symbols.symbol_sources.get(fm_ref)
                if owner_module and owner_module not in allowed_modules:
                    errors.append(
                        f"Module '{module.name}' integration '{integration.name}' "
                        f"references foreign model '{fm_ref}' from module '{owner_module}' "
                        f"without importing it (add: use {owner_module})"
                    )

    return errors


def validate_references(symbols: SymbolTable) -> list[str]:
    """
    Validate all cross-references in the symbol table.

    Checks:
    - Entity field refs point to valid entities
    - Surface entity refs point to valid entities
    - Surface action outcomes point to valid targets
    - Experience step targets point to valid surfaces/integrations
    - API refs in foreign models and integrations are valid
    - Foreign model refs in integrations are valid

    Args:
        symbols: Complete symbol table

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Validate entity references in entity fields
    for entity_name, entity in symbols.entities.items():
        for entity_field in entity.fields:
            if entity_field.type.kind == ir.FieldTypeKind.REF:
                ref_entity = entity_field.type.ref_entity
                if ref_entity not in symbols.entities:
                    errors.append(
                        f"Entity '{entity_name}' field '{entity_field.name}' references "
                        f"unknown entity '{ref_entity}'"
                    )

        # Validate constraint field references
        for constraint in entity.constraints:
            for field_name in constraint.fields:
                if not entity.get_field(field_name):
                    errors.append(
                        f"Entity '{entity_name}' constraint references unknown field '{field_name}'"
                    )

        # v0.10.3: Validate archetype references in extends
        for archetype_name in entity.extends:
            if archetype_name not in symbols.archetypes:
                errors.append(
                    f"Entity '{entity_name}' extends unknown archetype '{archetype_name}'"
                )

    # Validate surface references
    for surface_name, surface in symbols.surfaces.items():
        # Check entity reference
        if surface.entity_ref and surface.entity_ref not in symbols.entities:
            errors.append(
                f"Surface '{surface_name}' references unknown entity '{surface.entity_ref}'"
            )

        # Check action outcomes
        for action in surface.actions:
            outcome = action.outcome
            if outcome.kind == ir.OutcomeKind.SURFACE:
                if outcome.target not in symbols.surfaces:
                    errors.append(
                        f"Surface '{surface_name}' action '{action.name}' references "
                        f"unknown surface '{outcome.target}'"
                    )
            elif outcome.kind == ir.OutcomeKind.EXPERIENCE:
                if outcome.target not in symbols.experiences:
                    errors.append(
                        f"Surface '{surface_name}' action '{action.name}' references "
                        f"unknown experience '{outcome.target}'"
                    )
            elif outcome.kind == ir.OutcomeKind.INTEGRATION:
                if outcome.target not in symbols.integrations:
                    errors.append(
                        f"Surface '{surface_name}' action '{action.name}' references "
                        f"unknown integration '{outcome.target}'"
                    )

    # Validate experience references
    for experience_name, experience in symbols.experiences.items():
        # Check if start step exists
        if not experience.get_step(experience.start_step):
            errors.append(
                f"Experience '{experience_name}' references unknown start step "
                f"'{experience.start_step}'"
            )

        # Check each step
        for step in experience.steps:
            # Validate step targets
            if step.kind == ir.StepKind.SURFACE:
                if step.surface and step.surface not in symbols.surfaces:
                    errors.append(
                        f"Experience '{experience_name}' step '{step.name}' references "
                        f"unknown surface '{step.surface}'"
                    )
            elif step.kind == ir.StepKind.INTEGRATION:
                if step.integration and step.integration not in symbols.integrations:
                    errors.append(
                        f"Experience '{experience_name}' step '{step.name}' references "
                        f"unknown integration '{step.integration}'"
                    )

            # Validate transitions
            for transition in step.transitions:
                if not experience.get_step(transition.next_step):
                    errors.append(
                        f"Experience '{experience_name}' step '{step.name}' transition "
                        f"references unknown step '{transition.next_step}'"
                    )

    # Validate foreign model API references
    for fm_name, foreign_model in symbols.foreign_models.items():
        if foreign_model.api_ref not in symbols.apis:
            errors.append(
                f"Foreign model '{fm_name}' references unknown API '{foreign_model.api_ref}'"
            )

    # Validate integration references
    for integration_name, integration in symbols.integrations.items():
        # Check API refs
        for api_ref in integration.api_refs:
            if api_ref not in symbols.apis:
                errors.append(
                    f"Integration '{integration_name}' references unknown API '{api_ref}'"
                )

        # Check foreign model refs
        for fm_ref in integration.foreign_model_refs:
            if fm_ref not in symbols.foreign_models:
                errors.append(
                    f"Integration '{integration_name}' references unknown foreign model '{fm_ref}'"
                )

    return errors


def merge_fragments(modules: list[ir.ModuleIR], symbols: SymbolTable) -> ir.ModuleFragment:
    """
    Merge all module fragments into a single fragment.

    Args:
        modules: List of modules
        symbols: Symbol table (ensures no duplicates)

    Returns:
        Unified ModuleFragment
    """
    return ir.ModuleFragment(
        entities=list(symbols.entities.values()),
        surfaces=list(symbols.surfaces.values()),
        workspaces=list(symbols.workspaces.values()),
        experiences=list(symbols.experiences.values()),
        apis=list(symbols.apis.values()),
        foreign_models=list(symbols.foreign_models.values()),
        integrations=list(symbols.integrations.values()),
        tests=list(symbols.tests.values()),
        personas=list(symbols.personas.values()),  # v0.8.5
        scenarios=list(symbols.scenarios.values()),  # v0.8.5
    )
