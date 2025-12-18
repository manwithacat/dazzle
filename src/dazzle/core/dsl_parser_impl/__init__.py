"""
DAZZLE DSL Parser Package.

This package provides a modular parser for the DAZZLE DSL.
The parser is built using mixins to separate parsing logic by construct type,
making it easier to maintain and extend.

The main exports are:
- Parser: The complete parser class
- parse_dsl: Convenience function to parse a DSL file

Usage:
    from dazzle.core.parser import parse_dsl

    module_name, app_name, app_title, uses, fragment = parse_dsl(text, file)
"""

from pathlib import Path

from .. import ir
from ..lexer import tokenize
from .base import BaseParser
from .conditions import ConditionParserMixin
from .entity import EntityParserMixin
from .eventing import EventingParserMixin
from .flow import FlowParserMixin
from .governance import GovernanceParserMixin
from .hless import HLESSParserMixin
from .integration import IntegrationParserMixin
from .llm import LLMParserMixin
from .messaging import MessagingParserMixin
from .process import ProcessParserMixin
from .scenario import ScenarioParserMixin
from .service import ServiceParserMixin
from .story import StoryParserMixin
from .surface import SurfaceParserMixin
from .test import TestParserMixin
from .types import TypeParserMixin
from .ux import UXParserMixin
from .workspace import WorkspaceParserMixin


class Parser(
    BaseParser,
    TypeParserMixin,
    ConditionParserMixin,
    EntityParserMixin,
    SurfaceParserMixin,
    ServiceParserMixin,
    IntegrationParserMixin,
    TestParserMixin,
    FlowParserMixin,
    UXParserMixin,
    WorkspaceParserMixin,
    ScenarioParserMixin,
    StoryParserMixin,
    MessagingParserMixin,
    EventingParserMixin,
    HLESSParserMixin,
    GovernanceParserMixin,
    LLMParserMixin,
    ProcessParserMixin,
):
    """
    Complete DAZZLE DSL Parser.

    This class composes all parser mixins to provide full DSL parsing capability.
    Each mixin provides parsing for a specific construct type:

    - TypeParserMixin: Field types and modifiers
    - ConditionParserMixin: Condition expressions for access rules and visibility
    - EntityParserMixin: Entity and archetype declarations
    - SurfaceParserMixin: Surface declarations with sections and actions
    - ServiceParserMixin: External APIs and domain services
    - IntegrationParserMixin: Integration declarations with actions and syncs
    - TestParserMixin: API contract tests
    - FlowParserMixin: E2E flow tests
    - UXParserMixin: UX semantic layer (attention signals, persona variants)
    - WorkspaceParserMixin: Workspace declarations with regions
    """

    def parse(self) -> ir.ModuleFragment:
        """
        Parse entire module and return IR fragment.

        Returns:
            ModuleFragment with all parsed declarations
        """
        from ..lexer import TokenType

        fragment = ir.ModuleFragment()

        self.skip_newlines()

        while not self.match(TokenType.EOF):
            self.skip_newlines()

            # v0.7.1: Check for archetype declaration
            if self.match(TokenType.ARCHETYPE):
                archetype = self.parse_archetype()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes + [archetype],
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.ENTITY):
                entity = self.parse_entity()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities + [entity],
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.SURFACE):
                surface = self.parse_surface()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces + [surface],
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.EXPERIENCE):
                experience = self.parse_experience()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences + [experience],
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.SERVICE):
                service = self.parse_service()
                # Route to apis or domain_services based on type
                if isinstance(service, ir.DomainServiceSpec):
                    fragment = ir.ModuleFragment(
                        archetypes=fragment.archetypes,
                        entities=fragment.entities,
                        surfaces=fragment.surfaces,
                        workspaces=fragment.workspaces,
                        experiences=fragment.experiences,
                        apis=fragment.apis,
                        domain_services=fragment.domain_services + [service],
                        foreign_models=fragment.foreign_models,
                        integrations=fragment.integrations,
                        tests=fragment.tests,
                        e2e_flows=fragment.e2e_flows,
                        fixtures=fragment.fixtures,
                        personas=fragment.personas,
                        scenarios=fragment.scenarios,
                        stories=fragment.stories,
                        processes=fragment.processes,
                        schedules=fragment.schedules,
                    )
                else:
                    fragment = ir.ModuleFragment(
                        archetypes=fragment.archetypes,
                        entities=fragment.entities,
                        surfaces=fragment.surfaces,
                        workspaces=fragment.workspaces,
                        experiences=fragment.experiences,
                        apis=fragment.apis + [service],
                        domain_services=fragment.domain_services,
                        foreign_models=fragment.foreign_models,
                        integrations=fragment.integrations,
                        tests=fragment.tests,
                        e2e_flows=fragment.e2e_flows,
                        fixtures=fragment.fixtures,
                        personas=fragment.personas,
                        scenarios=fragment.scenarios,
                        stories=fragment.stories,
                        processes=fragment.processes,
                        schedules=fragment.schedules,
                    )

            elif self.match(TokenType.FOREIGN_MODEL):
                foreign_model = self.parse_foreign_model()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models + [foreign_model],
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.INTEGRATION):
                integration = self.parse_integration()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations + [integration],
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.TEST):
                test = self.parse_test()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests + [test],
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.WORKSPACE):
                workspace = self.parse_workspace()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces + [workspace],
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.FLOW):
                flow = self.parse_flow()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows + [flow],
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.PERSONA):
                persona = self.parse_persona()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas + [persona],
                    scenarios=fragment.scenarios,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.SCENARIO):
                scenario = self.parse_scenario()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios + [scenario],
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            # v0.22.0 Stories DSL
            elif self.match(TokenType.STORY):
                self.advance()  # consume 'story' token
                story = self.parse_story()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    stories=fragment.stories + [story],
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            # v0.9.0 Messaging Channels
            elif self.match(TokenType.MESSAGE):
                message = self.parse_message()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages + [message],
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.CHANNEL):
                channel = self.parse_channel()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels + [channel],
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.ASSET):
                asset = self.parse_asset()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets + [asset],
                    documents=fragment.documents,
                    templates=fragment.templates,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.DOCUMENT):
                document = self.parse_document()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents + [document],
                    templates=fragment.templates,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.TEMPLATE):
                template = self.parse_template()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates + [template],
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.DEMO):
                demo_fixtures = self.parse_demo()
                # Demo fixtures go into the first scenario or create a default one
                if fragment.scenarios:
                    # Update the last scenario with new fixtures
                    last_scenario = fragment.scenarios[-1]
                    updated_scenario = ir.ScenarioSpec(
                        id=last_scenario.id,
                        name=last_scenario.name,
                        description=last_scenario.description,
                        persona_entries=last_scenario.persona_entries,
                        seed_data_path=last_scenario.seed_data_path,
                        demo_fixtures=list(last_scenario.demo_fixtures) + demo_fixtures,
                    )
                    fragment = ir.ModuleFragment(
                        archetypes=fragment.archetypes,
                        entities=fragment.entities,
                        surfaces=fragment.surfaces,
                        workspaces=fragment.workspaces,
                        experiences=fragment.experiences,
                        apis=fragment.apis,
                        domain_services=fragment.domain_services,
                        foreign_models=fragment.foreign_models,
                        integrations=fragment.integrations,
                        tests=fragment.tests,
                        e2e_flows=fragment.e2e_flows,
                        fixtures=fragment.fixtures,
                        personas=fragment.personas,
                        scenarios=fragment.scenarios[:-1] + [updated_scenario],
                        stories=fragment.stories,
                        processes=fragment.processes,
                        schedules=fragment.schedules,
                    )
                else:
                    # Create a default scenario for standalone demo blocks
                    default_scenario = ir.ScenarioSpec(
                        id="default",
                        name="Default",
                        description="Default demo scenario",
                        demo_fixtures=demo_fixtures,
                    )
                    fragment = ir.ModuleFragment(
                        archetypes=fragment.archetypes,
                        entities=fragment.entities,
                        surfaces=fragment.surfaces,
                        workspaces=fragment.workspaces,
                        experiences=fragment.experiences,
                        apis=fragment.apis,
                        domain_services=fragment.domain_services,
                        foreign_models=fragment.foreign_models,
                        integrations=fragment.integrations,
                        tests=fragment.tests,
                        e2e_flows=fragment.e2e_flows,
                        fixtures=fragment.fixtures,
                        personas=fragment.personas,
                        scenarios=[default_scenario],
                        stories=fragment.stories,
                        processes=fragment.processes,
                        schedules=fragment.schedules,
                    )

            # v0.18.0 Event-First Architecture
            elif self.match(TokenType.EVENT_MODEL):
                event_model = self.parse_event_model()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.SUBSCRIBE):
                subscription = self.parse_subscribe()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions + [subscription],
                    projections=fragment.projections,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.PROJECT):
                projection = self.parse_projection()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections + [projection],
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            # v0.19.0 HLESS - High-Level Event Semantics
            elif self.match(TokenType.STREAM):
                stream = self.parse_stream()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams + [stream],
                    hless_pragma=fragment.hless_pragma,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.HLESS):
                hless_pragma = self.parse_hless_pragma()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=hless_pragma,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            # v0.18.0 Governance sections (Issue #25)
            elif self.match(TokenType.POLICIES):
                policies = self.parse_policies()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.TENANCY):
                tenancy = self.parse_tenancy()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.INTERFACES):
                interfaces = self.parse_interfaces()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=interfaces,
                    data_products=fragment.data_products,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.DATA_PRODUCTS):
                data_products = self.parse_data_products()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=data_products,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            # LLM Jobs as First-Class Events (v0.21.0 - Issue #33)
            elif self.match(TokenType.LLM_MODEL):
                llm_model = self.parse_llm_model()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    llm_config=fragment.llm_config,
                    llm_models=[*fragment.llm_models, llm_model],
                    llm_intents=fragment.llm_intents,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.LLM_CONFIG):
                llm_config = self.parse_llm_config()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    llm_config=llm_config,
                    llm_models=fragment.llm_models,
                    llm_intents=fragment.llm_intents,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.LLM_INTENT):
                llm_intent = self.parse_llm_intent()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    llm_config=fragment.llm_config,
                    llm_models=fragment.llm_models,
                    llm_intents=[*fragment.llm_intents, llm_intent],
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=fragment.schedules,
                )

            # v0.23.0 Process Workflows
            elif self.match(TokenType.PROCESS):
                process = self.parse_process()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    llm_config=fragment.llm_config,
                    llm_models=fragment.llm_models,
                    llm_intents=fragment.llm_intents,
                    stories=fragment.stories,
                    processes=[*fragment.processes, process],
                    schedules=fragment.schedules,
                )

            elif self.match(TokenType.SCHEDULE):
                schedule = self.parse_schedule()
                fragment = ir.ModuleFragment(
                    archetypes=fragment.archetypes,
                    entities=fragment.entities,
                    surfaces=fragment.surfaces,
                    workspaces=fragment.workspaces,
                    experiences=fragment.experiences,
                    apis=fragment.apis,
                    domain_services=fragment.domain_services,
                    foreign_models=fragment.foreign_models,
                    integrations=fragment.integrations,
                    tests=fragment.tests,
                    e2e_flows=fragment.e2e_flows,
                    fixtures=fragment.fixtures,
                    personas=fragment.personas,
                    scenarios=fragment.scenarios,
                    messages=fragment.messages,
                    channels=fragment.channels,
                    assets=fragment.assets,
                    documents=fragment.documents,
                    templates=fragment.templates,
                    event_model=fragment.event_model,
                    subscriptions=fragment.subscriptions,
                    projections=fragment.projections,
                    streams=fragment.streams,
                    hless_pragma=fragment.hless_pragma,
                    policies=fragment.policies,
                    tenancy=fragment.tenancy,
                    interfaces=fragment.interfaces,
                    data_products=fragment.data_products,
                    llm_config=fragment.llm_config,
                    llm_models=fragment.llm_models,
                    llm_intents=fragment.llm_intents,
                    stories=fragment.stories,
                    processes=fragment.processes,
                    schedules=[*fragment.schedules, schedule],
                )

            else:
                token = self.current_token()
                if token.type == TokenType.EOF:
                    break
                # Skip unknown tokens
                self.advance()

        return fragment


def parse_dsl(
    text: str, file: Path
) -> tuple[
    str | None, str | None, str | None, ir.AppConfigSpec | None, list[str], ir.ModuleFragment
]:
    """
    Parse complete DSL file.

    Args:
        text: DSL source text
        file: Source file path

    Returns:
        Tuple of (module_name, app_name, app_title, app_config, uses, fragment)
    """
    # Tokenize
    tokens = tokenize(text, file)

    # Parse
    parser = Parser(tokens, file)
    module_name, app_name, app_title, app_config, uses = parser.parse_module_header()
    fragment = parser.parse()

    return module_name, app_name, app_title, app_config, uses, fragment


__all__ = [
    "Parser",
    "parse_dsl",
    "BaseParser",
    "TypeParserMixin",
    "ConditionParserMixin",
    "EntityParserMixin",
    "SurfaceParserMixin",
    "ServiceParserMixin",
    "IntegrationParserMixin",
    "TestParserMixin",
    "FlowParserMixin",
    "UXParserMixin",
    "WorkspaceParserMixin",
    "ScenarioParserMixin",
    "StoryParserMixin",
    "MessagingParserMixin",
    "EventingParserMixin",
    "HLESSParserMixin",
    "ProcessParserMixin",
]
