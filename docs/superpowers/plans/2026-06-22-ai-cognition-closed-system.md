# Closed-system AI Cognition (#1454) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every AI call in a Dazzle app carry a typed, auditable, scope-able subject — `AIJob.subject` becomes a required `poly_ref` over the declared-cognition surface (trigger `on_entity` entities ∪ a new `ProcessRun` run entity), and the subjectless bare `POST /execute/{intent_name}` path is removed.

**Architecture:** The framework-injected `AIJob` entity drops its stringly-typed `entity_type`/`entity_id` columns for a required `poly_ref subject [<derived>]` (→ `subject_type text` + `subject_id uuid`). Targets are derived at link time. Trigger-driven AI sets `subject = the triggering entity`; process-`llm_intent`-step AI sets `subject = the ProcessRun` (a newly-injected uuid-pk, `started_by`-anchored run entity persisted in app Postgres). The two declared surfaces are the only app-facing AI paths; the bare route is deleted and the executor/queue require a subject.

**Tech Stack:** Python 3.12+, Pydantic IR, the #1448 `poly_ref` primitive + `PolyPathCheck`, SQLAlchemy (`sa_schema`), psycopg3, FastAPI, pytest (unit + real-PG).

**Spec:** `docs/superpowers/specs/2026-06-22-ai-cognition-closed-system-1454-design.md`.

## Global Constraints

- **No-NULL invariant:** `AIJob.subject` is **required** — no persisted `AIJob` without a subject. Enforced by the schema (NOT NULL via `poly_ref ... required`) + the executor/queue raising on a missing subject.
- **Two declared surfaces only:** entity `llm_intent` trigger, or a `process` step `kind: llm_intent`. No third app-facing AI path.
- **Clean break, no shims** (ADR-0003): drop `entity_type`/`entity_id`, update all sites in the same change. **Schema via Alembic / regenerated** (ADR-0017); `AIJob` is framework-injected so it regenerates from the IR.
- **poly_ref targets must be uuid-pk** (#1448/ADR-0042). `ProcessRun` is injected uuid-pk to satisfy this.
- **poly_ref is `required` by the modifier** (#1448) — `poly_ref name [...] required` → both columns NOT NULL.
- Pre-ship gate = `pytest -m "not e2e"` from repo root (covers `tests/` + `src/dazzle/http/tests/`), plus mypy, ruff, lint-imports, and the drift suites (ir-types, api-surface, docs-drift). `dazzle fitness code --write-baseline` if complexity shifts.
- Ship discipline: `/bump patch`; `ruff format` touched files before commit (pre-commit aborts otherwise).

---

### Task 1: Inject the `ProcessRun` system entity (IR + linker)

**Files:**
- Modify: `src/dazzle/core/ir/process.py` (add `PROCESS_RUN_FIELDS` near the top-level field-tuple convention used by `JOB_RUN_FIELDS`)
- Modify: `src/dazzle/core/linker.py` (add `_build_process_run_entity`; inject it next to `_build_ai_job_entity` at ~line 137)
- Test: `tests/unit/test_process_run_entity.py` (create)

**Interfaces:**
- Produces: a `ProcessRun` `EntitySpec` with fields `id uuid pk`, `process_name str(200) required`, `status enum[pending,running,completed,failed] required =pending`, `started_by str(200)` (RBAC anchor — holds the initiating user's entity id), `started_at datetime`, `finished_at datetime`, `error_message text`, `created_at datetime required =now`. Injected when any process has an `llm_intent` step. Consumed by Tasks 2 (target set) and 4 (runtime row).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_process_run_entity.py
import os, tempfile
from pathlib import Path


def _build_appspec(dsl: str):
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(dsl); f.flush(); p = Path(f.name)
    try:
        return build_appspec(parse_modules([p]), parse_modules([p])[0].name)
    finally:
        os.unlink(p)


_DSL = """module m
app a "A"

llm_config:
  default_model: m1

llm_model m1 "M1":
  provider: anthropic
  model_id: x

entity Doc "Doc":
  id: uuid pk
  body: text

process review "Review":
  step classify:
    kind: llm_intent
    llm_intent: summarize
    llm_input_map:
      text: context.body

llm_intent summarize "Summarize":
  model: m1
  prompt: "{{ input.text }}"
"""


def test_process_run_injected_when_process_has_llm_step():
    appspec = _build_appspec(_DSL)
    pr = next((e for e in appspec.domain.entities if e.name == "ProcessRun"), None)
    assert pr is not None, "ProcessRun must be injected when a process has an llm_intent step"
    names = {f.name for f in pr.fields}
    assert {"id", "process_name", "status", "started_by", "started_at"} <= names
    idf = next(f for f in pr.fields if f.name == "id")
    assert idf.type.kind.value == "uuid"
```

> Confirm the exact process-step DSL grammar (`kind: llm_intent`, `llm_intent:`, `llm_input_map:`) against `tests/unit/test_parser.py` / a process fixture; adjust the `_DSL` to parse. If `build_appspec` needs a specific entry, mirror `tests/unit/test_scope_rules.py::_build_appspec`.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_process_run_entity.py -q`
Expected: FAIL — no `ProcessRun` entity.

- [ ] **Step 3: Add `PROCESS_RUN_FIELDS`** in `src/dazzle/core/ir/process.py` (mirror `JOB_RUN_FIELDS` shape from `core/ir/jobs.py:141`):

```python
# #1454: persisted, uuid-pk, user-anchored run record for a process execution —
# the AIJob subject for process-step AI calls (closed-system AI cognition).
PROCESS_RUN_FIELDS: list[tuple[str, str, list[str], str | None]] = [
    ("id", "uuid", ["pk"], None),
    ("process_name", "str(200)", ["required"], None),
    ("status", "enum[pending,running,completed,failed]", ["required"], "pending"),
    ("started_by", "str(200)", [], None),  # initiating user's entity id — RBAC anchor
    ("started_at", "datetime", [], None),
    ("finished_at", "datetime", [], None),
    ("error_message", "text", [], None),
    ("created_at", "datetime", ["required"], "now"),
]
```

- [ ] **Step 4: Add `_build_process_run_entity` + inject it** in `src/dazzle/core/linker.py` (mirror `_build_ai_job_entity` at line 1004; import `PROCESS_RUN_FIELDS`). Add after the `_build_ai_job_entity` def:

```python
def _build_process_run_entity() -> ir.EntitySpec:
    """Build the auto-generated ProcessRun system entity (#1454).

    Persists each process execution as a uuid-pk, user-anchored audit row so a
    process `llm_intent` step's AIJob can name it as the subject.
    """
    from dazzle.core.ir.process import PROCESS_RUN_FIELDS

    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in PROCESS_RUN_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))
    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(operation=op, require_auth=True, effect=ir.PolicyEffect.PERMIT)
            for op in ir.PermissionKind
        ]
    )
    return ir.EntitySpec(
        name="ProcessRun",
        title="Process Run",
        intent="Audit record of a process execution; subject for process-step AI calls",
        domain="platform",
        patterns=["system", "audit"],
        fields=fields,
        access=access,
    )
```

In the injection block (linker.py ~135-138), inject `ProcessRun` when any process has an `llm_intent` step:

```python
    # 9. Auto-generate AIJob entity when LLM config is present (#376)
    entities = merged_fragment.entities
    if merged_fragment.llm_config is not None and not any(e.name == "AIJob" for e in entities):
        entities = [*entities, _build_ai_job_entity(_derive_aijob_subject_targets(merged_fragment))]
    # #1454: ProcessRun when any process runs AI — the run is the AIJob subject.
    _has_llm_step = any(
        getattr(s, "kind", None) == ir.StepKind.LLM_INTENT
        for p in merged_fragment.processes
        for s in p.steps
    )
    if _has_llm_step and not any(e.name == "ProcessRun" for e in entities):
        entities = [*entities, _build_process_run_entity()]
```

> `_derive_aijob_subject_targets` + the `_build_ai_job_entity(targets)` signature change land in Task 2; for Task 1, keep `_build_ai_job_entity()` as-is and only add the ProcessRun injection. (Order the commits so Task 1 doesn't reference Task 2's symbol — inject ProcessRun first, wire targets second.) Confirm `ir.StepKind.LLM_INTENT` is the enum value (`core/ir/process.py:49`).

- [ ] **Step 5: Run to verify it passes** → `python -m pytest tests/unit/test_process_run_entity.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
ruff format src/dazzle/core/ir/process.py src/dazzle/core/linker.py tests/unit/test_process_run_entity.py
git add -A && git commit -m "feat(ir): #1454 inject ProcessRun system entity for process-step AI subjects"
```

---

### Task 2: Derive `AIJob.subject` poly_ref targets + make `subject` required

**Files:**
- Modify: `src/dazzle/core/ir/llm.py` (`AI_JOB_FIELDS`: remove `entity_type`/`entity_id`)
- Modify: `src/dazzle/core/linker.py` (`_build_ai_job_entity(targets)` appends the `subject` poly_ref; add `_derive_aijob_subject_targets`)
- Modify: `src/dazzle/core/validation/` (add `E_AIJOB_NO_SUBJECT_SURFACE` — empty targets + llm_config present)
- Test: `tests/unit/test_aijob_subject.py` (create)

**Interfaces:**
- Consumes: `ProcessRun` (Task 1); `FieldTypeKind.POLY_REF` + `poly_targets` (#1448).
- Produces: `_derive_aijob_subject_targets(fragment) -> list[str]` = sorted `{trigger.on_entity}` ∪ (`{"ProcessRun"}` if any llm_intent step). `_build_ai_job_entity(targets: list[str])` appends `FieldSpec(name="subject", type=FieldType(kind=POLY_REF, poly_targets=targets), modifiers=[REQUIRED])`. `AIJob` has no `entity_type`/`entity_id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_aijob_subject.py  (reuse _build_appspec from test_process_run_entity pattern)
# ... _build_appspec + a DSL with: one llm_intent trigger on Doc, one process llm_intent step ...

def test_aijob_subject_is_required_polyref_over_derived_targets():
    appspec = _build_appspec(_DSL_WITH_TRIGGER_AND_PROCESS)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    names = {f.name for f in aijob.fields}
    assert "entity_type" not in names and "entity_id" not in names
    subj = next(f for f in aijob.fields if f.name == "subject")
    assert subj.type.kind.value == "poly_ref"
    assert "Doc" in subj.type.poly_targets and "ProcessRun" in subj.type.poly_targets
    assert subj.is_required  # the no-NULL invariant
```

- [ ] **Step 2: Run to verify it fails** → references `subject`/derivation that don't exist → FAIL.

- [ ] **Step 3: Remove the stringly columns** in `core/ir/llm.py` `AI_JOB_FIELDS` — delete these two lines:

```python
    ("entity_type", "str(200)", [], None),
    ("entity_id", "str(200)", [], None),
```

- [ ] **Step 4: Add derivation + change the builder** in `linker.py`:

```python
def _derive_aijob_subject_targets(fragment: object) -> list[str]:
    """#1454: AIJob subject targets = the declared-cognition surface — every
    trigger.on_entity, plus ProcessRun when any process runs an llm_intent step."""
    targets: set[str] = set()
    for intent in getattr(fragment, "llm_intents", []) or []:
        for trig in getattr(intent, "triggers", []) or []:
            if getattr(trig, "on_entity", None):
                targets.add(trig.on_entity)
    has_llm_step = any(
        getattr(s, "kind", None) == ir.StepKind.LLM_INTENT
        for p in getattr(fragment, "processes", []) or []
        for s in p.steps
    )
    if has_llm_step:
        targets.add("ProcessRun")
    return sorted(targets)
```

Change `_build_ai_job_entity` to accept `targets` and append the subject field (import `FieldTypeKind`/`FieldType` from `dazzle.core.ir.fields`):

```python
def _build_ai_job_entity(subject_targets: list[str]) -> ir.EntitySpec:
    """Build the auto-generated AIJob entity (#376/#1454). `subject` is a required
    poly_ref over the declared-cognition surface (trigger entities + ProcessRun)."""
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in AI_JOB_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))
    # #1454: required poly_ref subject — the governance unit.
    fields.append(
        FieldSpec(
            name="subject",
            type=ir.FieldType(kind=ir.FieldTypeKind.POLY_REF, poly_targets=subject_targets),
            modifiers=[ir.FieldModifier.REQUIRED],
        )
    )
    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(operation=op, require_auth=True, effect=ir.PolicyEffect.PERMIT)
            for op in ir.PermissionKind
        ]
    )
    return ir.EntitySpec(
        name="AIJob", title="AI Job",
        intent="Tracks every AI gateway call with token counts, cost, and audit trail",
        domain="platform", patterns=["system", "audit"], fields=fields, access=access,
    )
```

> Confirm `ir.FieldModifier.REQUIRED` is the correct modifier enum (grep `FieldModifier` in `core/ir/fields.py`); `_MODIFIER_MAP["required"]` in the linker shows the value. Confirm `FieldSpec.is_required` reflects it.

- [ ] **Step 5: Add the empty-surface validation error** (in the validator that runs framework-entity checks — grep where platform entities are validated, e.g. `core/validation/`):

```python
# When llm_config is present but no trigger/process declares a subject surface,
# AIJob has a required subject with no legal target — fail loud.
if appspec.llm_config is not None:
    aijob = next((e for e in appspec.domain.entities if e.name == "AIJob"), None)
    if aijob is not None:
        subj = next((f for f in aijob.fields if f.name == "subject"), None)
        if subj is not None and not (subj.type.poly_targets or []):
            errors.append(
                "E_AIJOB_NO_SUBJECT_SURFACE: llm_config is present but no AI subject "
                "surface is declared — add an llm_intent trigger (trigger: on_entity: X) "
                "or a process step (kind: llm_intent) so AIJob has a scope-able subject."
            )
```

Add a test for this error (llm_config, no triggers, no llm_intent steps → error).

- [ ] **Step 6: Run to verify passes** → `python -m pytest tests/unit/test_aijob_subject.py -q` → PASS.

- [ ] **Step 7: Commit**

```bash
ruff format src/dazzle/core/ir/llm.py src/dazzle/core/linker.py tests/unit/test_aijob_subject.py
git add -A && git commit -m "feat(ir): #1454 AIJob.subject required poly_ref over derived cognition surface"
```

---

### Task 3: AIJob write sites — `entity_type`/`entity_id` → `subject_type`/`subject_id`, subject required

**Files:**
- Modify: `src/dazzle/http/runtime/llm_queue.py` (`submit` + `LLMJob`)
- Modify: `src/dazzle/http/runtime/llm_executor.py` (`_record_job` + `execute` signature)
- Modify: `src/dazzle/http/runtime/llm_trigger.py` (dispatch call)
- Test: `tests/unit/test_aijob_write_sites.py` (create)

**Interfaces:**
- Consumes: the renamed columns (`subject_type`/`subject_id`) from Task 2's schema.
- Produces: `LLMJobQueue.submit(..., subject_type: str, subject_id: str, ...)` (required, no default); `LLMIntentExecutor.execute(..., subject_type: str, subject_id: str)` threading to `_record_job`; both **raise `ValueError` if subject is missing/empty** (the no-NULL guard). Consumed by Tasks 4 (process) + the trigger path.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_aijob_write_sites.py
import pytest


def test_record_job_writes_subject_columns(fake_ai_job_service):  # capture create payload
    # Build an LLMIntentExecutor with a fake _ai_job_service that records the dict;
    # call execute(..., subject_type="Doc", subject_id="<uuid>") and assert the
    # created AIJob dict has subject_type/subject_id (NOT entity_type/entity_id).
    ...


def test_submit_requires_subject():
    from dazzle.http.runtime.llm_queue import LLMJobQueue
    q = LLMJobQueue(...)  # mirror an existing llm_queue test's construction
    with pytest.raises(ValueError):
        # missing subject → fail-loud (no NULL-subject AIJob)
        anyio.run(q.submit, "intent", {})  # no subject_type/subject_id
```

> Mirror an existing `tests/unit/test_llm_*` for executor/queue construction + the `fake_ai_job_service` capture pattern.

- [ ] **Step 2: Run to verify it fails** → FAIL (still `entity_type`/`entity_id`; no guard).

- [ ] **Step 3: Update `llm_queue.py` `submit`** — rename params + require + write subject columns:

```python
async def submit(
    self,
    intent_name: str,
    input_data: dict[str, Any],
    *,
    subject_type: str,
    subject_id: str,
    user_id: str | None = None,
    callback: CompletionCallback | None = None,
) -> str:
    if not subject_type or not subject_id:
        raise ValueError(
            f"AI call for intent '{intent_name}' has no subject — every AIJob must "
            "name a subject (entity or ProcessRun). #1454 closed-system AI cognition."
        )
    import uuid
    job_id = str(uuid.uuid4())
    if self._ai_job_service:
        try:
            resp = await asyncio.to_thread(
                self._ai_job_service.execute, action="create",
                data={
                    "id": job_id, "intent": intent_name, "model": "", "provider": "",
                    "status": "pending",
                    "subject_type": subject_type, "subject_id": subject_id,
                    "user_id": user_id,
                },
            )
            if resp and hasattr(resp, "get"):
                job_id = resp.get("id", job_id)
        except Exception:
            logger.debug("Could not create AIJob record for %s", intent_name)
    job = LLMJob(
        job_id=job_id, intent_name=intent_name, input_data=input_data,
        user_id=user_id, subject_type=subject_type, subject_id=subject_id, callback=callback,
    )
    await self._queue.put(job)
    return job_id
```

Rename `LLMJob`'s `entity_type`/`entity_id` fields → `subject_type`/`subject_id` (find the dataclass/model in `llm_queue.py`).

- [ ] **Step 4: Update `llm_executor.py`** — `execute` gains required `subject_type`/`subject_id`, threaded to `_record_job`, which writes them:

```python
# in _record_job's job_data dict, replace the (absent) entity columns with:
            "subject_type": subject_type,
            "subject_id": subject_id,
# and add subject_type/subject_id params to _record_job + execute signatures,
# raising ValueError if empty (mirror the submit guard).
```

- [ ] **Step 5: Update `llm_trigger.py`** dispatch — `entity_type=`/`entity_id=` → `subject_type=`/`subject_id=`:

```python
    await self._queue.submit(
        entry.intent_name, input_data,
        subject_type=event.entity_name,   # the triggering entity
        subject_id=event.entity_id,
        user_id=event.user_id,
        callback=callback,
    )
```

- [ ] **Step 6: Run → PASS.** Commit.

```bash
ruff format src/dazzle/http/runtime/llm_queue.py src/dazzle/http/runtime/llm_executor.py src/dazzle/http/runtime/llm_trigger.py tests/unit/test_aijob_write_sites.py
git add -A && git commit -m "feat(http): #1454 AIJob write sites set required subject_type/subject_id"
```

---

### Task 4: ProcessRun runtime row + process-step AI subject

**Files:**
- Modify: `src/dazzle/http/runtime/process_executor.py` (`execute` creates a ProcessRun row + threads `run_id`; `_execute_llm_step` passes `subject_type="ProcessRun", subject_id=run_id`)
- Test: `tests/unit/test_process_run_executor.py` (create)

**Interfaces:**
- Consumes: `ProcessRun` entity (Task 1); `executor.execute(..., subject_type, subject_id)` (Task 3).
- Produces: a persisted `ProcessRun` row per `ProcessExecutor.execute()` (status `running`→`completed`/`failed`, `started_by` = initiating user); `_execute_llm_step` calls `self._llm_executor.execute(intent_name, input_data, subject_type="ProcessRun", subject_id=context.run_id)`.

- [ ] **Step 1: Write the failing test** — execute a process with an llm_intent step against a fake executor + fake ProcessRun service; assert (a) a ProcessRun row was created with `started_by`, (b) the llm executor was called with `subject_type="ProcessRun"`, `subject_id=<that run id>`.

- [ ] **Step 2: Run → fail** (no run row, no subject passed).

- [ ] **Step 3: Create the ProcessRun row in `ProcessExecutor.execute()`** — at the start, insert a ProcessRun (status `running`, `started_by`=the initiating user, `process_name`=the process name) via the ProcessRun service/repository, store `run_id` on `ProcessContext`; on completion/failure update status. Mirror how `_ai_job_service` is injected for the ProcessRun service (a `_process_run_service` constructor-injected, like `_ai_job_service`).

- [ ] **Step 4: Pass the subject in `_execute_llm_step`** (process_executor.py:206):

```python
    result = await self._llm_executor.execute(
        intent_name, input_data,
        subject_type="ProcessRun", subject_id=context.run_id,
    )
```

- [ ] **Step 5: Run → PASS.** Commit.

> The ProcessRun service wiring (app_factory injecting a `_process_run_service` into `ProcessExecutor`, both boot paths) mirrors the `_ai_job_service` wiring — find where `ProcessExecutor` is constructed (`grep "ProcessExecutor("`), inject the ProcessRun CRUD service the same way. If processes don't currently run in-request with a CRUD service available, this is the task's main integration work — follow the `_ai_job_service` precedent exactly.

```bash
git add -A && git commit -m "feat(http): #1454 persist ProcessRun + set ProcessRun subject on process-step AI"
```

---

### Task 5: Remove the bare `POST /execute/{intent_name}` path

**Files:**
- Modify: `src/dazzle/http/runtime/llm_routes.py` (delete `execute_intent` + unused request/response models)
- Test: `tests/unit/test_no_bare_llm_route.py` (create — the guard)

**Interfaces:**
- Consumes: nothing.
- Produces: no mounted generic intent-execution route; a `test_no_*` guard asserting it stays gone.

- [ ] **Step 1: Write the failing guard test**

```python
# tests/unit/test_no_bare_llm_route.py
def test_no_generic_intent_execute_route():
    from dazzle.http.runtime.llm_routes import build_llm_router  # confirm the builder name
    router = build_llm_router(...)  # mirror an existing llm_routes test's construction
    paths = {r.path for r in router.routes}
    assert not any("/execute/" in p for p in paths), (
        "#1454: the bare POST /execute/{intent} path must stay removed — AI runs only "
        "via an entity trigger or a process step."
    )
```

- [ ] **Step 2: Run → fail** (route still present).

- [ ] **Step 3: Delete** the `@router.post("/execute/{intent_name}")` `execute_intent` function (llm_routes.py:58-84) and the `IntentExecuteRequest`/`IntentExecuteResponse`/`AsyncJobResponse` models if unused elsewhere (grep each name first; keep any still referenced).

- [ ] **Step 4: Run → PASS.** Verify nothing else imports the deleted names (`grep -rn "execute_intent\|IntentExecuteRequest"`). Commit.

```bash
git add -A && git commit -m "refactor(http)!: #1454 remove bare POST /execute/{intent} — no subjectless AI path"
```

---

### Task 6: Real-Postgres integration proof

**Files:**
- Modify: `tests/integration/test_poly_scope_pg.py` (or new `tests/integration/test_aijob_subject_pg.py`)

**Interfaces:** Consumes the full stack.

- [ ] **Step 1–3:** Add a real-PG test (mirror `tests/integration/test_poly_scope_pg.py`'s disposable-DB + build_metadata pattern) proving:
  - a trigger AIJob row has `subject_type` = the entity, `subject_id` = its id; the AIJob read scope (`subject[Doc].<anchor> = current_user`) isolates rows;
  - a process-step AIJob row has `subject_type="ProcessRun"`, `subject_id` = the run; the run's `started_by` scopes it;
  - **invariant:** every persisted AIJob row has non-null `subject_type` + `subject_id`;
  - `submit`/`execute` raise on a missing subject.

Run: `DATABASE_URL=postgresql://localhost:5432/postgres python -m pytest tests/integration/test_aijob_subject_pg.py -q`

- [ ] **Step 4: Commit.**

---

### Task 7: ADR + architecture explainer + drift/baselines + ship

**Files:**
- Create: `docs/adr/0043-closed-system-ai-cognition.md`
- Create: `docs/architecture/ai-cognition.md`
- Modify: `CHANGELOG.md` (Added + Agent Guidance), `docs/api-surface/*` (route removed → `dazzle inspect api runtime-urls --write`), `docs/api-surface/ir-types.txt` (`dazzle inspect api ir-types --write` — ProcessRun + AIJob.subject), example `expected/` AIJob references if any.

- [ ] **Step 1: ADR-0043** — the invariant (every AI call has a governed subject), the two surfaces, why the bare path is removed, subject-as-governance-unit, ProcessRun as the run referent. Add to `docs/adr/INDEX.md`.
- [ ] **Step 2: `docs/architecture/ai-cognition.md`** — the founder/agent narrative: declare AI via a trigger or a process step; audit/cost/RBAC are derived; no third path.
- [ ] **Step 3: CHANGELOG** Added + Agent Guidance ("to add AI cognition, declare an `llm_intent` trigger or a process `llm_intent` step; never a bare call; the AIJob audit trail scopes by subject automatically").
- [ ] **Step 4: Regenerate baselines** — `dazzle inspect api ir-types --write`, `dazzle inspect api runtime-urls --write`; run `tests/unit/test_docs_drift.py` + `test_api_surface_drift.py`; update any example `expected/` AIJob schema references.
- [ ] **Step 5: Full gate** — `pytest -m "not e2e"` (repo root), `ruff check --fix && ruff format`, `mypy src/dazzle`, `lint-imports`. Fix drift.
- [ ] **Step 6: Ship** — `/bump`, commit, tag, push, watch CI, comment + close #1454.

---

## Self-Review

**Spec coverage:** §1 invariant → enforced by Task 2 (required) + Task 3/4 (all write sites set subject) + Task 5 (no bare path) + Task 6 (invariant test). §2 two surfaces → Task 3 (trigger) + Task 4 (process) + Task 5 (removal). §3 required poly_ref → Task 2. §4 route removal → Task 5. §5 run referent → resolved: **inject ProcessRun** (Task 1) — the investigation confirmed no existing uuid-pk app-Postgres user-anchored run entity (`JobRun` lacks `started_by` + is job-only; process runs are in-memory). §6 derivation → Task 2 (`_derive_aijob_subject_targets`). §7 migration → clean break across Tasks 2-3 + Task 7 baselines. §8 docs → Task 7. §9 testing → Tasks 1-6. §11 rubric → schema NOT NULL + guard + oracle, all live.

**Placeholder scan:** the `> Confirm …` callouts are codebase-shape verifications (constructor signatures, enum names, the ProcessExecutor/service-injection site) each naming the exact grep — not deferred logic. The one genuinely investigation-gated item (run referent) is **resolved** (inject ProcessRun). Task 3/4/5 test bodies have `...` placeholders for fixture construction that must mirror named existing tests — the implementer fills them from the cited precedent; the production code is complete.

**Type consistency:** `subject_type`/`subject_id` used identically across Tasks 2 (schema), 3 (write sites), 4 (process), 6 (proof). `_derive_aijob_subject_targets(fragment) -> list[str]` ↔ `_build_ai_job_entity(subject_targets: list[str])` consistent. `ProcessRun` name + `started_by` anchor consistent across Tasks 1/4/6. `context.run_id` (Task 4) is the ProcessRun id.

**Scope:** one interlocked invariant (the no-NULL closure forces Tasks 1-5 to ship together — a partial state leaves a broken or NULL-subject path), so it's one plan, not decomposable.

**Note for the implementer:** ship Tasks 1-5 as one logical unit before the Task 6 PG proof + Task 7 ship — intermediate commits will have a red full-suite (AIJob schema changed before all write sites updated). Use a worktree or land Tasks 1-5 rapidly; the pre-ship gate is after Task 6.
