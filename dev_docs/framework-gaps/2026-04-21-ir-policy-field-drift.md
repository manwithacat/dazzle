# IR policy-field drift: DSL vocabulary ahead of runtime

**Surfaced:** cycle 368 (2026-04-21) via the IR-field-reader-parity ratchet lint
shipped cycle 367 (`tests/unit/test_ir_field_reader_parity.py`) + Heuristic 1
raw-layer verification.

## Problem statement

Dazzle's IR carries a substantial corpus of **policy fields** that no runtime
code reads. The DSL parser successfully populates these fields, the validator
accepts them, the `AppSpec` round-trips them through IR-level transformations
— and then the runtime ignores them and uses hardcoded defaults.

The author-visible effect is that DSL declarations appear honoured at every
checkpoint (parse success, no validation error, JSON dump shows the value),
but the live application behaves as if defaults were used everywhere.

This is a distinct shape from:

- **Cycle 232 Heuristic 4 (defaults-propagation audit)**: catches a *single*
  field whose intent fails to reach a template consumer. The present gap is
  systemic — whole policy objects are unread.
- **#838 (TwoFactorConfig orphan)**: the most extreme form of this class —
  no producer AND no consumer. Most other clusters in this gap *do* have
  producers but not consumers.

## Evidence (clusters from cycle-367 baseline)

### Cluster A — no producer, no consumer (most extreme)

- **`security.TwoFactorConfig`** — filed as **#838** (cycle 367). 5 policy fields
  (`methods`, `otp_length`, `otp_expiry_seconds`, `recovery_code_count`,
  `enforce_for_roles`) with zero external references. Runtime
  (`routes_2fa.py`/`totp.py`) hardcodes defaults.

### Cluster B — DSL parser populates, runtime never reads

Verified via `grep -rn "<field>" --include="*.py" src/` excluding the IR tree.

- **`messaging.ThrottleSpec`**
  - Producer: `dsl_parser_impl/messaging.py:626` (`_parse_throttle`) returns a populated `ThrottleSpec`.
  - Fields unread by any runtime: `max_messages`, `on_exceed`.
  - Also in the cluster: `SendOperationSpec.throttle` (the struct itself has no reader), `SendTriggerSpec.cron_expression`, `ProviderConfigSpec.max_per_minute`, `ChannelSpec.receive_operations`, `ReceiveOperationSpec.match_patterns`, `TemplateSpec.attachments`, `MappingSpec.is_template`.
  - Full subsystem fan-out: 12+ IR fields in the ratchet baseline declare
    messaging policy that the runtime does not consume.

- **`governance.TenantProvisioningSpec`**
  - Producer: `dsl_parser_impl/governance.py:326` populates.
  - Fields unread: `auto_create`, `require_approval`, `default_limits`.
  - Adjacent unread: `TenantIsolationSpec.enforce_in_queries`,
    `TenantIsolationSpec.cross_tenant_access`, `ErasureSpec.cascade`,
    `PoliciesSpec.default_retention`, `InterfacesSpec.default_auth`,
    `InterfacesSpec.default_rate_limit`.

- **`grants.GrantRelationSpec`**
  - Producer: populated via DSL (`grant_schema` block).
  - Fields unread: `principal_label`, `confirmation`, `revoke_verb`,
    `approved_by`, `expiry`, `max_duration`, `source_location`.
  - Impact is UI-facing: `revoke_verb` is the author-specified label on a
    revoke button that doesn't exist server-side; `confirmation` customises a
    dialog that never fires.

- **`hless.StreamSpec`**
  - Subsystem-wide: `ordering_scope`, `time_semantics`, `causality_fields`,
    `side_effect_policy`, `lineage`, `cross_partition`.
  - Plus sibling orphans: `TimeSemantics.t_event_field`/`t_log_field`/
    `t_process_field`, `IdempotencyStrategy.derivation`, entire
    `SideEffectPolicy` + `WindowSpec.grace_period` +
    `DerivationLineage.{derivation_type, rebuild_strategy, window_spec,
    derivation_function}` + `StreamSchema.compatibility`.
  - HLESS has its own entire orphan surface.

- **`appspec.AppSpec.hless_mode` / `hless_pragma`**
  - Top-level HLESS gating fields on the root `AppSpec` — **no reader
    anywhere**. A companion signal to the HLESS cluster above.

- **`llm.LLMModelSpec.cost_per_1k_input` / `cost_per_1k_output`**
  - Price-tracking metadata on LLM model specs — never billed against.
  - Adjacent: `ArtifactRefSpec.{artifact_id, storage_uri, byte_size}`.

- **`approvals.ApprovalSpec.*`** — 4 fields (`trigger_field`, `trigger_value`,
  `quorum`, `auto_approve`) declare approval triggering semantics; no runtime
  consumer.

### Cluster C — reserved vocabulary (may be intentional)

Some fields look aspirational — i.e. authored vocabulary for a feature that
the framework explicitly does not intend to implement at the runtime level:

- `email.NormalizedMailEvent.*` (~14 fields) — these read like an *event
  schema* (wire format for consumers downstream of Dazzle), not policy the
  framework itself acts on. **May be legitimate FP in the ratchet baseline.**
- `fidelity.SurfaceFidelityScore.interaction`, `fidelity.FidelityReport.integration_fidelity`
  — fidelity analytics; may be consumed by MCP-exposed tooling only.

## Root cause hypothesis

Dazzle's DSL grew faster than its runtime. New policy vocabulary landed in the
IR and parser (relatively cheap — the parse/IR round-trip is verifiable in
isolation), but runtime consumers lagged. Over time, the gap between
"vocabulary available to the author" and "behaviour available to the user"
widened without any mechanism to close it.

There's no structural reason a DSL author would notice the gap: validation
passes, lints pass, the app boots, the feature "exists." Observing the gap
requires either reading framework source or filing a support ticket when a
configured policy has no effect.

## Fix sketch

This is too broad for one issue. The pattern needs a **per-cluster triage
policy** with two possible verdicts:

### Verdict A — wire the runtime

The field is load-bearing intent. The runtime SHOULD honour it. File an
issue with a specific plan:
- which runtime module needs the read
- how the value flows (IR → context object → consumer)
- fallback behaviour when the IR field is absent or equals its default

**Triage heuristic:** the field has a direct user-visible consequence
(#838 2FA policy fields, `grants.revoke_verb` on a UI button, `throttle.on_exceed`
on a send pipeline).

### Verdict B — retire the vocabulary

The field is aspirational or speculative. Either:
- remove it from the IR + DSL parser with a CHANGELOG breaking-change entry
- mark it `deprecated: true` and have the DSL linter emit a warning when an
  author uses it
- narrow its scope (e.g. move from AppSpec to a plugin-scoped IR that
  downstream tooling must opt into)

**Triage heuristic:** the field is wire-format data for external consumers
(email event schema), analytics-only (fidelity scores), or was added for a
feature that was subsequently cancelled.

## Blast radius

### Confirmed affected

- 2FA subsystem (#838 + #829 + #831) — user-visible
- Messaging subsystem — silent misconfiguration of throttles, receive-mappings,
  template-attachments
- Governance tenant-provisioning — multi-tenant policy silently ignored
- Grants — revoke/confirmation UX customisation silently ignored
- HLESS subsystem — the entire stream-semantics vocabulary appears unwired

### Confirmed unaffected

- Workspace access control (`WorkspaceAccessSpec.allow_personas` /
  `deny_personas`) — readers verified in cycle 367 investigation of
  `TwoFactorConfig` (as contrast).
- Field-widget rendering (`FIELD_TYPE_TO_WIDGET` path, cycle 232 Heuristic 4
  case) — now wired through.

## Open questions

1. Which clusters are Verdict A vs Verdict B? This is a subsystem-by-subsystem
   judgment that should happen before any individual fix cycle.
2. Is the IR-field-reader-parity ratchet lint a sufficient rolling detector
   for *new* instances? **Yes** — the baseline captures 186 known orphans;
   new orphans will fail CI. This gap is about the *existing* 186, not
   future drift.
3. Should the IR grow a `metadata=` schema annotation distinguishing
   policy-intent fields from wire-format fields? That would let the
   ratchet lint differentiate "unread policy" (alarming) from "unread wire
   format" (expected) automatically, pruning Cluster C from the baseline.

## Related

- **#838** (cycle 367): TwoFactorConfig consolidated issue — concrete Verdict A
  case for one cluster. Same shape as the broader pattern described here.
- **#829 / #831** (cycles 299/303): earlier 2FA-specific issues.
- **Cycle 232 Heuristic 4** (`docs`): field-level defaults-propagation audit.
  This gap is the *systemic* version — entire policy objects, not single
  fields.
- **`tests/unit/test_ir_field_reader_parity.py`** (cycle 367) +
  `tests/unit/fixtures/ir_reader_baseline.json` — the detection mechanism
  that surfaced this gap. 186 known orphans frozen as debt; new orphans fail.
