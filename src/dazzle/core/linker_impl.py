"""
Module linker implementation for DAZZLE.

Handles dependency resolution, symbol table building, and reference validation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import ir
from .errors import LinkError


def _add_symbol(
    registry: dict[str, Any],
    key: str,
    value: Any,
    kind: str,
    module_name: str,
    symbol_sources: dict[str, str],
) -> None:
    """Add a symbol to a registry, raising LinkError on duplicates."""
    if key in registry:
        existing_module = symbol_sources.get(key, "unknown")
        raise LinkError(
            f"Duplicate {kind} '{key}' defined in modules '{existing_module}' and '{module_name}'"
        )
    registry[key] = value
    symbol_sources[key] = module_name


@dataclass
class DomainSymbols:
    """Domain-layer symbols: entities, enums, views, ledgers, foreign models."""

    entities: dict[str, ir.EntitySpec] = field(default_factory=dict)
    enums: dict[str, ir.EnumSpec] = field(default_factory=dict)
    views: dict[str, ir.ViewSpec] = field(default_factory=dict)
    ledgers: dict[str, ir.LedgerSpec] = field(default_factory=dict)
    foreign_models: dict[str, ir.ForeignModelSpec] = field(default_factory=dict)

    def add_entity(self, entity: ir.EntitySpec, module_name: str, sources: dict[str, str]) -> None:
        _add_symbol(self.entities, entity.name, entity, "entity", module_name, sources)

    def add_enum(self, enum: ir.EnumSpec, module_name: str, sources: dict[str, str]) -> None:
        _add_symbol(self.enums, enum.name, enum, "enum", module_name, sources)

    def add_view(self, view: ir.ViewSpec, module_name: str, sources: dict[str, str]) -> None:
        _add_symbol(self.views, view.name, view, "view", module_name, sources)

    def add_ledger(self, ledger: ir.LedgerSpec, module_name: str, sources: dict[str, str]) -> None:
        _add_symbol(self.ledgers, ledger.name, ledger, "ledger", module_name, sources)

    def add_foreign_model(
        self, foreign_model: ir.ForeignModelSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(
            self.foreign_models,
            foreign_model.name,
            foreign_model,
            "foreign model",
            module_name,
            sources,
        )


@dataclass
class UISymbols:
    """UI-layer symbols: surfaces, workspaces, experiences."""

    surfaces: dict[str, ir.SurfaceSpec] = field(default_factory=dict)
    workspaces: dict[str, ir.WorkspaceSpec] = field(default_factory=dict)
    experiences: dict[str, ir.ExperienceSpec] = field(default_factory=dict)

    def add_surface(
        self, surface: ir.SurfaceSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(self.surfaces, surface.name, surface, "surface", module_name, sources)

    def add_workspace(
        self, workspace: ir.WorkspaceSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(self.workspaces, workspace.name, workspace, "workspace", module_name, sources)

    def add_experience(
        self, experience: ir.ExperienceSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(
            self.experiences, experience.name, experience, "experience", module_name, sources
        )


@dataclass
class ProcessSymbols:
    """Process-layer symbols: processes, stories, personas, scenarios."""

    processes: dict[str, ir.ProcessSpec] = field(default_factory=dict)
    stories: dict[str, ir.StorySpec] = field(default_factory=dict)
    personas: dict[str, ir.PersonaSpec] = field(default_factory=dict)
    scenarios: dict[str, ir.ScenarioSpec] = field(default_factory=dict)

    def add_process(
        self, process: ir.ProcessSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(self.processes, process.name, process, "process", module_name, sources)

    def add_story(self, story: ir.StorySpec, module_name: str, sources: dict[str, str]) -> None:
        _add_symbol(self.stories, story.story_id, story, "story", module_name, sources)

    def add_persona(
        self, persona: ir.PersonaSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(self.personas, persona.id, persona, "persona", module_name, sources)

    def add_scenario(
        self, scenario: ir.ScenarioSpec, module_name: str, sources: dict[str, str]
    ) -> None:
        _add_symbol(self.scenarios, scenario.id, scenario, "scenario", module_name, sources)


@dataclass
class SymbolTable:
    """
    Symbol table for tracking all named definitions across modules.

    Delegates to DomainSymbols, UISymbols, and ProcessSymbols for grouped
    symbol types. Remaining symbol types are managed directly.
    """

    # Delegate groups
    _domain: DomainSymbols = field(default_factory=DomainSymbols)
    _ui: UISymbols = field(default_factory=UISymbols)
    _process: ProcessSymbols = field(default_factory=ProcessSymbols)

    # Remaining symbols managed directly
    apis: dict[str, ir.APISpec] = field(default_factory=dict)
    integrations: dict[str, ir.IntegrationSpec] = field(default_factory=dict)
    tests: dict[str, ir.TestSpec] = field(default_factory=dict)
    archetypes: dict[str, ir.ArchetypeSpec] = field(default_factory=dict)  # v0.10.3
    llm_models: dict[str, ir.LLMModelSpec] = field(default_factory=dict)  # v0.21.0
    llm_intents: dict[str, ir.LLMIntentSpec] = field(default_factory=dict)  # v0.21.0
    schedules: dict[str, ir.ScheduleSpec] = field(default_factory=dict)  # v0.23.0
    transactions: dict[str, ir.TransactionSpec] = field(default_factory=dict)  # v0.24.0
    webhooks: dict[str, ir.WebhookSpec] = field(default_factory=dict)  # v0.25.0
    approvals: dict[str, ir.ApprovalSpec] = field(default_factory=dict)  # v0.25.0
    slas: dict[str, ir.SLASpec] = field(default_factory=dict)  # v0.25.0

    # Track which module each symbol came from (for error reporting)
    symbol_sources: dict[str, str] = field(default_factory=dict)

    # Track LLM config (only one per app, from root module)
    llm_config: ir.LLMConfigSpec | None = None  # v0.21.0

    # --- Delegated properties for backward compatibility ---

    @property
    def entities(self) -> dict[str, ir.EntitySpec]:
        return self._domain.entities

    @property
    def enums(self) -> dict[str, ir.EnumSpec]:
        return self._domain.enums

    @property
    def views(self) -> dict[str, ir.ViewSpec]:
        return self._domain.views

    @property
    def ledgers(self) -> dict[str, ir.LedgerSpec]:
        return self._domain.ledgers

    @property
    def foreign_models(self) -> dict[str, ir.ForeignModelSpec]:
        return self._domain.foreign_models

    @property
    def surfaces(self) -> dict[str, ir.SurfaceSpec]:
        return self._ui.surfaces

    @property
    def workspaces(self) -> dict[str, ir.WorkspaceSpec]:
        return self._ui.workspaces

    @property
    def experiences(self) -> dict[str, ir.ExperienceSpec]:
        return self._ui.experiences

    @property
    def processes(self) -> dict[str, ir.ProcessSpec]:
        return self._process.processes

    @property
    def stories(self) -> dict[str, ir.StorySpec]:
        return self._process.stories

    @property
    def personas(self) -> dict[str, ir.PersonaSpec]:
        return self._process.personas

    @property
    def scenarios(self) -> dict[str, ir.ScenarioSpec]:
        return self._process.scenarios

    # --- Delegated add methods ---

    def add_entity(self, entity: ir.EntitySpec, module_name: str) -> None:
        """Add entity to symbol table, checking for duplicates."""
        self._domain.add_entity(entity, module_name, self.symbol_sources)

    def add_surface(self, surface: ir.SurfaceSpec, module_name: str) -> None:
        """Add surface to symbol table, checking for duplicates."""
        self._ui.add_surface(surface, module_name, self.symbol_sources)

    def add_workspace(self, workspace: ir.WorkspaceSpec, module_name: str) -> None:
        """Add workspace to symbol table, checking for duplicates."""
        self._ui.add_workspace(workspace, module_name, self.symbol_sources)

    def add_experience(self, experience: ir.ExperienceSpec, module_name: str) -> None:
        """Add experience to symbol table, checking for duplicates."""
        self._ui.add_experience(experience, module_name, self.symbol_sources)

    def add_api(self, api: ir.APISpec, module_name: str) -> None:
        """Add external API to symbol table, checking for duplicates."""
        _add_symbol(self.apis, api.name, api, "API", module_name, self.symbol_sources)

    def add_foreign_model(self, foreign_model: ir.ForeignModelSpec, module_name: str) -> None:
        """Add foreign model to symbol table, checking for duplicates."""
        self._domain.add_foreign_model(foreign_model, module_name, self.symbol_sources)

    def add_integration(self, integration: ir.IntegrationSpec, module_name: str) -> None:
        """Add integration to symbol table, checking for duplicates."""
        _add_symbol(
            self.integrations,
            integration.name,
            integration,
            "integration",
            module_name,
            self.symbol_sources,
        )

    def add_test(self, test: ir.TestSpec, module_name: str) -> None:
        """Add test to symbol table, checking for duplicates."""
        _add_symbol(self.tests, test.name, test, "test", module_name, self.symbol_sources)

    def add_persona(self, persona: ir.PersonaSpec, module_name: str) -> None:
        """Add persona to symbol table, checking for duplicates (v0.8.5)."""
        self._process.add_persona(persona, module_name, self.symbol_sources)

    def add_scenario(self, scenario: ir.ScenarioSpec, module_name: str) -> None:
        """Add scenario to symbol table, checking for duplicates (v0.8.5)."""
        self._process.add_scenario(scenario, module_name, self.symbol_sources)

    def add_archetype(self, archetype: ir.ArchetypeSpec, module_name: str) -> None:
        """Add archetype to symbol table, checking for duplicates (v0.10.3)."""
        _add_symbol(
            self.archetypes,
            archetype.name,
            archetype,
            "archetype",
            module_name,
            self.symbol_sources,
        )

    def add_story(self, story: ir.StorySpec, module_name: str) -> None:
        """Add story to symbol table, checking for duplicates (v0.22.0)."""
        self._process.add_story(story, module_name, self.symbol_sources)

    def add_llm_model(self, llm_model: ir.LLMModelSpec, module_name: str) -> None:
        """Add LLM model to symbol table, checking for duplicates (v0.21.0)."""
        _add_symbol(
            self.llm_models,
            llm_model.name,
            llm_model,
            "llm_model",
            module_name,
            self.symbol_sources,
        )

    def add_llm_intent(self, llm_intent: ir.LLMIntentSpec, module_name: str) -> None:
        """Add LLM intent to symbol table, checking for duplicates (v0.21.0)."""
        _add_symbol(
            self.llm_intents,
            llm_intent.name,
            llm_intent,
            "llm_intent",
            module_name,
            self.symbol_sources,
        )

    def set_llm_config(self, config: ir.LLMConfigSpec, module_name: str) -> None:
        """Set LLM config (v0.21.0). Only one config per app allowed."""
        if self.llm_config is not None:
            raise LinkError(
                f"Duplicate llm_config defined in module '{module_name}'. "
                "Only one llm_config block is allowed per app."
            )
        self.llm_config = config

    def add_process(self, process: ir.ProcessSpec, module_name: str) -> None:
        """Add process to symbol table, checking for duplicates (v0.23.0)."""
        self._process.add_process(process, module_name, self.symbol_sources)

    def add_schedule(self, schedule: ir.ScheduleSpec, module_name: str) -> None:
        """Add schedule to symbol table, checking for duplicates (v0.23.0)."""
        _add_symbol(
            self.schedules, schedule.name, schedule, "schedule", module_name, self.symbol_sources
        )

    def add_ledger(self, ledger: ir.LedgerSpec, module_name: str) -> None:
        """Add ledger to symbol table, checking for duplicates (v0.24.0)."""
        self._domain.add_ledger(ledger, module_name, self.symbol_sources)

    def add_transaction(self, transaction: ir.TransactionSpec, module_name: str) -> None:
        """Add transaction to symbol table, checking for duplicates (v0.24.0)."""
        _add_symbol(
            self.transactions,
            transaction.name,
            transaction,
            "transaction",
            module_name,
            self.symbol_sources,
        )

    def add_enum(self, enum: ir.EnumSpec, module_name: str) -> None:
        """Add shared enum to symbol table, checking for duplicates (v0.25.0)."""
        self._domain.add_enum(enum, module_name, self.symbol_sources)

    def add_view(self, view: ir.ViewSpec, module_name: str) -> None:
        """Add view to symbol table, checking for duplicates (v0.25.0)."""
        self._domain.add_view(view, module_name, self.symbol_sources)

    def add_webhook(self, webhook: ir.WebhookSpec, module_name: str) -> None:
        """Add webhook to symbol table, checking for duplicates (v0.25.0)."""
        _add_symbol(
            self.webhooks, webhook.name, webhook, "webhook", module_name, self.symbol_sources
        )

    def add_approval(self, approval: ir.ApprovalSpec, module_name: str) -> None:
        """Add approval to symbol table, checking for duplicates (v0.25.0)."""
        _add_symbol(
            self.approvals, approval.name, approval, "approval", module_name, self.symbol_sources
        )

    def add_sla(self, sla: ir.SLASpec, module_name: str) -> None:
        """Add SLA to symbol table, checking for duplicates (v0.25.0)."""
        _add_symbol(self.slas, sla.name, sla, "SLA", module_name, self.symbol_sources)


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

        # Add stories (v0.22.0)
        for story in module.fragment.stories:
            symbols.add_story(story, module.name)

        # Add LLM models (v0.21.0)
        for llm_model in module.fragment.llm_models:
            symbols.add_llm_model(llm_model, module.name)

        # Add LLM intents (v0.21.0)
        for llm_intent in module.fragment.llm_intents:
            symbols.add_llm_intent(llm_intent, module.name)

        # Set LLM config if present (v0.21.0)
        if module.fragment.llm_config is not None:
            symbols.set_llm_config(module.fragment.llm_config, module.name)

        # Add processes (v0.23.0)
        for process in module.fragment.processes:
            symbols.add_process(process, module.name)

        # Add schedules (v0.23.0)
        for schedule in module.fragment.schedules:
            symbols.add_schedule(schedule, module.name)

        # Add ledgers (v0.24.0)
        for ledger in module.fragment.ledgers:
            symbols.add_ledger(ledger, module.name)

        # Add transactions (v0.24.0)
        for transaction in module.fragment.transactions:
            symbols.add_transaction(transaction, module.name)

        # Add enums (v0.25.0)
        for enum in module.fragment.enums:
            symbols.add_enum(enum, module.name)

        # Add views (v0.25.0)
        for view in module.fragment.views:
            symbols.add_view(view, module.name)

        # Add webhooks (v0.25.0)
        for webhook in module.fragment.webhooks:
            symbols.add_webhook(webhook, module.name)

        # Add approvals (v0.25.0)
        for approval in module.fragment.approvals:
            symbols.add_approval(approval, module.name)

        # Add SLAs (v0.25.0)
        for sla in module.fragment.slas:
            symbols.add_sla(sla, module.name)

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
                            f"Module '{module.name}' entity "
                            f"'{entity.name}' field "
                            f"'{entity_field.name}' references "
                            f"entity '{ref_entity}' from module "
                            f"'{owner_module}' without importing "
                            f"it (add: use {owner_module})"
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
                        f"Module '{module.name}' surface '{surface.name}' action "
                        f"'{action.name}' references {outcome.kind.value} '{outcome.target}' "
                        f"from module '{target_module}' without importing it "
                        f"(add: use {target_module})"
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


def check_unused_imports(modules: list[ir.ModuleIR], symbols: SymbolTable) -> list[str]:
    """
    Check for modules that are imported but never used.

    v0.14.1: Added based on user feedback - helps catch unnecessary coupling.

    Args:
        modules: List of all modules
        symbols: Symbol table with all definitions

    Returns:
        List of warning messages for unused imports
    """
    warnings = []

    for module in modules:
        if not module.uses:
            continue

        # Track which imports are actually used
        used_modules: set[str] = set()

        # Check entity field references
        for entity in module.fragment.entities:
            for entity_field in entity.fields:
                if entity_field.type.kind == ir.FieldTypeKind.REF:
                    ref_entity = entity_field.type.ref_entity
                    if ref_entity:
                        owner = symbols.symbol_sources.get(ref_entity)
                        if owner and owner != module.name:
                            used_modules.add(owner)

        # Check surface entity references
        for surface in module.fragment.surfaces:
            if surface.entity_ref:
                owner = symbols.symbol_sources.get(surface.entity_ref)
                if owner and owner != module.name:
                    used_modules.add(owner)

            # Check surface action outcomes
            for action in surface.actions:
                outcome = action.outcome
                if outcome.target:
                    owner = symbols.symbol_sources.get(outcome.target)
                    if owner and owner != module.name:
                        used_modules.add(owner)

        # Check experience step references
        for experience in module.fragment.experiences:
            for step in experience.steps:
                if step.surface:
                    owner = symbols.symbol_sources.get(step.surface)
                    if owner and owner != module.name:
                        used_modules.add(owner)
                if step.integration:
                    owner = symbols.symbol_sources.get(step.integration)
                    if owner and owner != module.name:
                        used_modules.add(owner)

        # Check foreign model API references
        for foreign_model in module.fragment.foreign_models:
            if foreign_model.api_ref:
                owner = symbols.symbol_sources.get(foreign_model.api_ref)
                if owner and owner != module.name:
                    used_modules.add(owner)

        # Check integration references
        for integration in module.fragment.integrations:
            for api_ref in integration.api_refs:
                owner = symbols.symbol_sources.get(api_ref)
                if owner and owner != module.name:
                    used_modules.add(owner)
            for fm_ref in integration.foreign_model_refs:
                owner = symbols.symbol_sources.get(fm_ref)
                if owner and owner != module.name:
                    used_modules.add(owner)

        # Find unused imports
        unused = set(module.uses) - used_modules
        for unused_import in sorted(unused):
            warnings.append(
                f"Module '{module.name}' imports '{unused_import}' but never uses it. "
                f"Consider removing: use {unused_import}"
            )

    return warnings


def detect_entity_cycles(symbols: SymbolTable) -> list[str]:
    """
    Detect circular reference chains between entities.

    v0.14.1: Added based on user feedback - catches Entity A -> B -> C -> A cycles
    early during linking instead of at database migration time.

    Args:
        symbols: Complete symbol table

    Returns:
        List of warning messages for circular refs (empty if none)
    """
    warnings = []

    # Build adjacency list of entity refs
    ref_graph: dict[str, set[str]] = {name: set() for name in symbols.entities}

    for entity_name, entity in symbols.entities.items():
        for fld in entity.fields:
            if fld.type.kind == ir.FieldTypeKind.REF and fld.type.ref_entity:
                ref_entity = fld.type.ref_entity
                # Skip optional refs (they can break cycles) and self-refs (valid for trees)
                is_optional = ir.FieldModifier.OPTIONAL in fld.modifiers
                if is_optional or ref_entity == entity_name:
                    continue
                if ref_entity in symbols.entities:
                    ref_graph[entity_name].add(ref_entity)

    # DFS to detect cycles
    def find_cycle(start: str) -> list[str] | None:
        """Find cycle starting from given entity. Returns cycle path or None."""
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> list[str] | None:
            if node in path:
                # Found cycle - return the cycle portion
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            if node in visited:
                return None
            visited.add(node)
            path.append(node)
            for neighbor in ref_graph.get(node, set()):
                result = dfs(neighbor)
                if result:
                    return result
            path.pop()
            return None

        return dfs(start)

    # Check each entity for cycles
    reported_cycles: set[tuple[str, ...]] = set()
    for entity_name in symbols.entities:
        cycle = find_cycle(entity_name)
        if cycle:
            # Normalize cycle to avoid duplicates (sort by first element)
            # e.g., [A, B, C, A] and [B, C, A, B] are the same cycle
            min_idx = cycle[:-1].index(min(cycle[:-1]))
            normalized = tuple(cycle[min_idx:-1]) + (cycle[min_idx],)
            if normalized not in reported_cycles:
                reported_cycles.add(normalized)
                cycle_str = " -> ".join(cycle)
                warnings.append(
                    f"Circular entity reference detected: {cycle_str}\n"
                    f"  This may cause issues with database migrations and data loading.\n"
                    f"  Consider breaking the cycle with optional refs or a junction entity."
                )

    return warnings


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
    - v0.14.1: Entity circular reference cycles

    Args:
        symbols: Complete symbol table

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # v0.14.1: Detect entity reference cycles early
    cycle_warnings = detect_entity_cycles(symbols)
    errors.extend(cycle_warnings)

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

        # Check view reference (for list field projection)
        if surface.view_ref:
            if surface.view_ref not in symbols.views:
                errors.append(
                    f"Surface '{surface_name}' references unknown view '{surface.view_ref}'"
                )
            else:
                view = symbols.views[surface.view_ref]
                if (
                    surface.entity_ref
                    and view.source_entity
                    and view.source_entity != surface.entity_ref
                ):
                    errors.append(
                        f"Surface '{surface_name}' references view '{surface.view_ref}' "
                        f"whose source entity '{view.source_entity}' does not match "
                        f"surface entity '{surface.entity_ref}'"
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

            # Validate step access persona references
            if step.access and step.access.allow_personas and symbols.personas:
                for persona_name in step.access.allow_personas:
                    if persona_name not in symbols.personas:
                        errors.append(
                            f"Experience '{experience_name}' step '{step.name}' access "
                            f"references unknown persona '{persona_name}'"
                        )

        # Validate experience-level access persona references
        if experience.access and experience.access.allow_personas and symbols.personas:
            for persona_name in experience.access.allow_personas:
                if persona_name not in symbols.personas:
                    errors.append(
                        f"Experience '{experience_name}' access references "
                        f"unknown persona '{persona_name}'"
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

    # v0.22.0: Validate story references
    for story_id, story in symbols.stories.items():
        # Check actor reference (should be a valid persona id or label)
        # Note: actor can be a persona id or label - we validate against personas
        if story.actor and symbols.personas:
            # Only validate if personas are defined
            if story.actor not in symbols.personas:
                # Check if it could be a label in any persona
                found_label = False
                for persona in symbols.personas.values():
                    if story.actor == persona.label:
                        found_label = True
                        break
                if not found_label:
                    errors.append(
                        f"Story '{story_id}' actor '{story.actor}' is not a defined persona "
                        f"id or label. Available personas: {list(symbols.personas.keys())}"
                    )

        # Check scope references (should be valid entities)
        for entity_name in story.scope:
            if entity_name not in symbols.entities:
                errors.append(f"Story '{story_id}' scope references unknown entity '{entity_name}'")

    # v0.21.0: Validate LLM intent references
    for intent_name, llm_intent in symbols.llm_intents.items():
        # Check model reference
        if llm_intent.model_ref and llm_intent.model_ref not in symbols.llm_models:
            errors.append(
                f"llm_intent '{intent_name}' references unknown llm_model '{llm_intent.model_ref}'"
            )

        # Check output_schema reference (should be a valid entity)
        if llm_intent.output_schema and llm_intent.output_schema not in symbols.entities:
            errors.append(
                f"llm_intent '{intent_name}' output_schema references "
                f"unknown entity '{llm_intent.output_schema}'"
            )

    # v0.21.0: Validate LLM config references
    if symbols.llm_config:
        config = symbols.llm_config
        # Check default_model reference
        if config.default_model and config.default_model not in symbols.llm_models:
            errors.append(
                f"llm_config default_model references unknown llm_model '{config.default_model}'"
            )

        # Check rate_limits model references
        if config.rate_limits:
            for model_name in config.rate_limits:
                if model_name not in symbols.llm_models:
                    errors.append(
                        f"llm_config rate_limits references unknown llm_model '{model_name}'"
                    )

    # v0.21.0: Validate that intents have a model (either explicit or default)
    if symbols.llm_intents and not symbols.llm_models:
        errors.append(
            "llm_intent(s) defined but no llm_model(s) are available. "
            "Define at least one llm_model for intents to use."
        )
    elif symbols.llm_intents:
        default_model = symbols.llm_config.default_model if symbols.llm_config else None
        for intent_name, llm_intent in symbols.llm_intents.items():
            if not llm_intent.model_ref and not default_model:
                errors.append(
                    f"llm_intent '{intent_name}' has no model reference and no default_model "
                    "is set in llm_config. Either specify model: in the intent or set "
                    "default_model: in llm_config."
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
        stories=list(symbols.stories.values()),  # v0.22.0
        llm_config=symbols.llm_config,  # v0.21.0
        llm_models=list(symbols.llm_models.values()),  # v0.21.0
        llm_intents=list(symbols.llm_intents.values()),  # v0.21.0
        processes=list(symbols.processes.values()),  # v0.23.0
        schedules=list(symbols.schedules.values()),  # v0.23.0
        ledgers=list(symbols.ledgers.values()),  # v0.24.0
        transactions=list(symbols.transactions.values()),  # v0.24.0
        enums=list(symbols.enums.values()),  # v0.25.0
        views=list(symbols.views.values()),  # v0.25.0
        webhooks=list(symbols.webhooks.values()),  # v0.25.0
        approvals=list(symbols.approvals.values()),  # v0.25.0
        slas=list(symbols.slas.values()),  # v0.25.0
    )
