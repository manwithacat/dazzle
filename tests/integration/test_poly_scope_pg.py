"""#1448: real-Postgres proof that a poly_ref read scope isolates rows correctly.

Executes the *compiled* poly scope WHERE against seeded data and asserts the
spec's proof obligation: a teacher sees only AIJob rows whose subject is a Cohort
they uploaded — not a peer's cohort (in-type, out-of-scope subject), and not a
Department-typed row (out-of-scope discriminator).
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_DSL = """module polyscope
app polyscope "Poly Scope"

entity Cohort "Cohort":
  id: uuid pk
  uploaded_by: uuid required

entity Department "Department":
  id: uuid pk
  name: str(80)

entity AIJob "AI Job":
  id: uuid pk
  cost: decimal(10,2)
  subject: poly_ref [Cohort, Department] required

  permit:
    read: role(teacher)

  scope:
    read: subject[Cohort].uploaded_by = current_user
      as: teacher
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
            # The only attr used here is entity_id == the user's own id.
            out.append(user_id)
        else:
            out.append(p)
    return out


@pytest.mark.asyncio
async def test_poly_read_scope_isolates_rows() -> None:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import psycopg

    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.predicate_compiler import compile_predicate
    from dazzle.http.runtime.sa_schema import build_metadata
    from dazzle.rbac.verification_harness import _DisposableDatabase

    appspec = _build_appspec(_DSL)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    read_rule = next(r for r in aijob.access.scopes if r.operation.value == "read")
    sql, params = compile_predicate(read_rule.predicate, "AIJob", appspec.fk_graph)

    teacher1, teacher2 = _mk(), _mk()
    cohort1, cohort2 = _mk(), _mk()  # cohort1 uploaded by teacher1, cohort2 by teacher2
    dept = _mk()
    job_in_scope = _mk()  # subject = cohort1 (teacher1's)
    job_peer = _mk()  # subject = cohort2 (teacher2's) — in-type, out-of-scope
    job_other_type = _mk()  # subject = Department — out-of-scope discriminator

    async with _DisposableDatabase(_PG_URL) as db_url:
        # Create the schema from the (converted, poly-expanded) back-spec entities.
        md = build_metadata(convert_entities(appspec.domain.entities))
        engine_url = db_url
        with psycopg.connect(engine_url, autocommit=True) as conn:
            for tbl in md.sorted_tables:
                cols = []
                for c in tbl.columns:
                    pgt = (
                        "uuid"
                        if c.type.__class__.__name__ == "Uuid"
                        else ("numeric" if c.type.__class__.__name__ == "Numeric" else "text")
                    )
                    cols.append(f'"{c.name}" {pgt}')
                conn.execute(f'CREATE TABLE "{tbl.name}" ({", ".join(cols)})')  # nosemgrep

        with psycopg.connect(engine_url) as conn:
            conn.execute(
                'INSERT INTO "Cohort" (id, uploaded_by) VALUES (%s, %s)', (cohort1, teacher1)
            )
            conn.execute(
                'INSERT INTO "Cohort" (id, uploaded_by) VALUES (%s, %s)', (cohort2, teacher2)
            )
            conn.execute('INSERT INTO "Department" (id, name) VALUES (%s, %s)', (dept, "Maths"))
            conn.execute(
                'INSERT INTO "AIJob" (id, subject_type, subject_id) VALUES (%s, %s, %s)',
                (job_in_scope, "Cohort", cohort1),
            )
            conn.execute(
                'INSERT INTO "AIJob" (id, subject_type, subject_id) VALUES (%s, %s, %s)',
                (job_peer, "Cohort", cohort2),
            )
            conn.execute(
                'INSERT INTO "AIJob" (id, subject_type, subject_id) VALUES (%s, %s, %s)',
                (job_other_type, "Department", dept),
            )
            conn.commit()

            resolved = _resolve_params(params, user_id=teacher1)
            query = f'SELECT id FROM "AIJob" WHERE {sql}'  # nosemgrep — compiled scope fragment
            with conn.cursor() as cur:
                cur.execute(query, resolved)
                visible = {str(row[0]) for row in cur.fetchall()}

    assert job_in_scope in visible, "teacher must see their own cohort's job"
    assert job_peer not in visible, (
        "teacher must NOT see a peer's cohort job (out-of-scope subject)"
    )
    assert job_other_type not in visible, "teacher must NOT see a Department-typed job (wrong type)"
    assert visible == {job_in_scope}


@pytest.mark.asyncio
async def test_poly_create_scope_probe() -> None:
    """#1455: create-scope poly probe against real Postgres — a teacher may create
    an AIJob only when subject_type matches AND the subject row is one they own."""
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import psycopg

    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata
    from dazzle.http.runtime.scope_create_eval import check_create_predicate
    from dazzle.rbac.verification_harness import _DisposableDatabase

    appspec = _build_appspec(_DSL)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    # Reuse the (read) poly predicate — the create probe is verb-independent.
    pred = aijob.access.scopes[0].predicate

    teacher1, teacher2 = _mk(), _mk()
    cohort1, cohort2, dept = _mk(), _mk(), _mk()

    async with _DisposableDatabase(_PG_URL) as db_url:
        md = build_metadata(convert_entities(appspec.domain.entities))
        with psycopg.connect(db_url, autocommit=True) as conn:
            for tbl in md.sorted_tables:
                cols = []
                for c in tbl.columns:
                    pgt = (
                        "uuid"
                        if c.type.__class__.__name__ == "Uuid"
                        else ("numeric" if c.type.__class__.__name__ == "Numeric" else "text")
                    )
                    cols.append(f'"{c.name}" {pgt}')
                conn.execute(f'CREATE TABLE "{tbl.name}" ({", ".join(cols)})')  # nosemgrep
        with psycopg.connect(db_url) as conn:
            conn.execute(
                'INSERT INTO "Cohort" (id, uploaded_by) VALUES (%s, %s)', (cohort1, teacher1)
            )
            conn.execute(
                'INSERT INTO "Cohort" (id, uploaded_by) VALUES (%s, %s)', (cohort2, teacher2)
            )
            conn.execute('INSERT INTO "Department" (id, name) VALUES (%s, %s)', (dept, "Maths"))
            conn.commit()

            def probe(sql: str, params: list) -> bool:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT 1 WHERE {sql}", params)  # nosemgrep — compiled probe
                    return cur.fetchone() is not None

            def can_create(payload: dict) -> bool:
                return check_create_predicate(
                    pred,
                    payload,
                    user_id=teacher1,
                    probe=probe,
                    fk_graph=appspec.fk_graph,
                    entity_name="AIJob",
                )

            # Own cohort → allowed.
            assert can_create({"subject_type": "Cohort", "subject_id": cohort1}) is True
            # Peer's cohort → denied (in-type, out-of-scope subject).
            assert can_create({"subject_type": "Cohort", "subject_id": cohort2}) is False
            # Department-typed → denied (out-of-scope discriminator, no probe needed).
            assert can_create({"subject_type": "Department", "subject_id": dept}) is False
