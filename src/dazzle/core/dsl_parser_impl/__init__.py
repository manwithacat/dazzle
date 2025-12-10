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
from .flow import FlowParserMixin
from .integration import IntegrationParserMixin
from .service import ServiceParserMixin
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
) -> tuple[str | None, str | None, str | None, list[str], ir.ModuleFragment]:
    """
    Parse complete DSL file.

    Args:
        text: DSL source text
        file: Source file path

    Returns:
        Tuple of (module_name, app_name, app_title, uses, fragment)
    """
    # Tokenize
    tokens = tokenize(text, file)

    # Parse
    parser = Parser(tokens, file)
    module_name, app_name, app_title, uses = parser.parse_module_header()
    fragment = parser.parse()

    return module_name, app_name, app_title, uses, fragment


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
]
