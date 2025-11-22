"""
Module linker implementation for DAZZLE.

Handles dependency resolution, symbol table building, and reference validation.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional

from . import ir
from .errors import LinkError, make_link_error


@dataclass
class SymbolTable:
    """
    Symbol table for tracking all named definitions across modules.

    Tracks entities, surfaces, experiences, services, foreign models, integrations, and tests
    to enable cross-module reference resolution.
    """
    entities: Dict[str, ir.EntitySpec] = field(default_factory=dict)
    surfaces: Dict[str, ir.SurfaceSpec] = field(default_factory=dict)
    experiences: Dict[str, ir.ExperienceSpec] = field(default_factory=dict)
    services: Dict[str, ir.ServiceSpec] = field(default_factory=dict)
    foreign_models: Dict[str, ir.ForeignModelSpec] = field(default_factory=dict)
    integrations: Dict[str, ir.IntegrationSpec] = field(default_factory=dict)
    tests: Dict[str, ir.TestSpec] = field(default_factory=dict)

    # Track which module each symbol came from (for error reporting)
    symbol_sources: Dict[str, str] = field(default_factory=dict)

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

    def add_service(self, service: ir.ServiceSpec, module_name: str) -> None:
        """Add service to symbol table, checking for duplicates."""
        if service.name in self.services:
            existing_module = self.symbol_sources.get(service.name, "unknown")
            raise LinkError(
                f"Duplicate service '{service.name}' defined in modules "
                f"'{existing_module}' and '{module_name}'"
            )
        self.services[service.name] = service
        self.symbol_sources[service.name] = module_name

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


def resolve_dependencies(modules: List[ir.ModuleIR]) -> List[ir.ModuleIR]:
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
    # Build dependency graph
    module_map = {m.name: m for m in modules}
    dependencies: Dict[str, Set[str]] = {m.name: set(m.uses) for m in modules}

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
        raise LinkError(
            f"Circular dependency detected involving modules: {unprocessed}"
        )

    return sorted_modules


def build_symbol_table(modules: List[ir.ModuleIR]) -> SymbolTable:
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

        # Add experiences
        for experience in module.fragment.experiences:
            symbols.add_experience(experience, module.name)

        # Add services
        for service in module.fragment.services:
            symbols.add_service(service, module.name)

        # Add foreign models
        for foreign_model in module.fragment.foreign_models:
            symbols.add_foreign_model(foreign_model, module.name)

        # Add integrations
        for integration in module.fragment.integrations:
            symbols.add_integration(integration, module.name)

        # Add tests
        for test in module.fragment.tests:
            symbols.add_test(test, module.name)

    return symbols


def validate_references(symbols: SymbolTable) -> List[str]:
    """
    Validate all cross-references in the symbol table.

    Checks:
    - Entity field refs point to valid entities
    - Surface entity refs point to valid entities
    - Surface action outcomes point to valid targets
    - Experience step targets point to valid surfaces/integrations
    - Service refs in foreign models and integrations are valid
    - Foreign model refs in integrations are valid

    Args:
        symbols: Complete symbol table

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Validate entity references in entity fields
    for entity_name, entity in symbols.entities.items():
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF:
                ref_entity = field.type.ref_entity
                if ref_entity not in symbols.entities:
                    errors.append(
                        f"Entity '{entity_name}' field '{field.name}' references "
                        f"unknown entity '{ref_entity}'"
                    )

        # Validate constraint field references
        for constraint in entity.constraints:
            for field_name in constraint.fields:
                if not entity.get_field(field_name):
                    errors.append(
                        f"Entity '{entity_name}' constraint references "
                        f"unknown field '{field_name}'"
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

    # Validate foreign model service references
    for fm_name, foreign_model in symbols.foreign_models.items():
        if foreign_model.service_ref not in symbols.services:
            errors.append(
                f"Foreign model '{fm_name}' references unknown service "
                f"'{foreign_model.service_ref}'"
            )

    # Validate integration references
    for integration_name, integration in symbols.integrations.items():
        # Check service refs
        for service_ref in integration.service_refs:
            if service_ref not in symbols.services:
                errors.append(
                    f"Integration '{integration_name}' references unknown service "
                    f"'{service_ref}'"
                )

        # Check foreign model refs
        for fm_ref in integration.foreign_model_refs:
            if fm_ref not in symbols.foreign_models:
                errors.append(
                    f"Integration '{integration_name}' references unknown foreign model "
                    f"'{fm_ref}'"
                )

    return errors


def merge_fragments(modules: List[ir.ModuleIR], symbols: SymbolTable) -> ir.ModuleFragment:
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
        experiences=list(symbols.experiences.values()),
        services=list(symbols.services.values()),
        foreign_models=list(symbols.foreign_models.values()),
        integrations=list(symbols.integrations.values()),
        tests=list(symbols.tests.values()),
    )
