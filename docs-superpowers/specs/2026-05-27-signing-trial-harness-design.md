# Signing trial harness — design

**Date:** 2026-05-27
**Status:** Draft for implementation
**Related:** #1283 (`signable: true` primitive, closed v0.79.13)

## Goal

Exercise the `signable: true` DSL primitive end-to-end in two example apps and grade each run on four axes — functional correctness, UX quality (LLM-persona verdict), per-route latency, and PAdES signature integrity. The harness is an extension of `dazzle qa trial`, not a new command.

## Why

`signable: true` shipped across v0.79.7–v0.79.13 (#1283 phases 2-8). No example app currently uses it. Two downstream consumers (cyfuture, AegisMark) already need the primitive in production — having two in-tree example apps that exercise it (one engagement-letter shaped, one waiver-shaped) is the right validation that the abstraction is genuinely generic. Reusing the existing `dazzle qa trial` substrate means the same LLM-persona harness that already grades UX across the framework also grades the signing flow; no parallel test substrate is introduced.

## Non-goals

- Higher signature tiers (AES, QES) — out of scope; primitive is SES + PAdES B-T only.
- Real notification delivery — the harness uses a mock inbox tool the persona reads. Production email delivery is a separate concern.
- Cross-tenant cert isolation — phase-1 of `signable:` ships one CA per project; harness mirrors that.
- DocuSeal interop or third-party signing-service drivers.

## Architecture

```
dazzle qa trial <app> <scenario>
  │
  ├─ Driver boots `dazzle serve` subprocess
  │     env: SIGNING_CERT_PFX_B64 / SIGNING_CERT_PASSWORD / SIGNING_TOKEN_SECRET
  │     all ephemeral, minted by `dazzle signing init` into a per-run tmpdir
  │
  ├─ Driver inspects app_spec → detects signable entities → conditionally
  │     registers four persona-facing tools (skipped silently if no signable
  │     entity exists; non-signing apps unchanged)
  │
  ├─ Seed: harness inserts one row of the signable entity in `sent` status,
  │     mints a token via dazzle.signing.tokens.mint_token(), writes the link
  │     into the persona's mock inbox
  │
  ├─ Persona observe → decide → act loop runs the existing trial machinery.
  │     Persona reads the inbox, opens the link, signs or declines.
  │     Persona is never told about token mechanics or status field names.
  │
  ├─ Verification phase (auto, fires when transcript shows any /sign/ hit):
  │     - read final row from the runtime DB
  │     - assert status transition matches the inferred expected outcome
  │     - assert audit row populated
  │     - if PDF produced: pyhanko validate_pdf_signature against project chain
  │     - capture get_sign and post_sign latency from request log
  │
  └─ Report = existing trial JSON + `signing_outcomes` block
```

## Components

### A. DSL additions in the two example apps

**`examples/contact_manager/dsl/signing.dsl`** — declares `EngagementLetter` with `signable: true`. Fields: `contact: ref Contact required`, `party: str(200) required`, `scope_summary: text`, `effective_date: date`. Template at `examples/contact_manager/templates/letters/EngagementLetter/default.html.j2`.

**`examples/support_tickets/dsl/signing.dsl`** — declares `SlaWaiver` with `signable: true`. Fields: `ticket: ref Ticket required`, `breach_summary: text required`, `waiver_terms: text required`, `signatory_role: str(120) required`. Template at `examples/support_tickets/templates/letters/SlaWaiver/default.html.j2`.

**`signing_validator:` hooks** at `examples/<app>/app/signing/validator.py`. Each hook is a no-op on the happy path and raises `SigningError("…")` only when called against a row marked with a designated `_test_reject: true` (or equivalent) marker the harness sets for the validator-rejected scenario.

### B. Harness extension (in framework, under `src/dazzle/qa/`)

**`src/dazzle/qa/signing_tools.py`** — four persona-facing agent tools, conditionally registered at trial-driver boot:
- `open_signing_link(entity: str, id: str, token: str) -> PageState` — navigates to `GET /sign/<entity>/<id>?token=<token>`.
- `sign_document(authority_confirmed: bool) -> ActionResult` — fills canvas with a synthetic signature stroke + POSTs `/api/sign/<entity>/<id>`.
- `decline_signing(reason: str) -> ActionResult` — emits the decline path; final status `declined`.
- `tamper_token() -> ActionResult` — mangles the current token's signature segment + retries the GET; harness records the resulting 403.

A fifth helper, `read_inbox()`, is added at the same opt-in point so the persona has a way to find the link without harness leakage.

Registration gate: at trial boot the driver checks `any(e.signable for e in app_spec.domain.entities)`. If false, none of the above tools are exposed and `trial.toml` semantics are unchanged.

**`src/dazzle/qa/signing_verifier.py`** — post-trial verification, callable as `verify_signing_outcome(transcript, runtime_db, app_spec) -> SigningOutcome`. Branches:
1. `detected = any "/sign/" path in transcript request log` — if false, returns `{detected: False}` and exits.
2. Read final row from runtime DB by id (the seeded row).
3. Infer `expected_outcome` from which tools the persona invoked (`sign_document` → `signed`, `decline_signing` → `declined`, `tamper_token` → `token_invalid`, etc.).
4. Assert `final_row.status == expected_status_for(expected_outcome)`. Mark functional pass/fail.
5. Assert audit row present in framework audit table for the entity+id+actor.
6. If a PDF was emitted, fetch it via the audit row's `signed_document` reference and call `pyhanko.sign.validation.validate_pdf_signature` against the project's cert chain. Capture summary.
7. Capture `latency_ms.get_sign` and `latency_ms.post_sign` from the request log (single values per scenario; a scenario only emits one of each).
8. Never raise — every failure becomes a structured finding in the returned dataclass.

### C. CLI wiring

`src/dazzle/cli/qa.py` (existing trial command):
1. Boot `dazzle serve` subprocess (existing).
2. **New:** if any signable entity exists, mint ephemeral cert into tmpdir and inject env vars into the subprocess.
3. **New:** if any signable entity exists, seed one row of each signable entity in `sent` status with a freshly-minted token. Write `{entity}/{id}/{token}` triples into a per-scenario mock inbox JSON file the persona reads via `read_inbox`.
4. Run trial (existing).
5. **New:** call `signing_verifier.verify_signing_outcome()`; merge result into the trial report under `signing_outcomes`.
6. Tear down tmpdir (cert + mock inbox) on exit (success or failure).

### D. Trial scenarios

Five `[[scenario]]` entries appended to each of `examples/contact_manager/trial.toml` and `examples/support_tickets/trial.toml`. `trial.toml` schema is **unchanged** — signing is detected from runtime behaviour, not from a TOML flag.

contact_manager personas (suggested):
- Priya, COO of a 40-person agency, reviewing an NDA before engaging your firm.

support_tickets personas (suggested):
- Devon, customer success manager acknowledging an SLA breach waiver.

The five outcomes per app:

| Outcome | Persona task instruction (paraphrased) |
|---|---|
| Happy path | Open the link in your inbox; read the agreement; sign if you accept |
| Declined | Open the link, read carefully; if anything looks off, decline |
| Token expired | Open the link from the inbox (harness pre-expires the token) |
| Validator-rejected | Open the link, sign (the validator hook will reject) |
| Already-signed | Sign normally, then re-open the same link from the inbox |

### E. Report extension

The existing trial report JSON gains a top-level `signing_outcomes` block per scenario:

```jsonc
{
  "signing_outcomes": {
    "detected": true,
    "expected_outcome_inferred": "signed",
    "functional": {
      "status": "pass",
      "final_row_status": "signed",
      "audit_row_present": true,
      "reason": null
    },
    "signature_integrity": {
      "valid": true,
      "embedded_timestamp": "2026-05-27T15:42:11Z",
      "pyhanko_summary": "PAdES B-T, cert chain validates against project CA"
    },
    "latency_ms": { "get_sign": 142, "post_sign": 891 }
  }
}
```

For `detected: false`, only the `detected` key is present.

## Data flow per scenario

See architecture diagram above. Key invariants:

- The persona is never told about token internals, status field names, or harness mechanics — only the user-facing instruction text.
- Verification runs against the **live runtime DB** (psycopg connection inherited from `dazzle serve`'s configured DSN), not against the persona's transcript.
- The transcript is only used to infer **what the persona intended** (`expected_outcome_inferred`), so failure modes grade correctly.
- For `token_expired` and `tamper_token` scenarios, the harness pre-mints the token with `exp = now - 1h`; the persona's behaviour is identical to the happy path.

## Error handling

| Failure | Behaviour |
|---|---|
| `dazzle signing init` fails to mint ephemeral cert | Abort scenario early; mark as `harness_error`. Stderr captured in report. |
| `dazzle serve` subprocess fails to boot | `harness_error`; subprocess log captured. Persona never dispatched. |
| Persona never visits a `/sign/` URL | `signing_outcomes: { detected: false }`. Scenario graded on UX/verdict only. |
| `pyhanko.validate_pdf_signature` raises | `signature_integrity: { valid: false, error: <repr> }`. Functional pass still possible if status transitioned. |
| DB row not found post-flow | `harness_error` — seed should have committed before persona started. |
| Audit row missing despite `status=signed` | Functional **fail** with `reason: audit_row_missing`. Catches framework audit regressions. |

The verifier never raises out — every failure becomes a structured finding so the report is always complete.

## Testing strategy

- **Unit (`tests/unit/`):**
  - `test_signing_tools_registration.py` — tools register iff `app_spec.has_signable_entity()`; absent otherwise.
  - `test_signing_verifier_branches.py` — each verification branch (status, audit, pyhanko, latency) with mocked DB and mocked pyhanko.

- **Integration (`tests/integration/test_qa_trial_signing.py`):**
  - Boot a minimal `signable` fixture app (under `fixtures/signing_validation/`).
  - Run a deterministic scripted persona (replay-mode driver, no live LLM) through each of the 5 outcomes.
  - Assert the report block matches expected shape per outcome.
  - No real LLM calls in CI.

- **E2E (`pytest -m e2e`, opt-in):**
  - One happy-path scenario per example app with a real LLM persona.
  - Gated behind `DAZZLE_E2E_SIGNING_TRIAL=1` so it doesn't burn tokens on every push.

- **Drift gate:**
  - Persona-tool catalogue + report schema documented in `docs/reference/document-signing.md` § "QA trial harness".
  - `tests/unit/test_docs_drift.py` style check that the tool list and schema stay in sync.

## Risks and open questions

1. **Ephemeral-cert cost.** Minting a fresh ECDSA cert chain per scenario adds ~200–500ms per scenario; 10 scenarios = 2–5s overhead. Acceptable. If it ever becomes a bottleneck: share one ephemeral CA per *run*, rotate per *scenario* only when the test specifically needs cert isolation.

2. **Mock-inbox seam.** New persona-facing infrastructure outside the four signing tools. If real notification delivery lands later, the seam stays — the harness swaps the mock inbox for capturing a real email.

3. **`_test_reject` marker on validator-rejected row.** The validator hook needs a way to know which row to reject without making the rejection generic. Cleanest: an env-driven "rejected ids" list the validator consults at request time. Decided in implementation, not the spec.

4. **PostgreSQL connection from verifier.** The verifier needs DB access while the `dazzle serve` subprocess holds its own connection pool. Reusing the same DSN from a fresh psycopg connection should be safe (read-only inspection) but worth confirming the pool doesn't lock anything that would block reads.

## Phasing

1. **Add `signable: true` to the two example apps** — DSL files, templates, `signing_validator:` hooks. Validates the primitive on two distinct domains. Ships as one PR.
2. **Build the harness extension** — `signing_tools.py`, `signing_verifier.py`, CLI wiring, ephemeral cert provisioning, mock inbox. Ships as a second PR.
3. **Author the 10 trial scenarios** — 5 in each app's `trial.toml`. Ships with phase 2 or as a follow-up depending on phase-2 PR size.
4. **Integration tests + drift gate** — `tests/integration/test_qa_trial_signing.py`, docs-drift check. Ships with phase 2.
5. **Opt-in E2E** — one happy-path run per app with a real LLM. Ships last, gated behind env var.

Total upstream effort: ~3-5 working days.

## Closing

The primitive exists; the QA substrate exists; the example apps exist. The work here is in stitching them: turn `signable: true` into something a Dazzle developer can adopt with confidence by demonstrating, in-tree, that the full lifecycle (mint → seed → persona-driven sign or decline → verify) is graded automatically across four lenses every time the trial harness runs.
