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
from .approval import ApprovalParserMixin
from .base import BaseParser
from .conditions import ConditionParserMixin
from .entity import EntityParserMixin
from .enum import EnumParserMixin
from .eventing import EventingParserMixin
from .flow import FlowParserMixin
from .governance import GovernanceParserMixin
from .hless import HLESSParserMixin
from .integration import IntegrationParserMixin
from .ledger import LedgerParserMixin
from .llm import LLMParserMixin
from .messaging import MessagingParserMixin
from .process import ProcessParserMixin
from .scenario import ScenarioParserMixin
from .service import ServiceParserMixin
from .sla import SLAParserMixin
from .story import StoryParserMixin
from .surface import SurfaceParserMixin
from .test import TestParserMixin
from .types import TypeParserMixin
from .ux import UXParserMixin
from .view import ViewParserMixin
from .webhook import WebhookParserMixin
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
    LedgerParserMixin,
    EnumParserMixin,
    ViewParserMixin,
    WebhookParserMixin,
    ApprovalParserMixin,
    SLAParserMixin,
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

        def _updated(frag: ir.ModuleFragment, **overrides: object) -> ir.ModuleFragment:
            """Create a new fragment copying all fields, with overrides applied."""
            return ir.ModuleFragment(
                **{
                    **{f: getattr(frag, f) for f in ir.ModuleFragment.model_fields},
                    **overrides,
                }
            )

        fragment = ir.ModuleFragment()

        self.skip_newlines()

        while not self.match(TokenType.EOF):
            self.skip_newlines()

            # v0.7.1: Check for archetype declaration
            if self.match(TokenType.ARCHETYPE):
                archetype = self.parse_archetype()
                fragment = _updated(fragment, archetypes=[*fragment.archetypes, archetype])

            elif self.match(TokenType.ENTITY):
                entity = self.parse_entity()
                fragment = _updated(fragment, entities=[*fragment.entities, entity])

            elif self.match(TokenType.SURFACE):
                surface = self.parse_surface()
                fragment = _updated(fragment, surfaces=[*fragment.surfaces, surface])

            elif self.match(TokenType.EXPERIENCE):
                experience = self.parse_experience()
                fragment = _updated(fragment, experiences=[*fragment.experiences, experience])

            elif self.match(TokenType.SERVICE):
                service = self.parse_service()
                # Route to apis or domain_services based on type
                if isinstance(service, ir.DomainServiceSpec):
                    fragment = _updated(
                        fragment,
                        domain_services=[*fragment.domain_services, service],
                    )
                else:
                    fragment = _updated(fragment, apis=[*fragment.apis, service])

            elif self.match(TokenType.FOREIGN_MODEL):
                foreign_model = self.parse_foreign_model()
                fragment = _updated(
                    fragment, foreign_models=[*fragment.foreign_models, foreign_model]
                )

            elif self.match(TokenType.INTEGRATION):
                integration = self.parse_integration()
                fragment = _updated(fragment, integrations=[*fragment.integrations, integration])

            elif self.match(TokenType.TEST):
                test = self.parse_test()
                fragment = _updated(fragment, tests=[*fragment.tests, test])

            elif self.match(TokenType.WORKSPACE):
                workspace = self.parse_workspace()
                fragment = _updated(fragment, workspaces=[*fragment.workspaces, workspace])

            elif self.match(TokenType.FLOW):
                flow = self.parse_flow()
                fragment = _updated(fragment, e2e_flows=[*fragment.e2e_flows, flow])

            elif self.match(TokenType.PERSONA):
                persona = self.parse_persona()
                fragment = _updated(fragment, personas=[*fragment.personas, persona])

            elif self.match(TokenType.SCENARIO):
                scenario = self.parse_scenario()
                fragment = _updated(fragment, scenarios=[*fragment.scenarios, scenario])

            # v0.22.0 Stories DSL
            elif self.match(TokenType.STORY):
                self.advance()  # consume 'story' token
                story = self.parse_story()
                fragment = _updated(fragment, stories=[*fragment.stories, story])

            # v0.9.0 Messaging Channels
            elif self.match(TokenType.MESSAGE):
                message = self.parse_message()
                fragment = _updated(fragment, messages=[*fragment.messages, message])

            elif self.match(TokenType.CHANNEL):
                channel = self.parse_channel()
                fragment = _updated(fragment, channels=[*fragment.channels, channel])

            elif self.match(TokenType.ASSET):
                asset = self.parse_asset()
                fragment = _updated(fragment, assets=[*fragment.assets, asset])

            elif self.match(TokenType.DOCUMENT):
                document = self.parse_document()
                fragment = _updated(fragment, documents=[*fragment.documents, document])

            elif self.match(TokenType.TEMPLATE):
                template = self.parse_template()
                fragment = _updated(fragment, templates=[*fragment.templates, template])

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
                    fragment = _updated(
                        fragment,
                        scenarios=[*fragment.scenarios[:-1], updated_scenario],
                    )
                else:
                    # Create a default scenario for standalone demo blocks
                    default_scenario = ir.ScenarioSpec(
                        id="default",
                        name="Default",
                        description="Default demo scenario",
                        demo_fixtures=demo_fixtures,
                    )
                    fragment = _updated(fragment, scenarios=[default_scenario])

            # v0.18.0 Event-First Architecture
            elif self.match(TokenType.EVENT_MODEL):
                event_model = self.parse_event_model()
                fragment = _updated(fragment, event_model=event_model)

            elif self.match(TokenType.SUBSCRIBE):
                subscription = self.parse_subscribe()
                fragment = _updated(fragment, subscriptions=[*fragment.subscriptions, subscription])

            elif self.match(TokenType.PROJECT):
                projection = self.parse_projection()
                fragment = _updated(fragment, projections=[*fragment.projections, projection])

            # v0.19.0 HLESS - High-Level Event Semantics
            elif self.match(TokenType.STREAM):
                stream = self.parse_stream()
                fragment = _updated(fragment, streams=[*fragment.streams, stream])

            elif self.match(TokenType.HLESS):
                hless_pragma = self.parse_hless_pragma()
                fragment = _updated(fragment, hless_pragma=hless_pragma)

            # v0.18.0 Governance sections (Issue #25)
            elif self.match(TokenType.POLICIES):
                policies = self.parse_policies()
                fragment = _updated(fragment, policies=policies)

            elif self.match(TokenType.TENANCY):
                tenancy = self.parse_tenancy()
                fragment = _updated(fragment, tenancy=tenancy)

            elif self.match(TokenType.INTERFACES):
                interfaces = self.parse_interfaces()
                fragment = _updated(fragment, interfaces=interfaces)

            elif self.match(TokenType.DATA_PRODUCTS):
                data_products = self.parse_data_products()
                fragment = _updated(fragment, data_products=data_products)

            # LLM Jobs as First-Class Events (v0.21.0 - Issue #33)
            elif self.match(TokenType.LLM_MODEL):
                llm_model = self.parse_llm_model()
                fragment = _updated(fragment, llm_models=[*fragment.llm_models, llm_model])

            elif self.match(TokenType.LLM_CONFIG):
                llm_config = self.parse_llm_config()
                fragment = _updated(fragment, llm_config=llm_config)

            elif self.match(TokenType.LLM_INTENT):
                llm_intent = self.parse_llm_intent()
                fragment = _updated(fragment, llm_intents=[*fragment.llm_intents, llm_intent])

            # v0.23.0 Process Workflows
            elif self.match(TokenType.PROCESS):
                process = self.parse_process()
                fragment = _updated(fragment, processes=[*fragment.processes, process])

            elif self.match(TokenType.SCHEDULE):
                schedule = self.parse_schedule()
                fragment = _updated(fragment, schedules=[*fragment.schedules, schedule])

            # v0.24.0 TigerBeetle Ledgers
            elif self.match(TokenType.LEDGER):
                ledger = self.parse_ledger()
                fragment = _updated(fragment, ledgers=[*fragment.ledgers, ledger])

            elif self.match(TokenType.TRANSACTION):
                transaction = self.parse_transaction()
                fragment = _updated(fragment, transactions=[*fragment.transactions, transaction])

            # v0.25.0 Shared Enums
            elif self.match(TokenType.ENUM):
                enum_spec = self.parse_enum()
                fragment = _updated(fragment, enums=[*fragment.enums, enum_spec])

            # v0.25.0 Views (VIEW token already exists for e2e flows,
            # but top-level 'view' followed by identifier = view construct)
            elif self.match(TokenType.VIEW) and self.peek_token().type in (
                TokenType.IDENTIFIER,
                TokenType.STRING,
            ):
                view_spec = self.parse_view()
                fragment = _updated(fragment, views=[*fragment.views, view_spec])

            # v0.25.0 Webhooks
            elif self.match(TokenType.WEBHOOK):
                webhook_spec = self.parse_webhook()
                fragment = _updated(fragment, webhooks=[*fragment.webhooks, webhook_spec])

            # v0.25.0 Approvals
            elif self.match(TokenType.APPROVAL):
                approval_spec = self.parse_approval()
                fragment = _updated(fragment, approvals=[*fragment.approvals, approval_spec])

            # v0.25.0 SLAs
            elif self.match(TokenType.SLA):
                sla_spec = self.parse_sla()
                fragment = _updated(fragment, slas=[*fragment.slas, sla_spec])

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
    "LedgerParserMixin",
    "EnumParserMixin",
    "ViewParserMixin",
    "WebhookParserMixin",
    "ApprovalParserMixin",
    "SLAParserMixin",
]
