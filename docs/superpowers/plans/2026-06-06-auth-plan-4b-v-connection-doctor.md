# Auth Plan 4b.v — Connection doctor (agent-driven activation)

> **For agentic workers:** hybrid inline execution + review. Embodies the agent-driven
> enterprise-auth north-star: human sets the binary requirement + pays for infra; the
> agent fills config and follows/emits a runbook.

**Goal:** `dazzle auth connection doctor <id>` reports exactly what a connection still needs
to go live (config-vs-missing) + an ordered activation runbook, with a `--json` mode an agent
can parse to drive remediation. `dazzle auth connection scaffold` prints the end-to-end
create→verify→register command sequence for a fresh connection.

**Architecture:** A pure `diagnose_connection(connection, *, secret_key_ok, sso_extra_ok,
dns_extra_ok) -> Diagnosis` returns structured `Check`s (required/recommended ·
ok/warn/fail · detail · remedy) + `ready` (all required ok) + `runbook`. The CLI computes the
three environment flags, loads the connection (key-gated), and renders rich or JSON. **No
network** (no discovery fetch) — deterministic + no SSRF surface; a discovery probe is a
deferred opt-in. **Secrets are never printed** — only presence is checked.

**Tech Stack:** stdlib, the 4a–4b.iv connection modules, Typer/rich.

---

## Checks (OIDC)

Required (gate `ready`): `secret_key` (DAZZLE_CONNECTION_SECRET valid) · `sso_extra` (authlib) ·
`issuer_or_discovery` · `client_id` · `client_secret` (presence only) · `verified_domain` (≥1).
Recommended (warn): `dns_extra` (dnspython, for verify-domain) · `group_mapping` (else members
get no roles — default-deny) · `claimed_unverified` (publish TXT + verify).

The runbook lists the remedy for each failing required check in order, then always the
redirect-URI registration reminder (`<base_url>/auth/enterprise/callback`) and a test pointer.

## Task 1: diagnose kernel

**Files:** Create `src/dazzle/http/runtime/auth/connection_doctor.py`,
`tests/unit/test_connection_doctor.py`.

- `Check`/`Diagnosis` frozen dataclasses, `diagnose_connection`. Tests: fully-configured →
  ready + empty required-remedies; each missing required field → fail + remedy + not ready;
  empty group_mapping / no-verified-but-claimed → warn (still affects ready only via verified);
  non-oidc type → minimal note.

## Task 2: CLI `doctor` + `scaffold`

**Files:** Modify `src/dazzle/cli/auth_connection.py`.

- `doctor <id> [--json]`: key-gate (no key → single remedy, exit 1), load, diagnose, render
  (rich table + runbook, or JSON), exit 0 iff ready. Never prints the secret value.
- `scaffold`: print the create→add-domain→publish-TXT→verify→register sequence (placeholders).

## Task 3: verify + review + ship

- ruff + mypy + drift + mkdocs --strict; full unit slice.
- Review (code-reviewer) on secret-non-leak + exit-code/ready correctness.
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
