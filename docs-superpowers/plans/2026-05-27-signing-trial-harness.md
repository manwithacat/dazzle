# Signing Trial Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `dazzle qa trial` to grade `signable: true` flows on four axes (functional, UX, latency, PAdES integrity) by adding signing-aware persona tools, a post-trial verifier, and 10 trial scenarios across two example apps.

**Architecture:** Two example apps (`contact_manager`, `support_tickets`) gain a `signable: true` entity, a template, and a `signing_validator:` hook. The trial driver conditionally registers four persona-facing signing tools when any signable entity exists in the app_spec. After the persona ends, a verifier inspects the runtime DB, runs `pyhanko.validate_pdf_signature`, and merges a `signing_outcomes` block into the trial report.

**Tech Stack:** Python 3.12+, `pyhanko`, `fpdf2`, existing `dazzle.agent` mission framework, existing `dazzle.signing` primitives, psycopg, typer.

**Spec:** `docs/superpowers/specs/2026-05-27-signing-trial-harness-design.md`.

---

## File map

**Created:**
- `examples/contact_manager/dsl/signing.dsl` — `EngagementLetter` entity
- `examples/contact_manager/templates/letters/EngagementLetter/default.html.j2` — letter body
- `examples/contact_manager/app/signing/__init__.py`
- `examples/contact_manager/app/signing/validator.py` — `validate_engagement_letter` hook
- `examples/support_tickets/dsl/signing.dsl` — `SlaWaiver` entity
- `examples/support_tickets/templates/letters/SlaWaiver/default.html.j2`
- `examples/support_tickets/app/signing/__init__.py`
- `examples/support_tickets/app/signing/validator.py` — `validate_sla_waiver` hook
- `src/dazzle/qa/signing_tools.py` — five persona tools (`read_inbox`, `open_signing_link`, `sign_document`, `decline_signing`, `tamper_token`)
- `src/dazzle/qa/signing_verifier.py` — `SigningOutcome` dataclass + `verify_signing_outcome()`
- `src/dazzle/qa/signing_seed.py` — ephemeral cert minter + mock inbox writer
- `tests/unit/test_qa/test_signing_tools.py`
- `tests/unit/test_qa/test_signing_verifier.py`
- `tests/unit/test_qa/test_signing_seed.py`
- `tests/integration/test_qa_trial_signing.py`
- `fixtures/signing_validation/dazzle.toml`
- `fixtures/signing_validation/dsl/app.dsl` — minimal signable fixture for integration tests

**Modified:**
- `examples/contact_manager/dsl/app.dsl` — `use contact_manager.signing` import
- `examples/contact_manager/trial.toml` — append 5 scenarios
- `examples/support_tickets/dsl/app.dsl` — `use support_tickets.signing` import
- `examples/support_tickets/trial.toml` — append 5 scenarios
- `src/dazzle/core/ir/domain.py` — add `has_signable_entity()` helper on `AppSpec`
- `src/dazzle/agent/missions/trial.py` — accept optional `signing_tools` list, append to `Mission.tools`
- `src/dazzle/cli/qa.py` — wire ephemeral cert provisioning + seed + verifier
- `src/dazzle/qa/trial_report.py` — `SigningOutcome` block in report JSON + markdown rendering
- `docs/reference/document-signing.md` — new "QA trial harness" section

---

## Task 1 — Add `has_signable_entity()` helper to AppSpec

**Files:**
- Modify: `src/dazzle/core/ir/domain.py` — locate `class AppSpec`
- Test: `tests/unit/test_core/test_appspec_signable.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_core/test_appspec_signable.py
from dazzle.core.ir.domain import AppSpec, DomainSpec, EntitySpec


def _make_appspec(*entities: EntitySpec) -> AppSpec:
    return AppSpec(name="t", domain=DomainSpec(entities=list(entities)))


def test_has_signable_entity_true_when_one_signable():
    e = EntitySpec(name="Contract", label="Contract", fields=[], signable=True)
    assert _make_appspec(e).has_signable_entity() is True


def test_has_signable_entity_false_when_none_signable():
    e = EntitySpec(name="Contact", label="Contact", fields=[], signable=False)
    assert _make_appspec(e).has_signable_entity() is False


def test_has_signable_entity_false_when_empty():
    assert _make_appspec().has_signable_entity() is False
```

- [ ] **Step 2: Run test to verify it fails**

`pytest tests/unit/test_core/test_appspec_signable.py -v` — expected FAIL with `AttributeError: 'AppSpec' object has no attribute 'has_signable_entity'`.

- [ ] **Step 3: Add the helper**

In `src/dazzle/core/ir/domain.py`, in `class AppSpec`:

```python
    def has_signable_entity(self) -> bool:
        """True iff any entity in the app's domain has signable=True."""
        return any(e.signable for e in self.domain.entities)
```

- [ ] **Step 4: Run test to verify it passes**

`pytest tests/unit/test_core/test_appspec_signable.py -v` — expected 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_core/test_appspec_signable.py src/dazzle/core/ir/domain.py
git commit -m "Add AppSpec.has_signable_entity() helper for trial-harness gating"
```

---

## Task 2 — `EngagementLetter` entity in `contact_manager`

**Files:**
- Create: `examples/contact_manager/dsl/signing.dsl`
- Create: `examples/contact_manager/templates/letters/EngagementLetter/default.html.j2`
- Create: `examples/contact_manager/app/signing/__init__.py`
- Create: `examples/contact_manager/app/signing/validator.py`
- Modify: `examples/contact_manager/dsl/app.dsl` — add `use contact_manager.signing`
- Test: `tests/integration/test_examples_signable_validate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_examples_signable_validate.py
import subprocess
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _run_validate(project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["dazzle", "validate"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def test_contact_manager_validates_with_engagement_letter():
    result = _run_validate(EXAMPLES / "contact_manager")
    assert result.returncode == 0, result.stderr
    assert "EngagementLetter" in result.stdout + result.stderr
```

- [ ] **Step 2: Run** `pytest tests/integration/test_examples_signable_validate.py -v` — expected FAIL.

- [ ] **Step 3: Create the DSL file**

`examples/contact_manager/dsl/signing.dsl`:

```dsl
module contact_manager.signing

use contact_manager.core

entity EngagementLetter "Engagement Letter":
  intent: "Signed engagement letter / NDA between the firm and a contact"
  domain: crm
  patterns: signing

  id: uuid pk
  contact: ref Contact required
  party: str(200) required
  scope_summary: text required
  effective_date: date required
  signatory_name: str(200) required
  signatory_email: email required

  signable: true
  signing_validator: contact_manager.app.signing.validator.validate_engagement_letter
```

- [ ] **Step 4: Create the template**

`examples/contact_manager/templates/letters/EngagementLetter/default.html.j2`:

```html
<h1>Engagement Letter</h1>
<p>This Letter of Engagement is made on {{ row.effective_date }} between
<strong>{{ row.party }}</strong> ("Client") and the Firm.</p>

<h2>Scope of Engagement</h2>
<p>{{ row.scope_summary }}</p>

<h2>Authority to Sign</h2>
<p>The signatory ({{ row.signatory_name }}, <em>{{ row.signatory_email }}</em>)
confirms they have authority to bind the Client.</p>
```

- [ ] **Step 5: Create the validator hook**

`examples/contact_manager/app/signing/__init__.py`: empty file.

`examples/contact_manager/app/signing/validator.py`:

```python
"""Project-side signing_validator hook for EngagementLetter.

Reads DAZZLE_QA_SIGNING_REJECT_IDS (comma-separated row ids) and
raises SigningError when the row being signed is in the set. Used by
the trial harness to exercise the validator-rejected scenario.
"""

from __future__ import annotations

import os
from typing import Any

from dazzle.signing import SigningError


def _rejected_ids() -> set[str]:
    raw = os.environ.get("DAZZLE_QA_SIGNING_REJECT_IDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def validate_engagement_letter(*, entity: Any, row: Any) -> None:
    row_id = str(getattr(row, "id", ""))
    if row_id and row_id in _rejected_ids():
        raise SigningError(
            "Signatory lacks authority to sign on behalf of this party"
        )
```

- [ ] **Step 6: Wire the import**

In `examples/contact_manager/dsl/app.dsl`, after the module declaration, add:

```dsl
use contact_manager.signing
```

- [ ] **Step 7: Run** `pytest tests/integration/test_examples_signable_validate.py -v` — expected PASS.

- [ ] **Step 8: Commit**

```bash
git add examples/contact_manager tests/integration/test_examples_signable_validate.py
git commit -m "Add EngagementLetter signable entity to contact_manager"
```

---

## Task 3 — `SlaWaiver` entity in `support_tickets`

**Files:**
- Create: `examples/support_tickets/dsl/signing.dsl`
- Create: `examples/support_tickets/templates/letters/SlaWaiver/default.html.j2`
- Create: `examples/support_tickets/app/signing/__init__.py`
- Create: `examples/support_tickets/app/signing/validator.py`
- Modify: `examples/support_tickets/dsl/app.dsl` — add `use support_tickets.signing`
- Test: extend `tests/integration/test_examples_signable_validate.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_support_tickets_validates_with_sla_waiver():
    result = _run_validate(EXAMPLES / "support_tickets")
    assert result.returncode == 0, result.stderr
    assert "SlaWaiver" in result.stdout + result.stderr
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Create the DSL file**

`examples/support_tickets/dsl/signing.dsl`:

```dsl
module support_tickets.signing

use support_tickets.core

entity SlaWaiver "SLA Waiver":
  intent: "Signed acknowledgement of an SLA breach and waiver terms"
  domain: support
  patterns: signing

  id: uuid pk
  ticket: ref Ticket required
  breach_summary: text required
  waiver_terms: text required
  signatory_role: str(120) required
  signatory_name: str(200) required
  signatory_email: email required

  signable: true
  signing_validator: support_tickets.app.signing.validator.validate_sla_waiver
```

- [ ] **Step 4: Create the template**

`examples/support_tickets/templates/letters/SlaWaiver/default.html.j2`:

```html
<h1>SLA Breach Acknowledgement &amp; Waiver</h1>
<p>This waiver pertains to ticket <strong>{{ row.ticket }}</strong>.</p>

<h2>Breach Summary</h2>
<p>{{ row.breach_summary }}</p>

<h2>Waiver Terms</h2>
<p>{{ row.waiver_terms }}</p>

<h2>Acknowledgement</h2>
<p>I, {{ row.signatory_name }} ({{ row.signatory_role }},
<em>{{ row.signatory_email }}</em>), acknowledge the breach and accept
the waiver terms in full.</p>
```

- [ ] **Step 5: Create the validator hook**

`examples/support_tickets/app/signing/__init__.py`: empty.

`examples/support_tickets/app/signing/validator.py`:

```python
"""Project-side signing_validator hook for SlaWaiver."""

from __future__ import annotations

import os
from typing import Any

from dazzle.signing import SigningError


def _rejected_ids() -> set[str]:
    raw = os.environ.get("DAZZLE_QA_SIGNING_REJECT_IDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def validate_sla_waiver(*, entity: Any, row: Any) -> None:
    row_id = str(getattr(row, "id", ""))
    if row_id and row_id in _rejected_ids():
        raise SigningError(
            "Signatory not authorised to accept SLA waiver "
            "on behalf of this organisation"
        )
```

- [ ] **Step 6: Wire the import**

In `examples/support_tickets/dsl/app.dsl`:

```dsl
use support_tickets.signing
```

- [ ] **Step 7: Run** `pytest tests/integration/test_examples_signable_validate.py -v` — expected 2 passed.

- [ ] **Step 8: Commit**

```bash
git add examples/support_tickets tests/integration/test_examples_signable_validate.py
git commit -m "Add SlaWaiver signable entity to support_tickets"
```

---

## Task 4 — Minimal fixture app for integration tests

**Files:**
- Create: `fixtures/signing_validation/dazzle.toml`, `dsl/app.dsl`, `app/signing/validator.py`, template
- Test: `tests/unit/test_qa/test_fixture_signing_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa/test_fixture_signing_validation.py
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "signing_validation"


def test_fixture_dazzle_toml_exists():
    assert (FIXTURE / "dazzle.toml").is_file()


def test_fixture_has_signable_entity():
    dsl_text = (FIXTURE / "dsl" / "app.dsl").read_text()
    assert "signable: true" in dsl_text
    assert "entity TestDoc" in dsl_text
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Create fixture files**

`fixtures/signing_validation/dazzle.toml`:

```toml
[project]
name = "Signing Validation Fixture"

[signing]
project_name = "Test Co"
```

`fixtures/signing_validation/dsl/app.dsl`:

```dsl
module signing_validation

app signing_validation "Signing Validation Fixture"

persona admin "Administrator":
  default_workspace: docs

entity TestDoc "Test Document":
  id: uuid pk
  party: str(200) required
  body: text required
  signatory_email: email required

  signable: true
  signing_validator: app.signing.validator.validate_test_doc
```

`fixtures/signing_validation/app/signing/__init__.py`: empty.

`fixtures/signing_validation/app/signing/validator.py`:

```python
"""Test validator hook."""

from __future__ import annotations

import os
from typing import Any

from dazzle.signing import SigningError


def validate_test_doc(*, entity: Any, row: Any) -> None:
    row_id = str(getattr(row, "id", ""))
    rejected = {p.strip() for p in os.environ.get("DAZZLE_QA_SIGNING_REJECT_IDS", "").split(",") if p.strip()}
    if row_id and row_id in rejected:
        raise SigningError("Test rejection: id in reject set")
```

`fixtures/signing_validation/templates/letters/TestDoc/default.html.j2`:

```html
<h1>Test Document</h1>
<p>Party: {{ row.party }}</p>
<p>{{ row.body }}</p>
```

- [ ] **Step 4: Run** `pytest tests/unit/test_qa/test_fixture_signing_validation.py -v` — expected 2 passed.

- [ ] **Step 5: Commit**

```bash
git add fixtures/signing_validation tests/unit/test_qa/test_fixture_signing_validation.py
git commit -m "Add signing_validation fixture for trial-harness integration tests"
```

---

## Task 5 — `signing_seed.py`: ephemeral cert + mock inbox

**Files:**
- Create: `src/dazzle/qa/signing_seed.py`
- Test: `tests/unit/test_qa/test_signing_seed.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa/test_signing_seed.py
import json
from pathlib import Path

from dazzle.qa.signing_seed import (
    SeededDoc, SigningSeedContext, mint_ephemeral_cert_env, write_mock_inbox,
)


def test_mint_ephemeral_cert_env_sets_three_vars(tmp_path: Path):
    env = mint_ephemeral_cert_env(tmp_path, project_name="Test Co")
    assert env["SIGNING_CERT_PFX_B64"]
    assert env["SIGNING_CERT_PASSWORD"]
    assert env["SIGNING_TOKEN_SECRET"]


def test_write_mock_inbox_dumps_seeded_docs(tmp_path: Path):
    docs = [SeededDoc(
        entity="TestDoc", id="abc-123", token="tok-xyz",
        signing_url="http://localhost:3000/sign/TestDoc/abc-123?token=tok-xyz",
        signatory_email="a@b.com",
    )]
    inbox_path = write_mock_inbox(tmp_path, docs)
    payload = json.loads(inbox_path.read_text())
    assert payload[0]["entity"] == "TestDoc"
    assert payload[0]["signing_url"].startswith("http://")


def test_seed_context_is_a_dataclass(tmp_path: Path):
    ctx = SigningSeedContext(env={"X": "Y"}, inbox_path=tmp_path / "inbox.json", seeded_docs=[])
    assert ctx.env == {"X": "Y"}
```

- [ ] **Step 2: Run** — expected FAIL (module not found).

- [ ] **Step 3: Implement the module**

`src/dazzle/qa/signing_seed.py`:

```python
"""Ephemeral cert + mock inbox provisioning for `dazzle qa trial`
signing scenarios.

Three pieces of state are provisioned per-trial-run:
1. A signing cert chain (SIGNING_CERT_PFX_B64, SIGNING_CERT_PASSWORD).
2. A token secret (SIGNING_TOKEN_SECRET).
3. A mock inbox file containing seeded signing links the persona
   reads via the `read_inbox` tool.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dazzle.signing.cert import mint_project_cert


@dataclass(frozen=True)
class SeededDoc:
    entity: str
    id: str
    token: str
    signing_url: str
    signatory_email: str


@dataclass(frozen=True)
class SigningSeedContext:
    env: dict[str, str]
    inbox_path: Path
    seeded_docs: list[SeededDoc] = field(default_factory=list)


def mint_ephemeral_cert_env(tmpdir: Path, *, project_name: str) -> dict[str, str]:
    """Mint a one-shot ECDSA cert chain + token secret into ``tmpdir``."""
    pfx_b64, pfx_password = mint_project_cert(
        project_name=project_name,
        country="GB",
    )
    return {
        "SIGNING_CERT_PFX_B64": pfx_b64,
        "SIGNING_CERT_PASSWORD": pfx_password,
        "SIGNING_TOKEN_SECRET": secrets.token_urlsafe(48),
    }


def write_mock_inbox(tmpdir: Path, docs: list[SeededDoc]) -> Path:
    """Serialize ``docs`` to a JSON file the persona's read_inbox tool reads."""
    inbox_path = tmpdir / "mock_inbox.json"
    inbox_path.write_text(json.dumps([
        {
            "entity": d.entity, "id": d.id, "token": d.token,
            "signing_url": d.signing_url, "signatory_email": d.signatory_email,
        } for d in docs
    ], indent=2))
    return inbox_path
```

NOTE: Verify `mint_project_cert`'s actual signature via `grep -n "def mint_project_cert" src/dazzle/signing/cert.py` and adapt kwargs if they differ. Do not invent kwargs — read the source.

- [ ] **Step 4: Run** — expected 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/signing_seed.py tests/unit/test_qa/test_signing_seed.py
git commit -m "Add qa.signing_seed: ephemeral cert + mock inbox provisioning"
```

---

## Task 6 — `signing_tools.py`: the five persona-facing tools

**Files:**
- Create: `src/dazzle/qa/signing_tools.py`
- Test: `tests/unit/test_qa/test_signing_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa/test_signing_tools.py
from pathlib import Path
from dazzle.agent.core import AgentTool
from dazzle.qa.signing_seed import SeededDoc
from dazzle.qa.signing_tools import build_signing_tools


def test_returns_five_named_tools(tmp_path: Path):
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox, seeded_docs=[], action_sink={},
    )
    names = {t.name for t in tools}
    assert names == {
        "read_inbox", "open_signing_link", "sign_document",
        "decline_signing", "tamper_token",
    }
    for tool in tools:
        assert isinstance(tool, AgentTool)


def test_read_inbox_returns_seeded_docs(tmp_path: Path):
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        '[{"entity":"TestDoc","id":"abc","token":"tok",'
        '"signing_url":"http://x","signatory_email":"a@b.com"}]'
    )
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox, seeded_docs=[], action_sink=sink,
    )
    read_inbox = next(t for t in tools if t.name == "read_inbox")
    result = read_inbox.execute({})
    assert "TestDoc" in result
    assert "abc" in result
    assert sink["invoked"] == ["read_inbox"]
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement the module**

`src/dazzle/qa/signing_tools.py` — five tools, each built with `AgentTool(name=..., description=..., input_schema=..., execute=...)`. The `execute` callable receives the JSON args dict and returns a string. Each tool mutates `action_sink` to record:

1. `action_sink.setdefault("invoked", []).append(<name>)` on entry.
2. `action_sink.setdefault("requests", []).append({"method", "url", "status"})` for every HTTP call.
3. `action_sink["active_doc"] = <SeededDoc>` when `open_signing_link` succeeds.

Tool behaviour:

| Tool | Input schema | Body |
|---|---|---|
| `read_inbox` | `{}` | Read `inbox_path`; return numbered list of `entity/id` pairs + signing URLs. |
| `open_signing_link` | `{entity, id, token}` | `httpx.get(base_url + f"/sign/{entity}/{id}?token={token}")`. Set `active_doc`. |
| `sign_document` | `{authority_confirmed: bool}` | If not `authority_confirmed`, return refusal. Else `httpx.post(base_url + f"/api/sign/{active_doc.entity}/{active_doc.id}", json={"signature_data_url": "data:image/png;base64,iVBORw0KGgo=", "authority_confirmed": True})`. |
| `decline_signing` | `{reason: str}` | `httpx.post(base_url + f"/api/sign/{active_doc.entity}/{active_doc.id}/decline", json={"reason": reason})`. |
| `tamper_token` | `{}` | Mangle `active_doc.token` (e.g., `token[:-4] + "ZZZZ"`), retry the GET, record the resulting status. |

All HTTP timeouts: 30s for POST, 10s for GET. Wrap every httpx call in try/except `httpx.HTTPError` and return the error message as the tool's string result (the harness records the absent request; no exception escapes the tool boundary).

The module's public surface is one function:

```python
def build_signing_tools(
    *,
    base_url: str,
    inbox_path: Path,
    seeded_docs: list[SeededDoc],
    action_sink: dict[str, Any],
) -> list[AgentTool]:
    ...
```

NOTE: Inspect `class AgentTool` in `src/dazzle/agent/core.py` (line ~91) before writing. If the constructor uses `handler=` instead of `execute=`, adapt. Do not guess.

- [ ] **Step 4: Run** `pytest tests/unit/test_qa/test_signing_tools.py -v` — expected 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/signing_tools.py tests/unit/test_qa/test_signing_tools.py
git commit -m "Add qa.signing_tools: five persona-facing signing tools"
```

---

## Task 7 — `signing_verifier.py`: post-trial verification

**Files:**
- Create: `src/dazzle/qa/signing_verifier.py`
- Test: `tests/unit/test_qa/test_signing_verifier.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_qa/test_signing_verifier.py
from dataclasses import asdict
from unittest.mock import MagicMock

from dazzle.qa.signing_seed import SeededDoc
from dazzle.qa.signing_verifier import (
    SigningOutcome, infer_expected_outcome, verify_signing_outcome,
)


def test_infer_expected_outcome():
    assert infer_expected_outcome(["read_inbox", "open_signing_link", "sign_document"]) == "signed"
    assert infer_expected_outcome(["open_signing_link", "decline_signing"]) == "declined"
    assert infer_expected_outcome(["open_signing_link", "tamper_token"]) == "token_invalid"
    assert infer_expected_outcome(["read_inbox"]) == "not_engaged"
    assert infer_expected_outcome([]) == "not_engaged"


def test_returns_detected_false_when_no_sign_request():
    outcome = verify_signing_outcome(
        action_sink={"invoked": ["read_inbox"], "requests": []},
        seeded_docs=[], db_reader=MagicMock(), pdf_validator=MagicMock(),
    )
    assert outcome.detected is False
    assert outcome.expected_outcome_inferred == "not_engaged"


def test_grades_pass_when_status_matches():
    doc = SeededDoc("TestDoc", "abc", "tok", "http://x", "a@b.com")
    action_sink = {
        "invoked": ["read_inbox", "open_signing_link", "sign_document"],
        "requests": [
            {"method": "GET", "url": "http://x/sign/TestDoc/abc?token=tok", "status": 200},
            {"method": "POST", "url": "http://x/api/sign/TestDoc/abc", "status": 200},
        ],
        "active_doc": doc,
    }
    db_reader = MagicMock(return_value={
        "id": "abc", "status": "signed", "signed_at": "2026-05-27T15:00:00Z",
        "signer_ip": "127.0.0.1", "signed_document": "/files/abc.pdf",
    })
    pdf_validator = MagicMock(return_value={"valid": True, "summary": "OK"})
    outcome = verify_signing_outcome(
        action_sink=action_sink, seeded_docs=[doc],
        db_reader=db_reader, pdf_validator=pdf_validator,
    )
    assert outcome.detected is True
    assert outcome.functional["status"] == "pass"
    assert outcome.signature_integrity["valid"] is True


def test_grades_fail_when_status_mismatches():
    doc = SeededDoc("TestDoc", "abc", "tok", "http://x", "a@b.com")
    outcome = verify_signing_outcome(
        action_sink={
            "invoked": ["open_signing_link", "sign_document"],
            "requests": [{"method": "POST", "url": "http://x/api/sign/TestDoc/abc", "status": 500}],
            "active_doc": doc,
        },
        seeded_docs=[doc],
        db_reader=MagicMock(return_value={"id": "abc", "status": "viewed"}),
        pdf_validator=MagicMock(),
    )
    assert outcome.functional["status"] == "fail"


def test_outcome_serializes_to_dict():
    outcome = SigningOutcome(detected=False, expected_outcome_inferred="not_engaged")
    assert asdict(outcome)["detected"] is False
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement the verifier**

`src/dazzle/qa/signing_verifier.py`:

```python
"""Post-trial signing verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from dazzle.qa.signing_seed import SeededDoc

DbReader = Callable[[str, str], dict[str, Any] | None]
PdfValidator = Callable[[str], dict[str, Any]]

_EXPECTED_STATUS = {
    "signed": "signed",
    "declined": "declined",
    "token_invalid": "sent",
    "not_engaged": None,
}


@dataclass
class SigningOutcome:
    detected: bool = False
    expected_outcome_inferred: str = "not_engaged"
    functional: dict[str, Any] = field(default_factory=dict)
    signature_integrity: dict[str, Any] = field(default_factory=dict)
    latency_ms: dict[str, int] = field(default_factory=dict)


def infer_expected_outcome(invoked: list[str]) -> str:
    for action in invoked:
        if action == "sign_document":
            return "signed"
        if action == "decline_signing":
            return "declined"
        if action == "tamper_token":
            return "token_invalid"
    return "not_engaged"


def _compute_latency(requests: list[dict[str, Any]]) -> dict[str, int]:
    latency: dict[str, int] = {}
    for req in requests:
        url = req.get("url", "")
        elapsed = req.get("elapsed_ms")
        if elapsed is None:
            continue
        if "/api/sign/" in url:
            latency.setdefault("post_sign", int(elapsed))
        elif "/sign/" in url and req.get("method") == "GET":
            latency.setdefault("get_sign", int(elapsed))
    return latency


def _has_audit_fields(row: dict[str, Any]) -> bool:
    return bool(row.get("signer_ip")) and bool(row.get("signed_at"))


def verify_signing_outcome(
    *,
    action_sink: dict[str, Any],
    seeded_docs: list[SeededDoc],
    db_reader: DbReader,
    pdf_validator: PdfValidator,
) -> SigningOutcome:
    invoked: list[str] = action_sink.get("invoked", [])
    requests: list[dict[str, Any]] = action_sink.get("requests", [])
    expected = infer_expected_outcome(invoked)
    outcome = SigningOutcome(detected=False, expected_outcome_inferred=expected)

    if not any("/sign/" in r.get("url", "") for r in requests):
        return outcome

    outcome.detected = True
    outcome.latency_ms = _compute_latency(requests)

    active_doc: SeededDoc | None = action_sink.get("active_doc")
    if active_doc is None:
        outcome.functional = {
            "status": "harness_error",
            "reason": "no active_doc recorded by tools",
        }
        return outcome

    row = db_reader(active_doc.entity, active_doc.id)
    if row is None:
        outcome.functional = {
            "status": "harness_error",
            "reason": f"row {active_doc.entity}/{active_doc.id} not found post-flow",
        }
        return outcome

    expected_status = _EXPECTED_STATUS.get(expected)
    final_status = row.get("status")
    if expected_status is not None and final_status != expected_status:
        outcome.functional = {
            "status": "fail",
            "final_row_status": final_status,
            "audit_row_present": _has_audit_fields(row),
            "reason": f"expected status={expected_status} for outcome={expected}, got {final_status}",
        }
    else:
        outcome.functional = {
            "status": "pass",
            "final_row_status": final_status,
            "audit_row_present": _has_audit_fields(row),
            "reason": None,
        }

    pdf_path = row.get("signed_document")
    if pdf_path:
        try:
            outcome.signature_integrity = pdf_validator(pdf_path)
        except Exception as e:
            outcome.signature_integrity = {"valid": False, "error": repr(e)}

    return outcome
```

- [ ] **Step 4: Run** `pytest tests/unit/test_qa/test_signing_verifier.py -v` — expected 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/signing_verifier.py tests/unit/test_qa/test_signing_verifier.py
git commit -m "Add qa.signing_verifier: post-trial verification"
```

---

## Task 8 — Hook signing tools into the trial mission builder

**Files:**
- Modify: `src/dazzle/agent/missions/trial.py`
- Test: `tests/unit/test_qa/test_trial_mission_signing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa/test_trial_mission_signing.py
from dazzle.agent.core import AgentTool
from dazzle.agent.missions.trial import build_trial_mission


def test_baseline_tools_present():
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=None,
    )
    names = {t.name for t in mission.tools}
    assert "record_friction" in names
    assert "submit_verdict" in names


def test_signing_tools_appended_when_provided():
    fake = AgentTool(
        name="open_signing_link", description="x",
        input_schema={"type": "object", "properties": {}},
        execute=lambda _: "ok",
    )
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=[fake],
    )
    assert "open_signing_link" in {t.name for t in mission.tools}
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Modify `src/dazzle/agent/missions/trial.py`**

Change `build_trial_mission`'s signature to add `signing_tools: list[AgentTool] | None = None` (after `token_budget`). In the body, replace the `tools=[...]` argument to `Mission(...)` with:

```python
    base_tools = [
        _make_record_friction_tool(transcript_sink),
        _make_submit_verdict_tool(transcript_sink),
    ]
    if signing_tools:
        base_tools.extend(signing_tools)
```

…and pass `tools=base_tools` to `Mission(...)`.

- [ ] **Step 4: Run** `pytest tests/unit/test_qa/test_trial_mission_signing.py -v` — expected 2 passed.

- [ ] **Step 5: Run** `pytest tests/ -m "not e2e" -k "trial_mission or trial_report" -v` — expected all pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/agent/missions/trial.py tests/unit/test_qa/test_trial_mission_signing.py
git commit -m "Trial mission accepts optional signing_tools list"
```

---

## Task 9 — Extend `trial_report` with `SigningOutcome` block

**Files:**
- Modify: `src/dazzle/qa/trial_report.py`
- Test: `tests/unit/test_qa/test_trial_report_signing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa/test_trial_report_signing.py
from dazzle.qa.signing_verifier import SigningOutcome
from dazzle.qa.trial_report import build_trial_report, render_trial_report


def test_report_includes_signing_outcomes():
    outcome = SigningOutcome(
        detected=True, expected_outcome_inferred="signed",
        functional={"status": "pass", "final_row_status": "signed",
                    "audit_row_present": True, "reason": None},
        signature_integrity={"valid": True, "summary": "PAdES B-T OK"},
        latency_ms={"get_sign": 142, "post_sign": 891},
    )
    report = build_trial_report(
        scenario_name="happy", persona="Priya",
        verdict={"text": "fine", "recommend": True}, friction=[],
        signing_outcome=outcome,
    )
    assert report["signing_outcomes"]["detected"] is True
    assert report["signing_outcomes"]["functional"]["status"] == "pass"
    md = render_trial_report(report)
    assert "Signing Outcomes" in md
    assert "PAdES B-T OK" in md
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Modify `src/dazzle/qa/trial_report.py`**

Read the existing `build_trial_report` and `render_trial_report` signatures first. Add an optional kwarg `signing_outcome: SigningOutcome | None = None` to `build_trial_report`. When present, `report["signing_outcomes"] = asdict(signing_outcome)`.

In `render_trial_report`, after the existing sections, append a markdown block:

```python
    so = report.get("signing_outcomes")
    if so:
        parts.append("\n## Signing Outcomes\n")
        parts.append(f"- detected: {so['detected']}")
        parts.append(f"- expected outcome (inferred): {so['expected_outcome_inferred']}")
        if so.get("functional"):
            parts.append(f"- functional: {so['functional']}")
        if so.get("signature_integrity"):
            parts.append(f"- signature integrity: {so['signature_integrity']}")
        if so.get("latency_ms"):
            parts.append(f"- latency (ms): {so['latency_ms']}")
```

Add the imports at the top:

```python
from dataclasses import asdict
from dazzle.qa.signing_verifier import SigningOutcome
```

- [ ] **Step 4: Run** `pytest tests/unit/test_qa/test_trial_report_signing.py -v` — expected PASS.

- [ ] **Step 5: Run** `pytest tests/ -m "not e2e" -k "trial_report" -v` — expected all pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/qa/trial_report.py tests/unit/test_qa/test_trial_report_signing.py
git commit -m "Trial report: include SigningOutcome block + markdown render"
```

---

## Task 10 — CLI wiring: ephemeral cert provisioning + seed + verifier

**Files:**
- Modify: `src/dazzle/cli/qa.py`
- Test: `tests/unit/test_qa/test_cli_signing_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa/test_cli_signing_wiring.py
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.cli.qa import _provision_signing_env, _seed_signable_rows


def test_provision_returns_context_when_signable(tmp_path: Path):
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = True
    with patch("dazzle.cli.qa.mint_ephemeral_cert_env") as mint:
        mint.return_value = {
            "SIGNING_CERT_PFX_B64": "x", "SIGNING_CERT_PASSWORD": "y",
            "SIGNING_TOKEN_SECRET": "z",
        }
        ctx = _provision_signing_env(app_spec, tmp_path, project_name="Test")
    assert ctx is not None
    assert ctx.env["SIGNING_TOKEN_SECRET"] == "z"


def test_provision_returns_none_when_no_signable(tmp_path: Path):
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = False
    assert _provision_signing_env(app_spec, tmp_path, project_name="Test") is None


def test_seed_creates_one_doc_per_signable_entity():
    entity_a = MagicMock(signable=True)
    entity_a.name = "EngagementLetter"
    entity_b = MagicMock(signable=False)
    app_spec = MagicMock()
    app_spec.domain.entities = [entity_a, entity_b]
    with patch("dazzle.cli.qa.mint_token", return_value="tok-abc"), \
         patch("dazzle.cli.qa._insert_seed_row", return_value="row-id-1"), \
         patch.dict(os.environ, {"SIGNING_TOKEN_SECRET": "s"}):
        docs = _seed_signable_rows(
            app_spec=app_spec, base_url="http://localhost:3000",
            signatory_email="a@b.com",
        )
    assert len(docs) == 1
    assert docs[0].entity == "EngagementLetter"
    assert docs[0].token == "tok-abc"
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Add helpers to `src/dazzle/cli/qa.py`**

Near the existing imports add:

```python
import shutil
import tempfile
from typing import Callable

from dazzle.qa.signing_seed import (
    SeededDoc, SigningSeedContext,
    mint_ephemeral_cert_env, write_mock_inbox,
)
from dazzle.qa.signing_tools import build_signing_tools
from dazzle.qa.signing_verifier import SigningOutcome, verify_signing_outcome
from dazzle.signing.tokens import mint_token
```

Add module-level helpers (above `qa_trial`):

```python
def _provision_signing_env(
    app_spec: Any, tmp_root: Path, *, project_name: str,
) -> SigningSeedContext | None:
    if not app_spec.has_signable_entity():
        return None
    env = mint_ephemeral_cert_env(tmp_root, project_name=project_name)
    inbox_path = tmp_root / "mock_inbox.json"
    inbox_path.write_text("[]")
    return SigningSeedContext(env=env, inbox_path=inbox_path, seeded_docs=[])


def _insert_seed_row(*, entity_name: str, base_url: str, signatory_email: str) -> str:
    """Insert one row of ``entity_name`` in `sent` status via the runtime API."""
    import httpx
    payload = {
        "party": "Trial Counterparty Ltd",
        "scope_summary": "Trial-harness seed row.",
        "effective_date": "2026-05-27",
        "signatory_name": "Trial Signatory",
        "signatory_email": signatory_email,
        "status": "sent",
    }
    resp = httpx.post(f"{base_url}/api/{entity_name}", json=payload, timeout=10.0)
    resp.raise_for_status()
    return resp.json()["id"]


def _seed_signable_rows(
    *, app_spec: Any, base_url: str, signatory_email: str,
) -> list[SeededDoc]:
    docs: list[SeededDoc] = []
    for entity in app_spec.domain.entities:
        if not getattr(entity, "signable", False):
            continue
        row_id = _insert_seed_row(
            entity_name=entity.name, base_url=base_url,
            signatory_email=signatory_email,
        )
        token = mint_token(record_id=row_id, email=signatory_email)
        docs.append(SeededDoc(
            entity=entity.name, id=row_id, token=token,
            signing_url=f"{base_url}/sign/{entity.name}/{row_id}?token={token}",
            signatory_email=signatory_email,
        ))
    return docs


def _build_db_reader(project_dir: Path) -> Callable[[str, str], dict | None]:
    import psycopg
    import psycopg.rows
    # Reuse the same DSN-resolution path the existing seed helper uses.
    # Look around _seed_demo_data_for_trial in this file (line ~87).
    dsn = os.environ.get("DATABASE_URL", "")
    def _read(entity: str, row_id: str) -> dict | None:
        with psycopg.connect(dsn) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(f'SELECT * FROM "{entity}" WHERE id = %s', (row_id,))
                return cur.fetchone()
    return _read


def _pyhanko_validator(pdf_path: str) -> dict:
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator.context import ValidationContext
    from pyhanko.pdf_utils.reader import PdfFileReader
    with open(pdf_path, "rb") as fh:
        reader = PdfFileReader(fh)
        sig = reader.embedded_signatures[0]
        status = validate_pdf_signature(sig, ValidationContext())
    return {
        "valid": bool(status.intact and status.valid),
        "embedded_timestamp": (
            str(status.timestamp_validity) if status.timestamp_validity else None
        ),
        "summary": status.pretty_print_details(),
    }
```

- [ ] **Step 4: Wire into the trial flow**

In the existing `qa_trial` function body, AFTER the project dir + appspec are loaded and BEFORE the existing serve subprocess boot, add:

```python
    tmp_root = Path(tempfile.mkdtemp(prefix="dazzle-trial-signing-"))
    seed_ctx = _provision_signing_env(
        appspec, tmp_root,
        project_name=manifest.name or project_dir.name,
    )
    if seed_ctx is not None:
        os.environ.update(seed_ctx.env)
```

(Wrap the rest of the trial body in `try` / `finally: shutil.rmtree(tmp_root, ignore_errors=True)`.)

AFTER the serve subprocess is up and the existing demo-data seed runs, add:

```python
    signing_tools: list = []
    signing_action_sink: dict = {}
    if seed_ctx is not None:
        seeded = _seed_signable_rows(
            app_spec=appspec, base_url=site_url,
            signatory_email="trial-signatory@example.com",
        )
        seed_ctx = SigningSeedContext(
            env=seed_ctx.env, inbox_path=seed_ctx.inbox_path,
            seeded_docs=seeded,
        )
        write_mock_inbox(tmp_root, seeded)
        signing_tools = build_signing_tools(
            base_url=site_url, inbox_path=seed_ctx.inbox_path,
            seeded_docs=seeded, action_sink=signing_action_sink,
        )
```

In the `build_trial_mission(...)` call, add `signing_tools=signing_tools or None`.

After the agent finishes and before `build_trial_report(...)`:

```python
    signing_outcome: SigningOutcome | None = None
    if seed_ctx is not None and signing_action_sink.get("invoked"):
        db_reader = _build_db_reader(project_dir)
        signing_outcome = verify_signing_outcome(
            action_sink=signing_action_sink,
            seeded_docs=seed_ctx.seeded_docs,
            db_reader=db_reader, pdf_validator=_pyhanko_validator,
        )
```

In `build_trial_report(...)`, add `signing_outcome=signing_outcome`.

- [ ] **Step 5: Run** `pytest tests/unit/test_qa/test_cli_signing_wiring.py -v` — expected 3 passed.

- [ ] **Step 6: Run** `pytest tests/ -m "not e2e" -k "qa or trial" -v` — expected all pass.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/cli/qa.py tests/unit/test_qa/test_cli_signing_wiring.py
git commit -m "Wire ephemeral cert + seed + verifier into dazzle qa trial"
```

---

## Task 11 — Integration test: scripted persona end-to-end

**Files:**
- Create: `tests/integration/test_qa_trial_signing.py`
- Create: `tests/integration/helpers/signable_runner.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_qa_trial_signing.py
"""End-to-end signing trial using fixtures/signing_validation + scripted persona."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.qa.signing_tools import build_signing_tools
from dazzle.qa.signing_verifier import verify_signing_outcome

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "signing_validation"


@pytest.mark.integration
def test_happy_path(running_signable_app):
    sink: dict = {}
    tools = build_signing_tools(
        base_url=running_signable_app.base_url,
        inbox_path=running_signable_app.inbox_path,
        seeded_docs=running_signable_app.seeded_docs,
        action_sink=sink,
    )
    by_name = {t.name: t for t in tools}
    by_name["read_inbox"].execute({})
    doc = running_signable_app.seeded_docs[0]
    by_name["open_signing_link"].execute({"entity": doc.entity, "id": doc.id, "token": doc.token})
    by_name["sign_document"].execute({"authority_confirmed": True})

    outcome = verify_signing_outcome(
        action_sink=sink, seeded_docs=running_signable_app.seeded_docs,
        db_reader=running_signable_app.db_reader,
        pdf_validator=running_signable_app.pdf_validator,
    )
    assert outcome.detected is True
    assert outcome.expected_outcome_inferred == "signed"
    assert outcome.functional["status"] == "pass"
    assert outcome.functional["final_row_status"] == "signed"


@pytest.mark.integration
def test_declined(running_signable_app):
    sink: dict = {}
    tools = build_signing_tools(
        base_url=running_signable_app.base_url,
        inbox_path=running_signable_app.inbox_path,
        seeded_docs=running_signable_app.seeded_docs,
        action_sink=sink,
    )
    by_name = {t.name: t for t in tools}
    doc = running_signable_app.seeded_docs[0]
    by_name["open_signing_link"].execute({"entity": doc.entity, "id": doc.id, "token": doc.token})
    by_name["decline_signing"].execute({"reason": "Out of scope"})
    outcome = verify_signing_outcome(
        action_sink=sink, seeded_docs=running_signable_app.seeded_docs,
        db_reader=running_signable_app.db_reader,
        pdf_validator=running_signable_app.pdf_validator,
    )
    assert outcome.expected_outcome_inferred == "declined"
    assert outcome.functional["final_row_status"] == "declined"


@pytest.mark.integration
def test_token_tampered(running_signable_app):
    sink: dict = {}
    tools = build_signing_tools(
        base_url=running_signable_app.base_url,
        inbox_path=running_signable_app.inbox_path,
        seeded_docs=running_signable_app.seeded_docs,
        action_sink=sink,
    )
    by_name = {t.name: t for t in tools}
    doc = running_signable_app.seeded_docs[0]
    by_name["open_signing_link"].execute({"entity": doc.entity, "id": doc.id, "token": doc.token})
    by_name["tamper_token"].execute({})
    outcome = verify_signing_outcome(
        action_sink=sink, seeded_docs=running_signable_app.seeded_docs,
        db_reader=running_signable_app.db_reader,
        pdf_validator=running_signable_app.pdf_validator,
    )
    assert outcome.expected_outcome_inferred == "token_invalid"
    assert outcome.functional["final_row_status"] == "sent"


@pytest.mark.integration
def test_validator_rejected(running_signable_app_with_reject):
    app = running_signable_app_with_reject
    sink: dict = {}
    tools = build_signing_tools(
        base_url=app.base_url, inbox_path=app.inbox_path,
        seeded_docs=app.seeded_docs, action_sink=sink,
    )
    by_name = {t.name: t for t in tools}
    doc = app.seeded_docs[0]
    by_name["open_signing_link"].execute({"entity": doc.entity, "id": doc.id, "token": doc.token})
    by_name["sign_document"].execute({"authority_confirmed": True})
    outcome = verify_signing_outcome(
        action_sink=sink, seeded_docs=app.seeded_docs,
        db_reader=app.db_reader, pdf_validator=app.pdf_validator,
    )
    assert outcome.expected_outcome_inferred == "signed"
    assert outcome.functional["final_row_status"] == "viewed"
    assert outcome.functional["status"] == "fail"


@pytest.mark.integration
def test_already_signed(running_signable_app):
    sink: dict = {}
    tools = build_signing_tools(
        base_url=running_signable_app.base_url,
        inbox_path=running_signable_app.inbox_path,
        seeded_docs=running_signable_app.seeded_docs,
        action_sink=sink,
    )
    by_name = {t.name: t for t in tools}
    doc = running_signable_app.seeded_docs[0]
    by_name["open_signing_link"].execute({"entity": doc.entity, "id": doc.id, "token": doc.token})
    by_name["sign_document"].execute({"authority_confirmed": True})
    by_name["open_signing_link"].execute({"entity": doc.entity, "id": doc.id, "token": doc.token})
    by_name["sign_document"].execute({"authority_confirmed": True})
    outcome = verify_signing_outcome(
        action_sink=sink, seeded_docs=running_signable_app.seeded_docs,
        db_reader=running_signable_app.db_reader,
        pdf_validator=running_signable_app.pdf_validator,
    )
    assert outcome.functional["final_row_status"] == "signed"
    assert outcome.functional["status"] == "pass"


@pytest.fixture
def running_signable_app(tmp_path: Path):
    from tests.integration.helpers.signable_runner import boot_fixture_app
    yield from boot_fixture_app(FIXTURE, tmp_path, reject_seeded=False)


@pytest.fixture
def running_signable_app_with_reject(tmp_path: Path):
    from tests.integration.helpers.signable_runner import boot_fixture_app
    yield from boot_fixture_app(FIXTURE, tmp_path, reject_seeded=True)
```

- [ ] **Step 2: Add the helper module**

`tests/integration/helpers/__init__.py`: empty.

`tests/integration/helpers/signable_runner.py`:

```python
"""Boot fixtures/signing_validation with signing env wired."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections import namedtuple
from contextlib import closing
from pathlib import Path
from typing import Iterator

import httpx
import psycopg
import psycopg.rows

from dazzle.qa.signing_seed import (
    SeededDoc, mint_ephemeral_cert_env, write_mock_inbox,
)
from dazzle.signing.tokens import mint_token

RunningApp = namedtuple(
    "RunningApp",
    ["base_url", "seeded_docs", "db_reader", "pdf_validator", "inbox_path"],
)


def _free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"App at {url} did not become ready in {timeout}s")


def boot_fixture_app(
    fixture_dir: Path, tmp_path: Path, *, reject_seeded: bool,
) -> Iterator[RunningApp]:
    port = _free_port()
    base_url = f"http://localhost:{port}"

    env = os.environ.copy()
    env.update(mint_ephemeral_cert_env(tmp_path, project_name="Test Co"))

    proc = subprocess.Popen(
        ["dazzle", "serve", "--local", "--port", str(port)],
        cwd=fixture_dir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        _wait_for(f"{base_url}/health")
        payload = {
            "party": "Trial Counterparty",
            "body": "Test body",
            "signatory_email": "trial@example.com",
            "status": "sent",
        }
        r = httpx.post(f"{base_url}/api/TestDoc", json=payload, timeout=10.0)
        r.raise_for_status()
        row_id = r.json()["id"]

        if reject_seeded:
            proc.terminate(); proc.wait(timeout=10)
            env["DAZZLE_QA_SIGNING_REJECT_IDS"] = row_id
            proc = subprocess.Popen(
                ["dazzle", "serve", "--local", "--port", str(port)],
                cwd=fixture_dir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            _wait_for(f"{base_url}/health")

        token = mint_token(record_id=row_id, email="trial@example.com")
        seeded = [SeededDoc(
            entity="TestDoc", id=row_id, token=token,
            signing_url=f"{base_url}/sign/TestDoc/{row_id}?token={token}",
            signatory_email="trial@example.com",
        )]
        inbox_path = write_mock_inbox(tmp_path, seeded)

        dsn = env.get("DATABASE_URL", "")

        def _db_reader(entity: str, rid: str) -> dict | None:
            with psycopg.connect(dsn) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(f'SELECT * FROM "{entity}" WHERE id = %s', (rid,))
                return cur.fetchone()

        def _pdf_validator(path: str) -> dict:
            # Integration tests use presence-only check; unit tests cover pyhanko branch.
            return {"valid": Path(path).exists(), "summary": "presence-only check"}

        yield RunningApp(
            base_url=base_url, seeded_docs=seeded,
            db_reader=_db_reader, pdf_validator=_pdf_validator,
            inbox_path=inbox_path,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 3: Register the `integration` marker** in `pyproject.toml` (if not already):

```toml
[tool.pytest.ini_options]
markers = [
    "integration: long-running tests that boot a real dazzle serve subprocess",
]
```

- [ ] **Step 4: Run** `pytest tests/integration/test_qa_trial_signing.py -v -m integration` — expected 5 passed (slow).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_qa_trial_signing.py tests/integration/helpers
git commit -m "Add integration tests for signing trial harness (5 scripted scenarios)"
```

---

## Task 12 — Trial scenarios for `contact_manager`

**Files:**
- Modify: `examples/contact_manager/trial.toml`

- [ ] **Step 1: Append 5 scenarios** to `examples/contact_manager/trial.toml`. Each scenario follows the existing `[[scenario]]` schema (name, login_persona, time_budget_seconds, max_steps, user_identity, business_context, tasks, stop_when). Personas: COO Priya (happy / declined / token_expired / already_signed), Office Manager Devon (validator_rejected). The persona's `tasks` instruct them toward the relevant outcome without mentioning harness mechanics.

Concrete scenarios (paste verbatim):

```toml
[[scenario]]
name = "engagement_letter_happy_path"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Priya, COO of a 40-person agency. The firm has sent you an
engagement letter you're expected to sign before work begins.
"""
business_context = """
Your firm is engaging Consulting Co for a Q4 brand refresh. You've
verbally agreed the scope. The letter should match what you discussed.
"""
tasks = [
    "Read your inbox to find the engagement letter awaiting signature.",
    "Open the signing link.",
    "Read the document. If it matches what you expected, sign it.",
]
stop_when = """
Stop after signing or declining. Call submit_verdict with your verdict.
"""


[[scenario]]
name = "engagement_letter_declined"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Priya, COO of a 40-person agency. You've received an engagement
letter you weren't expecting and the scope reads broader than agreed.
"""
business_context = """
Your finance lead has flagged scope items that were explicitly out of
phase 1. You're going to read the document and decline.
"""
tasks = [
    "Read your inbox to find the engagement letter awaiting signature.",
    "Open the signing link.",
    "Read the document. If the scope looks off, decline with a clear reason.",
]
stop_when = """
Stop after declining. Call submit_verdict with your verdict.
"""


[[scenario]]
name = "engagement_letter_token_expired"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Priya, COO. You meant to sign the engagement letter yesterday
but got pulled into a board prep. You're opening the link now.
"""
business_context = """
The link was sent yesterday. You're aware these links sometimes expire.
"""
tasks = [
    "Read your inbox to find the engagement letter.",
    "Open the signing link.",
    "If the link is expired, note what the page tells you and call submit_verdict.",
]
stop_when = """
Call submit_verdict describing the expired-link experience.
"""


[[scenario]]
name = "engagement_letter_validator_rejected"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Devon, Office Manager. The Engagement Letter was sent to you
by mistake — the firm should have sent it to your COO. You're going to
try to sign it anyway because you'd rather not delay the project.
"""
business_context = """
You don't have authority to bind your firm to engagement letters.
"""
tasks = [
    "Read your inbox to find the engagement letter awaiting signature.",
    "Open the signing link.",
    "Sign it.",
]
stop_when = """
Call submit_verdict describing whether the system caught the
authority gap.
"""


[[scenario]]
name = "engagement_letter_already_signed"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Priya, COO. You signed the engagement letter five minutes ago
and now you're worried the click didn't go through — your network was
flaky. You're opening the link again to double-check.
"""
business_context = """
You're not trying to sign twice; you're trying to confirm the first
signature actually worked.
"""
tasks = [
    "Read your inbox to find the engagement letter.",
    "Open the signing link.",
    "Try to sign it if the first signature didn't go through.",
]
stop_when = """
Call submit_verdict describing whether the system made it clear the
document had already been signed.
"""
```

- [ ] **Step 2: Run** `cd examples/contact_manager && dazzle validate` — expected pass.

- [ ] **Step 3: Commit**

```bash
git add examples/contact_manager/trial.toml
git commit -m "Add 5 signing trial scenarios to contact_manager"
```

---

## Task 13 — Trial scenarios for `support_tickets`

**Files:**
- Modify: `examples/support_tickets/trial.toml`

- [ ] **Step 1: Append 5 scenarios** mirroring Task 12's structure but with Devon (customer success manager) as the happy/declined/token_expired/already_signed signatory and Sam (on-call engineer) as the validator_rejected signatory. Domain: SLA waiver after a P1 breach.

Concrete scenarios (paste verbatim):

```toml
[[scenario]]
name = "sla_waiver_happy_path"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Devon, customer success manager at a B2B SaaS company. Your
support vendor missed an SLA on a P1 ticket last Thursday. They've
sent you a waiver with what looks like fair remediation terms.
"""
business_context = """
P1 SLA was 4 hours; resolution took 9 hours. The waiver offers a
service credit + a written postmortem within 10 business days.
"""
tasks = [
    "Read your inbox to find the SLA waiver awaiting signature.",
    "Open the signing link.",
    "Read the breach summary and waiver terms. If reasonable, sign.",
]
stop_when = """
Stop after signing or declining. Call submit_verdict with a verdict.
"""


[[scenario]]
name = "sla_waiver_declined"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Devon. The waiver terms your vendor sent are insulting —
5% credit for a 9-hour outage that lost you two customers.
"""
business_context = """
You'll escalate to your account exec but want this waiver formally
declined so it doesn't sit as accepted.
"""
tasks = [
    "Read your inbox to find the SLA waiver awaiting signature.",
    "Open the signing link.",
    "Read the terms. If inadequate, decline with a clear reason.",
]
stop_when = """
Stop after declining. Call submit_verdict with your verdict.
"""


[[scenario]]
name = "sla_waiver_token_expired"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Devon. The waiver email is from two weeks ago and you only
just got to it. You're going to open the link.
"""
business_context = """
You're aware these links sometimes have time limits.
"""
tasks = [
    "Read your inbox to find the SLA waiver.",
    "Open the signing link.",
    "If expired, note what the page says and submit_verdict.",
]
stop_when = """
Call submit_verdict describing the expired-link experience.
"""


[[scenario]]
name = "sla_waiver_validator_rejected"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Sam, an on-call engineer. The SLA waiver was sent to you
because you were on the ticket but you don't have authority to accept
waiver terms.
"""
business_context = """
You don't have authority to bind your team to waiver terms.
"""
tasks = [
    "Read your inbox to find the SLA waiver awaiting signature.",
    "Open the signing link.",
    "Sign it.",
]
stop_when = """
Call submit_verdict describing whether the system caught the
authority gap.
"""


[[scenario]]
name = "sla_waiver_already_signed"
login_persona = "user"
time_budget_seconds = 400
max_steps = 25
user_identity = """
You are Devon. You signed the waiver an hour ago and want a copy of
the signed PDF for your CRM attachment.
"""
business_context = """
You're not trying to re-sign; you want the signed PDF.
"""
tasks = [
    "Read your inbox to find the SLA waiver.",
    "Open the signing link.",
    "If the system offers the signed PDF, note that.",
]
stop_when = """
Call submit_verdict describing the re-open experience.
"""
```

- [ ] **Step 2: Run** `cd examples/support_tickets && dazzle validate` — expected pass.

- [ ] **Step 3: Commit**

```bash
git add examples/support_tickets/trial.toml
git commit -m "Add 5 signing trial scenarios to support_tickets"
```

---

## Task 14 — Docs + drift gate + quality gate

**Files:**
- Modify: `docs/reference/document-signing.md`
- Modify: `CHANGELOG.md`
- Create: `tests/unit/test_qa/test_signing_docs_drift.py`

- [ ] **Step 1: Write the failing drift test**

```python
# tests/unit/test_qa/test_signing_docs_drift.py
from pathlib import Path

from dazzle.qa.signing_tools import build_signing_tools

DOCS = Path(__file__).resolve().parents[3] / "docs" / "reference" / "document-signing.md"


def test_docs_list_all_persona_tools():
    tools = build_signing_tools(
        base_url="x", inbox_path=Path("/tmp/i.json"),
        seeded_docs=[], action_sink={},
    )
    docs_text = DOCS.read_text()
    for tool in tools:
        assert f"`{tool.name}`" in docs_text


def test_docs_include_signing_outcomes_keys():
    docs_text = DOCS.read_text()
    for key in [
        "detected", "expected_outcome_inferred", "functional",
        "signature_integrity", "latency_ms",
    ]:
        assert key in docs_text
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Append the harness section to `docs/reference/document-signing.md`**:

```markdown
## QA trial harness

`dazzle qa trial` automatically grades signing flows when the app
contains any `signable: true` entity. Five persona-facing tools are
registered on top of the usual trial tool set:

- `read_inbox` — list documents awaiting signature.
- `open_signing_link` — open a link by entity + id + token.
- `sign_document` — submit the signature (requires
  `authority_confirmed: true`).
- `decline_signing` — decline with a reason.
- `tamper_token` — retry the GET with a mangled token.

After the persona ends, the harness inspects the runtime DB, runs
pyhanko on the signed PDF if one was produced, and merges a
`signing_outcomes` block into the trial report. The block has these
keys: `detected`, `expected_outcome_inferred`, `functional`,
`signature_integrity`, `latency_ms`.

### Provisioning

The harness mints an ephemeral ECDSA cert chain into a per-run tmpdir
and injects `SIGNING_CERT_PFX_B64`, `SIGNING_CERT_PASSWORD`,
`SIGNING_TOKEN_SECRET` into the `dazzle serve` subprocess. Torn down
on exit.

### Validator-rejected scenarios

Set `DAZZLE_QA_SIGNING_REJECT_IDS=<id>` and the project's validator
hook will consult that list. Both `contact_manager` and
`support_tickets` ship validator hooks that follow this convention.

### Reference scenarios

`examples/contact_manager/trial.toml` and
`examples/support_tickets/trial.toml` each declare 5 signing scenarios
(happy path, declined, token expired, validator-rejected,
already-signed).
```

- [ ] **Step 4: Run** `pytest tests/unit/test_qa/test_signing_docs_drift.py -v` — expected 2 passed.

- [ ] **Step 5: Add CHANGELOG entry**

In `CHANGELOG.md`, under the next unreleased / patch section:

```markdown
### Added
- `dazzle qa trial` signing harness. Five persona-facing tools auto-register
  when the app has any `signable: true` entity. Post-trial verifier grades
  functional correctness, PAdES signature integrity, and per-route latency.
- `EngagementLetter` (contact_manager) + `SlaWaiver` (support_tickets)
  example signable entities, each with 5 trial scenarios covering happy
  path, declined, token-expired, validator-rejected, already-signed.

### Agent Guidance
- When adding a new persona-facing tool to the signing harness, update
  `docs/reference/document-signing.md` § "QA trial harness".
  `tests/unit/test_qa/test_signing_docs_drift.py` enforces parity.
```

- [ ] **Step 6: Run the full quality gate**

```
pytest tests/ -m "not e2e" -q
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add docs/reference/document-signing.md CHANGELOG.md tests/unit/test_qa/test_signing_docs_drift.py
git commit -m "Document signing trial harness + drift gate"
```

---

## Task 15 — Opt-in E2E run with real LLM

**Files:**
- Create: `tests/e2e/test_signing_trial_live.py`

- [ ] **Step 1: Write the E2E test**

```python
# tests/e2e/test_signing_trial_live.py
"""Live LLM persona signing trial. Opt-in: DAZZLE_E2E_SIGNING_TRIAL=1."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("DAZZLE_E2E_SIGNING_TRIAL") != "1",
    reason="Opt-in: set DAZZLE_E2E_SIGNING_TRIAL=1 to enable",
)
@pytest.mark.parametrize("app", ["contact_manager", "support_tickets"])
def test_happy_path_with_live_llm(app: str, tmp_path: Path):
    project_dir = EXAMPLES / app
    scenario = (
        "engagement_letter_happy_path" if app == "contact_manager"
        else "sla_waiver_happy_path"
    )
    output = tmp_path / f"trial-{app}.json"
    result = subprocess.run(
        ["dazzle", "qa", "trial",
         "--scenario", scenario,
         "--output", str(output),
         "--format", "json"],
        cwd=project_dir, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    so = report["signing_outcomes"]
    assert so["detected"] is True
    assert so["expected_outcome_inferred"] == "signed"
    assert so["functional"]["status"] == "pass"
```

- [ ] **Step 2: Run locally (opt-in)**

```
DAZZLE_E2E_SIGNING_TRIAL=1 pytest tests/e2e/test_signing_trial_live.py -v
```

Expected: 2 passed (slow, burns tokens). Do not run in CI by default.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_signing_trial_live.py
git commit -m "Add opt-in E2E live-LLM signing trial smoke"
```

---

## Final task — Version bump and ship

- [ ] **Step 1: Bump version**

Invoke `/bump minor` (this is a minor bump — two example apps gain a feature; framework gains a QA tool surface).

- [ ] **Step 2: Verify clean worktree**

```
git status
```

Expected: clean. If files like `dist/`, `pyproject.toml`, `ROADMAP.md`, `core.toml`, `CHANGELOG.md` are dirty after the bump, commit them as part of the bump.

- [ ] **Step 3: Ship**

Invoke `/ship`. The skill handles push + tag.

---

## Self-review notes

**Spec coverage:** Every component in the spec maps to at least one task — DSL additions in two example apps (Tasks 2, 3), `signing_tools.py` (6), `signing_verifier.py` (7), CLI wiring (10), trial scenarios (12, 13), report extension (9), integration tests (11), opt-in E2E (15), docs + drift gate (14).

**Type consistency:** `SeededDoc`, `SigningSeedContext`, `SigningOutcome`, `build_signing_tools`, `verify_signing_outcome`, `mint_ephemeral_cert_env`, `write_mock_inbox`, `infer_expected_outcome` — names match across Tasks 5-11 and Task 14 docs.

**Verification before claiming done:** Task 14 step 6 runs the full quality gate (`pytest -m "not e2e"`, ruff, mypy). The bump + ship skill in the Final task is the canonical release entrypoint.

**One known unknown left for the implementer (flagged in Task 5 step 3 and Task 6 step 3):** verify `mint_project_cert` kwargs and `AgentTool` constructor parameter names against the actual source rather than guessing. The plan instructs the implementer to grep, not invent.
