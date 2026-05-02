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
from .analytics import AnalyticsParserMixin
from .approval import ApprovalParserMixin
from .audit import AuditParserMixin
from .base import BaseParser
from .conditions import ConditionParserMixin
from .entity import EntityParserMixin
from .enum import EnumParserMixin
from .eventing import EventingParserMixin
from .feedback_widget import FeedbackWidgetParserMixin
from .flow import FlowParserMixin
from .governance import GovernanceParserMixin
from .grant import GrantParserMixin
from .hless import HLESSParserMixin
from .integration import IntegrationParserMixin
from .island import IslandParserMixin
from .job import JobParserMixin
from .ledger import LedgerParserMixin
from .llm import LLMParserMixin
from .messaging import MessagingParserMixin
from .nav import NavParserMixin
from .notification import NotificationParserMixin
from .params import ParamParserMixin
from .process import ProcessParserMixin
from .question import QuestionParserMixin
from .rhythm import RhythmParserMixin
from .rule import RuleParserMixin
from .scenario import ScenarioParserMixin
from .service import ServiceParserMixin
from .sla import SLAParserMixin
from .story import StoryParserMixin
from .subprocessor import SubprocessorParserMixin
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
    RuleParserMixin,
    QuestionParserMixin,
    RhythmParserMixin,
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
    IslandParserMixin,
    NotificationParserMixin,
    JobParserMixin,
    AuditParserMixin,
    NavParserMixin,
    GrantParserMixin,
    ParamParserMixin,
    FeedbackWidgetParserMixin,
    SubprocessorParserMixin,
    AnalyticsParserMixin,
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

    # ── Per-token-type top-level dispatch handlers ──────────────────────

    def _dispatch_archetype(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        archetype = self.parse_archetype()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "archetypes": [*fragment.archetypes, archetype],
            }
        )

    def _dispatch_entity(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        entity = self.parse_entity()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "entities": [*fragment.entities, entity],
            }
        )

    def _dispatch_surface(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        surface = self.parse_surface()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "surfaces": [*fragment.surfaces, surface],
            }
        )

    def _dispatch_experience(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        experience = self.parse_experience()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "experiences": [*fragment.experiences, experience],
            }
        )

    def _dispatch_service(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        service = self.parse_service()
        # Route to apis or domain_services based on type
        if isinstance(service, ir.DomainServiceSpec):
            return ir.ModuleFragment(
                **{
                    **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                    "domain_services": [*fragment.domain_services, service],
                }
            )
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "apis": [*fragment.apis, service],
            }
        )

    def _dispatch_foreign_model(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        foreign_model = self.parse_foreign_model()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "foreign_models": [*fragment.foreign_models, foreign_model],
            }
        )

    def _dispatch_integration(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        integration = self.parse_integration()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "integrations": [*fragment.integrations, integration],
            }
        )

    def _dispatch_test(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        test = self.parse_test()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "tests": [*fragment.tests, test],
            }
        )

    def _dispatch_workspace(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        workspace = self.parse_workspace()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "workspaces": [*fragment.workspaces, workspace],
            }
        )

    def _dispatch_flow(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        flow = self.parse_flow()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "e2e_flows": [*fragment.e2e_flows, flow],
            }
        )

    def _dispatch_persona(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        persona = self.parse_persona()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "personas": [*fragment.personas, persona],
            }
        )

    def _dispatch_scenario(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        scenario = self.parse_scenario()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "scenarios": [*fragment.scenarios, scenario],
            }
        )

    def _dispatch_story(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'story' token
        story = self.parse_story()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "stories": [*fragment.stories, story],
            }
        )

    def _dispatch_rhythm(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'rhythm' token
        rhythm = self.parse_rhythm()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "rhythms": [*fragment.rhythms, rhythm],
            }
        )

    def _dispatch_rule(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'rule' token
        rule = self.parse_rule()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "rules": [*fragment.rules, rule],
            }
        )

    def _dispatch_question(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'question' token
        question = self.parse_question()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "questions": [*fragment.questions, question],
            }
        )

    def _dispatch_message(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        message = self.parse_message()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "messages": [*fragment.messages, message],
            }
        )

    def _dispatch_channel(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        channel = self.parse_channel()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "channels": [*fragment.channels, channel],
            }
        )

    def _dispatch_asset(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        asset = self.parse_asset()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "assets": [*fragment.assets, asset],
            }
        )

    def _dispatch_document(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        document = self.parse_document()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "documents": [*fragment.documents, document],
            }
        )

    def _dispatch_template(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        template = self.parse_template()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "templates": [*fragment.templates, template],
            }
        )

    def _dispatch_demo(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        demo_fixtures = self.parse_demo()
        # Demo fixtures go into the last scenario or create a default one
        if fragment.scenarios:
            last_scenario = fragment.scenarios[-1]
            updated_scenario = ir.ScenarioSpec(
                id=last_scenario.id,
                name=last_scenario.name,
                description=last_scenario.description,
                persona_entries=last_scenario.persona_entries,
                seed_data_path=last_scenario.seed_data_path,
                demo_fixtures=list(last_scenario.demo_fixtures) + demo_fixtures,
            )
            return ir.ModuleFragment(
                **{
                    **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                    "scenarios": [*fragment.scenarios[:-1], updated_scenario],
                }
            )
        # Create a default scenario for standalone demo blocks
        default_scenario = ir.ScenarioSpec(
            id="default",
            name="Default",
            description="Default demo scenario",
            demo_fixtures=demo_fixtures,
        )
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "scenarios": [default_scenario],
            }
        )

    def _dispatch_event_model(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        event_model = self.parse_event_model()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "event_model": event_model,
            }
        )

    def _dispatch_subscribe(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        subscription = self.parse_subscribe()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "subscriptions": [*fragment.subscriptions, subscription],
            }
        )

    def _dispatch_project(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        projection = self.parse_projection()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "projections": [*fragment.projections, projection],
            }
        )

    def _dispatch_stream(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        stream = self.parse_stream()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "streams": [*fragment.streams, stream],
            }
        )

    def _dispatch_hless(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        hless_pragma = self.parse_hless_pragma()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "hless_pragma": hless_pragma,
            }
        )

    def _dispatch_policies(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        policies = self.parse_policies()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "policies": policies,
            }
        )

    def _dispatch_tenancy(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        tenancy = self.parse_tenancy()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "tenancy": tenancy,
            }
        )

    def _dispatch_interfaces(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        interfaces = self.parse_interfaces()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "interfaces": interfaces,
            }
        )

    def _dispatch_data_products(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        data_products = self.parse_data_products()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "data_products": data_products,
            }
        )

    def _dispatch_llm_model(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        llm_model = self.parse_llm_model()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "llm_models": [*fragment.llm_models, llm_model],
            }
        )

    def _dispatch_llm_config(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        llm_config = self.parse_llm_config()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "llm_config": llm_config,
            }
        )

    def _dispatch_llm_intent(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        llm_intent = self.parse_llm_intent()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "llm_intents": [*fragment.llm_intents, llm_intent],
            }
        )

    def _dispatch_process(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        process = self.parse_process()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "processes": [*fragment.processes, process],
            }
        )

    def _dispatch_schedule(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        schedule = self.parse_schedule()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "schedules": [*fragment.schedules, schedule],
            }
        )

    def _dispatch_ledger(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        ledger = self.parse_ledger()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "ledgers": [*fragment.ledgers, ledger],
            }
        )

    def _dispatch_transaction(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        transaction = self.parse_transaction()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "transactions": [*fragment.transactions, transaction],
            }
        )

    def _dispatch_enum(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        enum_spec = self.parse_enum()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "enums": [*fragment.enums, enum_spec],
            }
        )

    def _dispatch_webhook(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        webhook_spec = self.parse_webhook()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "webhooks": [*fragment.webhooks, webhook_spec],
            }
        )

    def _dispatch_nav(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        nav_spec = self.parse_nav_definition()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "nav_definitions": [*fragment.nav_definitions, nav_spec],
            }
        )

    def _dispatch_approval(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        approval_spec = self.parse_approval()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "approvals": [*fragment.approvals, approval_spec],
            }
        )

    def _dispatch_sla(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        sla_spec = self.parse_sla()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "slas": [*fragment.slas, sla_spec],
            }
        )

    def _dispatch_island(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        island_spec = self.parse_island()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "islands": [*fragment.islands, island_spec],
            }
        )

    def _dispatch_notification(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        notification_spec = self.parse_notification()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "notifications": [*fragment.notifications, notification_spec],
            }
        )

    def _dispatch_job(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        # #953 — `job <name> "title": ...` blocks (background-job DSL)
        job_spec = self.parse_job()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "jobs": [*fragment.jobs, job_spec],
            }
        )

    def _dispatch_audit(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        # #956 — `audit on <Entity>: ...` blocks (audit-trail DSL)
        audit_spec = self.parse_audit()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "audits": [*fragment.audits, audit_spec],
            }
        )

    def _dispatch_grant_schema(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'grant_schema' token
        grant_schema = self.parse_grant_schema()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "grant_schemas": [*fragment.grant_schemas, grant_schema],
            }
        )

    def _dispatch_param(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'param' token
        param = self.parse_param()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "params": [*fragment.params, param],
            }
        )

    def _dispatch_feedback_widget(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        self.advance()  # consume 'feedback_widget' token
        spec = self.parse_feedback_widget()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "feedback_widget": spec,
            }
        )

    def _dispatch_subprocessor(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        # parse_subprocessor consumes the SUBPROCESSOR token itself.
        spec = self.parse_subprocessor()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "subprocessors": [*fragment.subprocessors, spec],
            }
        )

    def _dispatch_analytics(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
        # parse_analytics consumes the ANALYTICS token itself.
        if fragment.analytics is not None:
            tok = self.current_token()
            from ..errors import make_parse_error

            raise make_parse_error(
                "Only one `analytics:` block is allowed per module.",
                self.file,
                tok.line,
                tok.column,
            )
        spec = self.parse_analytics()
        return ir.ModuleFragment(
            **{
                **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                "analytics": spec,
            }
        )

    def _build_parse_dispatch(self) -> dict:  # type: ignore[type-arg]
        """Build the token-type → handler dispatch table."""
        from ..lexer import TokenType

        return {
            TokenType.ARCHETYPE: self._dispatch_archetype,
            TokenType.ENTITY: self._dispatch_entity,
            TokenType.SURFACE: self._dispatch_surface,
            TokenType.EXPERIENCE: self._dispatch_experience,
            TokenType.SERVICE: self._dispatch_service,
            TokenType.FOREIGN_MODEL: self._dispatch_foreign_model,
            TokenType.INTEGRATION: self._dispatch_integration,
            TokenType.TEST: self._dispatch_test,
            TokenType.WORKSPACE: self._dispatch_workspace,
            TokenType.FLOW: self._dispatch_flow,
            TokenType.PERSONA: self._dispatch_persona,
            TokenType.SCENARIO: self._dispatch_scenario,
            TokenType.STORY: self._dispatch_story,
            TokenType.RHYTHM: self._dispatch_rhythm,
            TokenType.RULE: self._dispatch_rule,
            TokenType.QUESTION_DECL: self._dispatch_question,
            TokenType.MESSAGE: self._dispatch_message,
            TokenType.CHANNEL: self._dispatch_channel,
            TokenType.ASSET: self._dispatch_asset,
            TokenType.DOCUMENT: self._dispatch_document,
            TokenType.TEMPLATE: self._dispatch_template,
            TokenType.DEMO: self._dispatch_demo,
            TokenType.EVENT_MODEL: self._dispatch_event_model,
            TokenType.SUBSCRIBE: self._dispatch_subscribe,
            TokenType.PROJECT: self._dispatch_project,
            TokenType.STREAM: self._dispatch_stream,
            TokenType.HLESS: self._dispatch_hless,
            TokenType.POLICIES: self._dispatch_policies,
            TokenType.TENANCY: self._dispatch_tenancy,
            TokenType.INTERFACES: self._dispatch_interfaces,
            TokenType.DATA_PRODUCTS: self._dispatch_data_products,
            TokenType.LLM_MODEL: self._dispatch_llm_model,
            TokenType.LLM_CONFIG: self._dispatch_llm_config,
            TokenType.LLM_INTENT: self._dispatch_llm_intent,
            TokenType.PROCESS: self._dispatch_process,
            TokenType.SCHEDULE: self._dispatch_schedule,
            TokenType.LEDGER: self._dispatch_ledger,
            TokenType.TRANSACTION: self._dispatch_transaction,
            TokenType.ENUM: self._dispatch_enum,
            TokenType.WEBHOOK: self._dispatch_webhook,
            TokenType.NAV: self._dispatch_nav,
            TokenType.APPROVAL: self._dispatch_approval,
            TokenType.SLA: self._dispatch_sla,
            TokenType.ISLAND: self._dispatch_island,
            TokenType.NOTIFICATION: self._dispatch_notification,
            TokenType.JOB: self._dispatch_job,  # #953
            TokenType.AUDIT: self._dispatch_audit,  # #956
            TokenType.GRANT_SCHEMA: self._dispatch_grant_schema,
            TokenType.PARAM: self._dispatch_param,
            TokenType.FEEDBACK_WIDGET: self._dispatch_feedback_widget,
            TokenType.SUBPROCESSOR: self._dispatch_subprocessor,
            TokenType.ANALYTICS: self._dispatch_analytics,
        }

    def parse(self) -> ir.ModuleFragment:
        """
        Parse entire module and return IR fragment.

        Returns:
            ModuleFragment with all parsed declarations
        """
        from ..lexer import TokenType

        dispatch = self._build_parse_dispatch()
        fragment = ir.ModuleFragment()

        self.skip_newlines()

        while not self.match(TokenType.EOF):
            self.skip_newlines()

            token_type = self.current_token().type

            # v0.25.0 Views: VIEW followed by identifier/string = view construct
            # (VIEW is also used in e2e flow steps, so guard with peek)
            if token_type == TokenType.VIEW and self.peek_token().type in (
                TokenType.IDENTIFIER,
                TokenType.STRING,
            ):
                view_spec = self.parse_view()
                fragment = ir.ModuleFragment(
                    **{
                        **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
                        "views": [*fragment.views, view_spec],
                    }
                )
            elif token_type in dispatch:
                fragment = dispatch[token_type](fragment)
            else:
                if token_type == TokenType.EOF:
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
    "RhythmParserMixin",
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
    "IslandParserMixin",
    "GrantParserMixin",
    "ParamParserMixin",
]
