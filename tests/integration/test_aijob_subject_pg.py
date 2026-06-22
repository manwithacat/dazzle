"""#1454: real-Postgres proof that AIJob.subject is required and scoped correctly.

Mirrors ``tests/integration/test_poly_scope_pg.py``'s disposable-DB + build_metadata
pattern.  Proves all four obligations from the closed-system AI cognition spec (§9):

1. Trigger subject: an AIJob written for a trigger-driven intent has subject_type=entity
   name and subject_id=entity id; the poly_ref scope isolates rows by entity anchor.
2. Process subject: an AIJob for a process-step intent has subject_type="ProcessRun",
   subject_id=run_id; started_by scopes it (subject[ProcessRun].started_by = current_user).
3. NOT-NULL invariant: subject_type and subject_id columns are NOT NULL at the DB level —
   an insert without them raises psycopg.errors.NotNullViolation.
4. Fail-loud: llm_queue.submit and llm_executor.execute raise ValueError when subject is
   missing or empty (no round-trip to Postgres needed for these).

Approach: schema+insert+scope-SQL proof (the "minimum viable proof" from the task brief).
Full runtime write is too heavy (requires a live LLM provider); the scope-SQL + constraint
assertions are the load-bearing correctness claims.

Note on ProcessRun: the governed ProcessRun entity (#1454 Task 1) is injected by the
linker when a process has an llm_intent step.  It carries a ``started_by`` RBAC anchor,
so :func:`dazzle.db.virtual.is_virtual_entity` classifies it as a REAL persisted table
(the admin-monitoring ProcessRun, which lacks ``started_by``, stays virtual).  Its table
is therefore produced by the real ``build_metadata`` path — we include it in the entity
set passed to ``build_metadata`` and create no table manually (the #1454 Task 6 fix; the
prior manual-table workaround is gone).  The scope SQL itself is built directly from IR
predicate types rather than parsed DSL scope rules, so no explicit entity AIJob block is
needed in the DSL.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

# ---------------------------------------------------------------------------
# DSL fixture
#
# Minimal app that triggers AIJob auto-injection (llm_config present) and
# ProcessRun injection (process with an llm_intent step).  No explicit AIJob
# entity block — the linker's auto-generated one is used so subject_type and
# subject_id come from the real AI_JOB_FIELDS derivation path.
# ---------------------------------------------------------------------------

_DSL = """module aijobpg
app aijobpg "AI Job PG"

entity Doc "Doc":
  id: uuid pk
  owner: uuid required

llm_model gpt4 "GPT-4":
  provider: openai
  model_id: gpt-4o
  tier: quality
  max_tokens: 1000

llm_config:
  default_model: gpt4

llm_intent summarize "Summarise Doc":
  model: gpt4
  prompt: "Summarise: $text"
  trigger:
    on_entity: Doc
    on_event: created

process review "Review":
  steps:
    - step run_summarize:
        llm_intent: summarize
        input_map:
          text: context.description
"""


def _mk() -> str:
    return str(uuid.uuid4())


def _build_appspec(dsl: str):
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(dsl)
        f.flush()
        fpath = Path(f.name)
    try:
        modules = parse_modules([fpath])
        return build_appspec(modules, modules[0].name)
    finally:
        os.unlink(fpath)


def _resolve_params(params: list, *, user_id: str) -> list:
    """Resolve compiled runtime markers to concrete values for this test user."""
    from dazzle.http.runtime.predicate_compiler import CurrentUserRef, UserAttrRef

    out = []
    for p in params:
        if isinstance(p, CurrentUserRef):
            out.append(user_id)
        elif isinstance(p, UserAttrRef):
            # entity_id marker resolves to the user's own uuid.
            out.append(user_id)
        else:
            out.append(p)
    return out


def _col_ddl(col) -> str:
    """Return a minimal Postgres DDL fragment for a SQLAlchemy Column."""
    type_map = {
        "Uuid": "uuid",
        "String": "text",
        "Text": "text",
        "Integer": "integer",
        "Float": "float",
        "Boolean": "boolean",
        "DateTime": "timestamptz",
        "Numeric": "numeric",
        "Char": "text",  # SA renders UUID as CHAR(32) — text is fine for scratch
    }
    type_name = type_map.get(col.type.__class__.__name__, "text")
    null_clause = "" if col.nullable else " NOT NULL"
    pk_clause = " PRIMARY KEY" if col.primary_key else ""
    return f'"{col.name}" {type_name}{pk_clause}{null_clause}'


def _build_scope_predicates():
    """Build Doc and ProcessRun scope predicates from IR types directly.

    The auto-generated AIJob entity has no user-authored scope rules (it uses
    simple auth-required permit rules).  We construct the predicates from IR
    types rather than parsing DSL scope rules — this is valid because the
    predicate IR is what the DSL scope rules compile to anyway.
    """
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.core.ir.predicates import CompOp, PolyPathCheck, UserAttrCheck
    from dazzle.http.runtime.predicate_compiler import compile_predicate

    fk_graph = FKGraph()  # no FK traversal needed — direct column checks

    # subject[Doc].owner = current_user
    doc_predicate = PolyPathCheck(
        field="subject",
        type_field="subject_type",
        type_value="Doc",
        id_field="subject_id",
        target_entity="Doc",
        sub=UserAttrCheck(field="owner", op=CompOp.EQ, user_attr="entity_id"),
    )
    doc_sql, doc_params = compile_predicate(doc_predicate, "AIJob", fk_graph)

    # subject[ProcessRun].started_by = current_user
    pr_predicate = PolyPathCheck(
        field="subject",
        type_field="subject_type",
        type_value="ProcessRun",
        id_field="subject_id",
        target_entity="ProcessRun",
        sub=UserAttrCheck(field="started_by", op=CompOp.EQ, user_attr="entity_id"),
    )
    pr_sql, pr_params = compile_predicate(pr_predicate, "AIJob", fk_graph)

    return (doc_sql, doc_params), (pr_sql, pr_params)


def _build_schema_and_create(conn, md) -> None:
    """Create every table from SA metadata.

    The governed ProcessRun table is produced by ``build_metadata`` itself
    (#1454 Task 6 fix: ``is_virtual_entity`` treats a ProcessRun carrying
    ``started_by`` as real), so there is no manual-table workaround here.
    """
    for tbl in md.sorted_tables:
        cols = [_col_ddl(c) for c in tbl.columns]
        conn.execute(f'CREATE TABLE "{tbl.name}" ({", ".join(cols)})')  # nosemgrep


def _insert_aijob(conn, job_id: str, subject_type: str, subject_id: str) -> None:
    """Insert a minimal AIJob row with valid required fields."""
    conn.execute(
        'INSERT INTO "AIJob" '
        "(id, intent, model, provider, status, created_at, subject_type, subject_id) "
        "VALUES (%s, 'summarize', 'gpt-4o', 'openai', 'completed', now(), %s, %s)",
        (job_id, subject_type, subject_id),
    )


@pytest.mark.asyncio
async def test_trigger_subject_scope_isolates_rows() -> None:
    """Obligation 1: trigger-driven AIJob scoped to Doc.owner = current_user.

    Asserts: user1 sees only the AIJob whose Doc subject is owned by user1, not
    user2's Doc job, and not a ProcessRun-typed job.
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import psycopg

    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata
    from dazzle.rbac.verification_harness import _DisposableDatabase

    appspec = _build_appspec(_DSL)
    (doc_sql, doc_params), _ = _build_scope_predicates()

    # Verify AIJob was auto-generated with a subject poly_ref.
    aijob_entity = next(e for e in appspec.domain.entities if e.name == "AIJob")
    subject_field = next(f for f in aijob_entity.fields if f.name == "subject")
    assert subject_field.is_required, "AIJob.subject must be required"
    assert "Doc" in subject_field.type.poly_targets, "Doc must be a valid subject target"

    user1, user2 = _mk(), _mk()
    doc1, doc2 = _mk(), _mk()
    run1 = _mk()
    job_mine = _mk()  # subject = doc1 (owned by user1) → visible to user1
    job_peer = _mk()  # subject = doc2 (owned by user2) → NOT visible to user1
    job_process = _mk()  # subject = ProcessRun → NOT visible under Doc scope

    db_entities = [e for e in appspec.domain.entities if e.name in ("Doc", "AIJob", "ProcessRun")]
    md = build_metadata(convert_entities(db_entities))

    async with _DisposableDatabase(_PG_URL) as db_url:
        with psycopg.connect(db_url, autocommit=True) as conn:
            _build_schema_and_create(conn, md)

        with psycopg.connect(db_url) as conn:
            conn.execute('INSERT INTO "Doc" (id, owner) VALUES (%s, %s)', (doc1, user1))
            conn.execute('INSERT INTO "Doc" (id, owner) VALUES (%s, %s)', (doc2, user2))
            conn.execute(
                'INSERT INTO "ProcessRun" '
                "(id, process_name, status, started_by, created_at) "
                "VALUES (%s, %s, 'completed', %s, now())",
                (run1, "review", user1),
            )
            _insert_aijob(conn, job_mine, "Doc", doc1)
            _insert_aijob(conn, job_peer, "Doc", doc2)
            _insert_aijob(conn, job_process, "ProcessRun", run1)
            conn.commit()

            resolved = _resolve_params(doc_params, user_id=user1)
            query = f'SELECT id FROM "AIJob" WHERE {doc_sql}'  # nosemgrep
            with conn.cursor() as cur:
                cur.execute(query, resolved)
                visible = {str(row[0]) for row in cur.fetchall()}

    assert job_mine in visible, "user1 must see AIJob for their own Doc"
    assert job_peer not in visible, "user1 must NOT see AIJob for user2's Doc"
    assert job_process not in visible, "ProcessRun job must NOT be visible under Doc scope"
    assert visible == {job_mine}


@pytest.mark.asyncio
async def test_process_subject_scope_isolates_rows() -> None:
    """Obligation 2: process-step AIJob scoped to ProcessRun.started_by = current_user.

    Asserts: user1 sees only the AIJob whose ProcessRun subject was started by user1,
    not user2's ProcessRun job, and not a Doc-typed job.
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import psycopg

    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata
    from dazzle.rbac.verification_harness import _DisposableDatabase

    appspec = _build_appspec(_DSL)
    _, (pr_sql, pr_params) = _build_scope_predicates()

    # Verify ProcessRun was auto-injected.
    pr_entity = next((e for e in appspec.domain.entities if e.name == "ProcessRun"), None)
    assert pr_entity is not None, (
        "ProcessRun must be injected when a process has an llm_intent step"
    )
    assert any(f.name == "started_by" for f in pr_entity.fields), (
        "ProcessRun must have started_by (RBAC anchor)"
    )

    # Also verify subject targets include ProcessRun.
    aijob_entity = next(e for e in appspec.domain.entities if e.name == "AIJob")
    subject_field = next(f for f in aijob_entity.fields if f.name == "subject")
    assert "ProcessRun" in subject_field.type.poly_targets, (
        "ProcessRun must be a valid subject target"
    )

    user1, user2 = _mk(), _mk()
    run_mine = _mk()  # started by user1
    run_peer = _mk()  # started by user2
    doc1 = _mk()
    job_mine = _mk()  # subject = run_mine → visible to user1
    job_peer = _mk()  # subject = run_peer → NOT visible to user1
    job_doc = _mk()  # subject = Doc → NOT visible under ProcessRun scope

    db_entities = [e for e in appspec.domain.entities if e.name in ("Doc", "AIJob", "ProcessRun")]
    md = build_metadata(convert_entities(db_entities))

    async with _DisposableDatabase(_PG_URL) as db_url:
        with psycopg.connect(db_url, autocommit=True) as conn:
            _build_schema_and_create(conn, md)

        with psycopg.connect(db_url) as conn:
            conn.execute(
                'INSERT INTO "ProcessRun" '
                "(id, process_name, status, started_by, created_at) "
                "VALUES (%s, %s, 'completed', %s, now())",
                (run_mine, "review", user1),
            )
            conn.execute(
                'INSERT INTO "ProcessRun" '
                "(id, process_name, status, started_by, created_at) "
                "VALUES (%s, %s, 'completed', %s, now())",
                (run_peer, "review", user2),
            )
            conn.execute('INSERT INTO "Doc" (id, owner) VALUES (%s, %s)', (doc1, user1))
            _insert_aijob(conn, job_mine, "ProcessRun", run_mine)
            _insert_aijob(conn, job_peer, "ProcessRun", run_peer)
            _insert_aijob(conn, job_doc, "Doc", doc1)
            conn.commit()

            resolved = _resolve_params(pr_params, user_id=user1)
            query = f'SELECT id FROM "AIJob" WHERE {pr_sql}'  # nosemgrep
            with conn.cursor() as cur:
                cur.execute(query, resolved)
                visible = {str(row[0]) for row in cur.fetchall()}

    assert job_mine in visible, "user1 must see AIJob for their own ProcessRun"
    assert job_peer not in visible, "user1 must NOT see AIJob for user2's ProcessRun"
    assert job_doc not in visible, "Doc job must NOT be visible under ProcessRun scope"
    assert visible == {job_mine}


@pytest.mark.asyncio
async def test_not_null_invariant_at_db() -> None:
    """Obligation 3: subject_type and subject_id are NOT NULL at the Postgres level.

    Verifies:
    - The SA metadata marks subject_type / subject_id as nullable=False (NOT NULL).
    - An INSERT omitting subject_type raises psycopg.errors.NotNullViolation.
    - An INSERT omitting subject_id raises psycopg.errors.NotNullViolation.
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import psycopg
    import psycopg.errors

    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata
    from dazzle.rbac.verification_harness import _DisposableDatabase

    appspec = _build_appspec(_DSL)
    db_entities = [e for e in appspec.domain.entities if e.name in ("Doc", "AIJob")]
    converted = convert_entities(db_entities)
    md = build_metadata(converted)

    # Confirm the SA column metadata marks subject_type and subject_id as NOT NULL.
    aijob_tbl = next(t for t in md.sorted_tables if t.name == "AIJob")
    assert not aijob_tbl.c["subject_type"].nullable, "subject_type must be NOT NULL in SA metadata"
    assert not aijob_tbl.c["subject_id"].nullable, "subject_id must be NOT NULL in SA metadata"

    async with _DisposableDatabase(_PG_URL) as db_url:
        with psycopg.connect(db_url, autocommit=True) as conn:
            _build_schema_and_create(conn, md)

        # INSERT without subject_type must fail at the DB level.
        with pytest.raises(psycopg.errors.NotNullViolation):
            with psycopg.connect(db_url) as conn:
                conn.execute(
                    'INSERT INTO "AIJob" '
                    "(id, intent, model, provider, status, created_at, subject_id) "
                    "VALUES (%s, 'x', 'y', 'z', 'pending', now(), %s)",
                    (str(uuid.uuid4()), str(uuid.uuid4())),
                )
                conn.commit()

        # INSERT without subject_id must fail at the DB level.
        with pytest.raises(psycopg.errors.NotNullViolation):
            with psycopg.connect(db_url) as conn:
                conn.execute(
                    'INSERT INTO "AIJob" '
                    "(id, intent, model, provider, status, created_at, subject_type) "
                    "VALUES (%s, 'x', 'y', 'z', 'pending', now(), 'Doc')",
                    (str(uuid.uuid4()),),
                )
                conn.commit()


def test_submit_raises_on_missing_subject() -> None:
    """Obligation 4a: llm_queue.submit raises ValueError when subject is empty."""
    import asyncio

    from dazzle.http.runtime.llm_queue import LLMJobQueue

    class _StubExecutor:
        pass

    queue = LLMJobQueue(executor=_StubExecutor())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="no subject"):
        asyncio.run(
            queue.submit(
                "test_intent",
                {},
                subject_type="",
                subject_id="some-id",
            )
        )

    with pytest.raises(ValueError, match="no subject"):
        asyncio.run(
            queue.submit(
                "test_intent",
                {},
                subject_type="Doc",
                subject_id="",
            )
        )


def test_executor_raises_on_missing_subject() -> None:
    """Obligation 4b: llm_executor.execute raises ValueError when subject is empty."""
    import asyncio

    from dazzle.http.runtime.llm_executor import LLMIntentExecutor

    class _StubAppSpec:
        llm_intents: list = []
        llm_models: list = []
        llm_config = None

    executor = LLMIntentExecutor(appspec=_StubAppSpec())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="no subject"):
        asyncio.run(
            executor.execute(
                "test_intent",
                {},
                subject_type="",
                subject_id="some-id",
            )
        )

    with pytest.raises(ValueError, match="no subject"):
        asyncio.run(
            executor.execute(
                "test_intent",
                {},
                subject_type="Doc",
                subject_id="",
            )
        )
