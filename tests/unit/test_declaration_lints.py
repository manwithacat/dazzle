"""Flense ship U: lints for declarations that silently change nothing.

Ships N, Q and R found DSL that parses, fills the IR and is then ignored: lenient
blocks that skip unknown keys, clauses no runtime reads, tenancy modes nothing
implements and grant clauses that contradict each other. These tests pin the
warning each now produces, and that a clean declaration stays silent.
"""

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.validation import (
    validate_grant_relation_clauses,
    validate_tenancy_mode_implemented,
)

_HEADER = 'module test.core\napp t "T"\n\n'


def _parse(body: str) -> ir.ModuleFragment:
    *_, fragment = parse_dsl(_HEADER + body, Path("test.dsl"))
    return fragment


def _parse_warnings(body: str) -> list[str]:
    return _parse(body).parse_warnings


# ---------------------------------------------------------------------------
# Item 5 — W_UNKNOWN_BLOCK_KEY at each lenient block's skip point
# ---------------------------------------------------------------------------

_UNKNOWN_KEY_CASES = {
    "policies": (
        "policies:\n  default_retention: long\n  audit_access: false\n",
        "default_retention",
        lambda f: f.policies is not None and f.policies.audit_access is False,
    ),
    "tenancy": (
        "tenancy:\n  mode: shared_schema\n  provisioning:\n    auto: true\n"
        "    region: eu\n  partition_key: org_id\n",
        "provisioning",
        lambda f: f.tenancy is not None and f.tenancy.isolation.partition_key == "org_id",
    ),
    "island": (
        'island chart:\n  prop size: int\n  entity: Task\n  fallback: "…"\n',
        "prop",
        lambda f: f.islands[0].entity == "Task" and f.islands[0].fallback == "…",
    ),
    "llm_model": (
        'llm_model m1:\n  provider: anthropic\n  model_id: m\n  description: "Fast"\n  max_tokens: 512\n',
        "description",
        lambda f: f.llm_models[0].max_tokens == 512,
    ),
    "llm_config": (
        "llm_config:\n  fallback_mode: mock\n  default_model: m1\n",
        "fallback_mode",
        lambda f: f.llm_config is not None and f.llm_config.default_model == "m1",
    ),
    "llm_intent": (
        'llm_intent summarise "S":\n  model: m1\n  vision: true\n  prompt: "x"\n',
        "vision",
        lambda f: f.llm_intents[0].prompt_template == "x",
    ),
    "view": (
        "view Totals:\n  source: Task\n  time_bucket: month\n  fields:\n    n: count()\n",
        "time_bucket",
        lambda f: f.views[0].source_entity == "Task" and len(f.views[0].fields) == 1,
    ),
    "process": (
        "process p:\n  emits:\n    on_complete: done\n  timeout: 1h\n"
        "  steps:\n    - step s:\n        service: svc\n",
        "emits",
        lambda f: f.processes[0].timeout_seconds == 3600 and len(f.processes[0].steps) == 1,
    ),
    "process step": (
        "process p:\n  steps:\n    - step s:\n        output: result\n        service: svc\n",
        "output",
        lambda f: f.processes[0].steps[0].service == "svc",
    ),
    "schedule": (
        'schedule nightly:\n  emits: done\n  cron: "0 1 * * *"\n'
        "  steps:\n    - step s:\n        service: svc\n",
        "emits",
        lambda f: f.schedules[0].cron == "0 1 * * *",
    ),
    "integration action": (
        "integration crm:\n  action push:\n    response foreign Contact\n"
        "    bogus: 1\n    when surface contact_create\n",
        "bogus",
        lambda f: f.integrations[0].actions[0].when_surface == "contact_create",
    ),
    "integration sync": (
        "integration crm:\n  sync pull:\n    from service crm_api\n    into entity Contact\n",
        "from",
        lambda f: f.integrations[0].syncs[0].into_entity == "Contact",
    ),
    # Flense ship X: the remaining lenient sub-blocks and the top-level loop.
    "llm_config logging": (
        "llm_config:\n  logging:\n    log_prompt: false\n    redact_pii: false\n"
        "  default_model: m1\n",
        "log_prompt",
        lambda f: (
            f.llm_config is not None
            and f.llm_config.logging.redact_pii is False
            and f.llm_config.logging.log_prompts is True
            and f.llm_config.default_model == "m1"
        ),
    ),
    "llm_intent retry": (
        'llm_intent s "S":\n  model: m1\n  retry:\n    max_attempt: 5\n'
        '    backoff: linear\n  prompt: "x"\n',
        "max_attempt",
        lambda f: (
            f.llm_intents[0].retry is not None
            and f.llm_intents[0].retry.max_attempts == 3
            and f.llm_intents[0].retry.backoff == ir.RetryBackoff.LINEAR
            and f.llm_intents[0].prompt_template == "x"
        ),
    ),
    "llm_intent pii": (
        'llm_intent s "S":\n  model: m1\n  pii:\n    scanning: true\n'
        '    action: reject\n  prompt: "x"\n',
        "scanning",
        lambda f: (
            f.llm_intents[0].pii is not None
            and f.llm_intents[0].pii.scan is False
            and f.llm_intents[0].pii.action == ir.PIIAction.REJECT
        ),
    ),
    "llm_intent trigger": (
        'llm_intent s "S":\n  model: m1\n  trigger:\n    on_entity: Task\n'
        "    debounce:\n      seconds: 5\n    on_event: created\n"
        '    when: "entity.category == null"\n  prompt: "x"\n',
        "debounce",
        lambda f: (
            f.llm_intents[0].triggers[0].when == "entity.category == null"
            and f.llm_intents[0].prompt_template == "x"
        ),
    ),
    "process trigger": (
        "process p:\n  trigger:\n    debounce: 5\n    when: entity Task created\n"
        "  steps:\n    - step s:\n        service: svc\n",
        "debounce",
        lambda f: (
            f.processes[0].trigger is not None
            and f.processes[0].trigger.entity_name == "Task"
            and len(f.processes[0].steps) == 1
        ),
    ),
    "human_task": (
        "process p:\n  steps:\n    - step s:\n        human_task:\n"
        "          form:\n            ok: bool required\n          timeout: 4h\n",
        "form",
        lambda f: (
            f.processes[0].steps[0].human_task is not None
            and f.processes[0].steps[0].human_task.timeout_seconds == 4 * 3600
        ),
    ),
    "parallel": (
        "process p:\n  steps:\n    - parallel both:\n        policy:\n"
        "          fail_fast: true\n        - step a:\n            service: svc\n",
        "policy",
        lambda f: [s.name for s in f.processes[0].steps[0].parallel_steps] == ["a"],
    ),
    "module": (
        "entitty Task:\n  id: uuid pk\n  meta:\n    x: 1\n\nentity B:\n  id: uuid pk\n",
        "entitty",
        lambda f: [e.name for e in f.entities] == ["B"],
    ),
}


@pytest.mark.parametrize("block", sorted(_UNKNOWN_KEY_CASES))
def test_unknown_key_in_lenient_block_warns_and_skips_only_that_entry(block: str) -> None:
    body, key, rest_parsed = _UNKNOWN_KEY_CASES[block]
    fragment = _parse(body)
    line = 3 + next(
        n for n, text in enumerate(body.splitlines(), 1) if text.strip().startswith(key)
    )
    assert fragment.parse_warnings == [
        f"W_UNKNOWN_BLOCK_KEY: unknown key `{key}` in `{block}` block ignored (test.dsl:{line})"
    ]
    # The entries after the unknown one — including after a skipped nested block — still parse.
    assert rest_parsed(fragment)


_CLEAN_BLOCKS = [
    "policies:\n  audit_access: true\n",
    "tenancy:\n  mode: shared_schema\n  partition_key: org_id\n  topics: namespace_per_tenant\n",
    "island chart:\n  entity: Task\n",
    "llm_model m1:\n  provider: anthropic\n  model_id: m\n  max_tokens: 512\n",
    "llm_config:\n  default_model: m1\n  rate_limits:\n    m1: 10\n",
    'llm_intent summarise "S":\n  model: m1\n  prompt: "x"\n',
    "view Totals:\n  source: Task\n  fields:\n    n: count()\n",
    "process p:\n  timeout: 1h\n  steps:\n    - step s:\n        service: svc\n",
    'schedule nightly:\n  cron: "0 1 * * *"\n  steps:\n    - step s:\n        service: svc\n',
    "integration crm:\n  sync pull:\n    into entity Contact\n",
    "llm_config:\n  logging:\n    log_prompts: false\n    log_completions: true\n"
    "    redact_pii: false\n",
    'llm_intent s "S":\n  model: m1\n  prompt: "x"\n  retry:\n    max_attempts: 2\n'
    "    backoff: linear\n    initial_delay_ms: 100\n    max_delay_ms: 1000\n"
    '  pii:\n    scan: true\n    action: redact\n    patterns: "a", "b"\n'
    "  trigger:\n    on_entity: Task\n    on_event: created\n    input_map:\n"
    '      title: entity.title\n    write_back:\n      Task.tag: output\n    when: "x"\n',
    "process p:\n  trigger:\n    when: entity Task created\n  steps:\n"
    "    - step s:\n        human_task:\n          surface: review\n"
    "          entity: Task\n          assignee_role: manager\n"
    '          assignee: "owner"\n          timeout: 4h\n          outcomes:\n'
    '            - ok "OK":\n                goto: complete\n'
    "    - parallel both:\n        - step a:\n            service: svc\n"
    "        - step b:\n            service: svc\n",
    "entity B:\n  id: uuid pk\n",
]


@pytest.mark.parametrize("body", _CLEAN_BLOCKS, ids=lambda b: b.split()[0])
def test_known_keys_produce_no_parse_warnings(body: str) -> None:
    assert _parse_warnings(body) == []


def test_unknown_list_item_in_parallel_block_warns_and_skips_the_item() -> None:
    body = (
        "process p:\n  steps:\n    - parallel both:\n        - stepp a:\n"
        "            service: svc\n        - step b:\n            service: svc\n"
    )
    fragment = _parse(body)
    assert fragment.parse_warnings == [
        "W_UNKNOWN_BLOCK_KEY: unknown key `stepp` in `parallel` block ignored (test.dsl:7)"
    ]
    assert [s.name for s in fragment.processes[0].steps[0].parallel_steps] == ["b"]


def test_parse_warnings_reach_validate_through_the_linker() -> None:
    body = "entity Task:\n  id: uuid pk\n\ntenancy:\n  provisioning:\n    auto: true\n"
    *_, fragment = parse_dsl(_HEADER + body, Path("test.dsl"))
    module = ir.ModuleIR(name="test.core", file=Path("test.dsl"), app_name="t", fragment=fragment)
    appspec = build_appspec([module], "test.core")
    _, warnings, _ = lint_appspec(appspec, suggest=False)
    assert (
        "W_UNKNOWN_BLOCK_KEY: unknown key `provisioning` in `tenancy` block ignored (test.dsl:8)"
        in warnings
    )


# ---------------------------------------------------------------------------
# Item 2 — tenancy `topics:` is a closed set: unknown values are a parse error
# ---------------------------------------------------------------------------


def test_unknown_tenancy_topics_value_is_a_parse_error() -> None:
    with pytest.raises(ParseError, match="Unknown tenancy topics 'per_tenant'"):
        _parse("tenancy:\n  topics: per_tenant\n")


@pytest.mark.parametrize("value", ["shared", "namespace_per_tenant"])
def test_known_tenancy_topics_values_parse(value: str) -> None:
    fragment = _parse(f"tenancy:\n  topics: {value}\n")
    assert fragment.tenancy is not None
    assert fragment.tenancy.isolation.topic_namespace.value == value


# ---------------------------------------------------------------------------
# Item 4 — W_DECLARED_NOT_READ for clauses consumers write that nothing reads
# ---------------------------------------------------------------------------

_UNREAD_CASES = {
    "feedback_widget": (
        "feedback_widget: enabled\n  position: bottom-left\n  shortcut: backtick\n"
        "  severities: [blocker]\n",
        "feedback_widget: `shortcut:`/`severities:` declared but not read by the runtime",
        "feedback_widget: enabled\n  position: bottom-left\n",
    ),
    "service stub": (
        "service calc:\n  kind: domain_logic\n  stub: python\n",
        "service 'calc': `stub:` declared but not read by the runtime",
        "service calc:\n  kind: domain_logic\n",
    ),
    "schedule catch_up/overlap": (
        'schedule nightly:\n  cron: "0 1 * * *"\n  catch_up: false\n  overlap: skip\n'
        "  steps:\n    - step s:\n        service: svc\n",
        "schedule 'nightly': `catch_up:`/`overlap:` declared but not read by the runtime",
        'schedule nightly:\n  cron: "0 1 * * *"\n  steps:\n    - step s:\n        service: svc\n',
    ),
    "llm_config artifact_store": (
        "llm_config:\n  artifact_store: local\n",
        "llm_config: `artifact_store:` declared but not read by the runtime",
        "llm_config:\n  default_model: m1\n",
    ),
    "entity_card scope_param": (
        "workspace w:\n  card:\n    source: Task\n    display: entity_card\n"
        "    entity_card_config:\n      scope_param: pupil_id\n      sections:\n"
        "        - name: halo\n          mode: halo\n          fields: [title]\n",
        "entity_card_config: `scope_param:` declared but not read by the runtime",
        "workspace w:\n  card:\n    source: Task\n    display: entity_card\n"
        "    entity_card_config:\n      sections:\n"
        "        - name: halo\n          mode: halo\n          fields: [title]\n",
    ),
}


@pytest.mark.parametrize("case", sorted(_UNREAD_CASES))
def test_unread_clause_warns(case: str) -> None:
    body, expected, _ = _UNREAD_CASES[case]
    warnings = [w for w in _parse_warnings(body) if w.startswith("W_DECLARED_NOT_READ")]
    assert len(warnings) == 1
    assert expected in warnings[0]
    assert "; no DD (test.dsl:" in warnings[0]


@pytest.mark.parametrize("case", sorted(_UNREAD_CASES))
def test_construct_without_unread_clause_is_silent(case: str) -> None:
    _, _, clean = _UNREAD_CASES[case]
    assert _parse_warnings(clean) == []


def test_scalar_concurrency_warns_instead_of_failing_the_parse() -> None:
    fragment = _parse("llm_config:\n  concurrency: 3\n  default_model: m1\n")
    assert fragment.llm_config is not None
    assert fragment.llm_config.concurrency is None
    assert fragment.llm_config.default_model == "m1"
    assert fragment.parse_warnings == [
        "W_CLAUSE_VALUE_IGNORED: llm_config: `concurrency:` takes an indented block of "
        "`<model>: <limit>` lines; the inline value is ignored (test.dsl:5)"
    ]


# ---------------------------------------------------------------------------
# Items 1 and 3 — validator lints over the AppSpec
# ---------------------------------------------------------------------------


def _appspec(**kwargs: object) -> AppSpec:
    return AppSpec(name="t", domain=DomainSpec(entities=[]), **kwargs)  # type: ignore[arg-type]


def _tenancy(mode: ir.TenancyMode) -> ir.TenancySpec:
    return ir.TenancySpec(isolation=ir.TenantIsolationSpec(mode=mode))


@pytest.mark.parametrize(
    ("mode", "warns"),
    [
        (ir.TenancyMode.SCHEMA_PER_TENANT, True),
        (ir.TenancyMode.DATABASE_PER_TENANT, True),
        (ir.TenancyMode.SHARED_SCHEMA, False),
        (ir.TenancyMode.SINGLE, False),
    ],
)
def test_unimplemented_tenancy_mode_warns(mode: ir.TenancyMode, warns: bool) -> None:
    errors, warnings = validate_tenancy_mode_implemented(_appspec(tenancy=_tenancy(mode)))
    assert errors == []
    expected = [
        f"W_TENANCY_MODE_UNIMPLEMENTED: tenancy mode '{mode.value}' is not implemented by "
        f"the runtime: no tenant fencing is applied; use shared_schema or single"
    ]
    assert warnings == (expected if warns else [])


def _grant(**rel: object) -> AppSpec:
    relation = ir.GrantRelationSpec(
        name="cover",
        label="Cover",
        granted_by=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")),
        **rel,  # type: ignore[arg-type]
    )
    schema = ir.GrantSchemaSpec(name="dept", label="Dept", scope="Department", relations=[relation])
    return _appspec(grant_schemas=[schema])


_APPROVER = ir.ConditionExpr(role_check=ir.RoleCheck(role_name="head"))


@pytest.mark.parametrize(
    ("rel", "code"),
    [
        (
            {"expiry": ir.GrantExpiryMode.NONE, "max_duration": "30d"},
            "W_GRANT_EXPIRY_CONTRADICTION",
        ),
        (
            {"approval": ir.GrantApprovalMode.NONE, "approved_by": _APPROVER},
            "W_GRANT_APPROVER_UNUSED",
        ),
        (
            {"approval": ir.GrantApprovalMode.IMMEDIATE, "approved_by": _APPROVER},
            "W_GRANT_APPROVER_UNUSED",
        ),
        ({"principal_label": "Staff", "revoke_verb": "Remove"}, "W_DECLARED_NOT_READ"),
    ],
)
def test_contradictory_or_unread_grant_clause_warns(rel: dict[str, object], code: str) -> None:
    errors, warnings = validate_grant_relation_clauses(_grant(**rel))
    assert errors == []
    assert len(warnings) == 1
    assert warnings[0].startswith(f"{code}: grant_schema 'dept' relation 'cover': ")


def test_presentation_only_warning_points_at_ship_q() -> None:
    _, warnings = validate_grant_relation_clauses(_grant(principal_label="Staff"))
    assert warnings == [
        "W_DECLARED_NOT_READ: grant_schema 'dept' relation 'cover': `principal_label:` "
        "declared but not read by the runtime (presentation text no framework grant UI "
        "renders yet); see CHANGELOG, flense ship Q"
    ]


@pytest.mark.parametrize(
    "rel",
    [
        {},
        {"expiry": ir.GrantExpiryMode.REQUIRED, "max_duration": "30d"},
        {"expiry": ir.GrantExpiryMode.NONE},
        {"approval": ir.GrantApprovalMode.REQUIRED, "approved_by": _APPROVER},
        {"approval": ir.GrantApprovalMode.NONE},
    ],
)
def test_consistent_grant_relation_is_silent(rel: dict[str, object]) -> None:
    assert validate_grant_relation_clauses(_grant(**rel)) == ([], [])
