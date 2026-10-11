# Auth Plan 2b — Access-Evidence / Access-Review Export

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Plan 2a membership lifecycle substrate into auditor-ready output: a `dazzle rbac access-review` command that produces a per-org membership snapshot (current **or** point-in-time "as of date D"), the Joiner/Mover/Leaver (JML) event stream over a period, both mapped to SOC 2 CC6.x / ISO A.5.15–18 controls, plus a tamper-evidence attestation — in markdown and JSON.

**Architecture:** A new pure module `src/dazzle/rbac/access_evidence.py` builds the evidence dataclasses from the live `AuthStore` (`get_memberships_for_tenant` for the current roster; replaying `get_membership_events` up to a date for point-in-time). A code-level control map encodes the spec §6 event→control table. Rendering lives in `src/dazzle/rbac/report.py` (markdown) with JSON via dataclass serialization. A new `dazzle rbac access-review` subcommand wires the live DB URL → AuthStore → builder → renderer. The static `rbac report` stays AppSpec-only; this is its DB-backed sibling.

**Tech Stack:** Python 3.12, psycopg3 (via `AuthStore`), typer (CLI), dataclasses + `json`. Consumes Plan 2a (`membership_events`, `get_membership_events`, `verify_membership_event_chain`).

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §6. This is slice **2b** of Plan 2; slice **2a** (the event substrate) shipped v0.81.39.

**Decisions (confirmed):** point-in-time replay (not current-only); new `dazzle rbac access-review` subcommand (not folded into the static report); markdown **and** JSON; control map in code (spec §6 is explicit).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/auth/store.py` (**modify**) | Add `get_memberships_for_tenant(tenant_id)` — the current-roster query (mirrors `get_memberships_for_identity`). |
| `src/dazzle/rbac/access_evidence.py` (**create**) | Evidence dataclasses (`MemberSnapshot`, `OrgAccessSnapshot`, `JmlEntry`, `AccessReview`), the point-in-time replay (`build_org_snapshot`), JML classification (`build_jml_stream`), the `ACCESS_EVIDENCE_CONTROLS` spec-§6 map, and `build_access_review`. Pure builders — the replay takes a list of events so it is unit-testable without a DB. |
| `src/dazzle/rbac/report.py` (**modify**) | Add `render_access_review_markdown(review)` — the human-readable evidence pack (roster table + JML table + control coverage + chain attestation). |
| `src/dazzle/cli/rbac.py` (**modify**) | Add `dazzle rbac access-review` subcommand: resolve live DB URL → `AuthStore` → `build_access_review` → markdown or JSON. |
| `tests/unit/test_access_evidence.py` (**create**) | Pure replay-logic tests (feed event lists): joiner/mover/leaver roster reconstruction, point-in-time cutoff, removed-then-reprovisioned, suspended-in-roster, JML classification, control-map coverage. |
| `tests/integration/test_access_review_pg.py` (**create**) | Real-PG: build_access_review end-to-end against a seeded auth store; current vs as-of snapshot; JSON round-trips; chain attestation present. |

---

## Task 1: `get_memberships_for_tenant` (current roster query)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (after `get_memberships_for_identity`, ~line 778)
- Test: `tests/integration/test_access_review_pg.py` (created here)

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_access_review_pg.py
"""Real-PG proof of the access-review export (auth Plan 2b)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _admin_url()
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_axrev_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=store_url)
    store._init_db()
    return store


def test_get_memberships_for_tenant_returns_current_roster(store_url: str) -> None:
    store = _store(store_url)
    ua = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    ub = store.create_user(email="b@b.test", password="pw123456", roles=["worker"])
    store.create_membership(tenant_id="org-1", identity_id=str(ua.id), roles=["admin"])
    store.create_membership(tenant_id="org-1", identity_id=str(ub.id), roles=["member"])
    store.create_membership(tenant_id="org-2", identity_id=str(ua.id), roles=["member"])

    roster = store.get_memberships_for_tenant("org-1")
    assert {m.identity_id for m in roster} == {str(ua.id), str(ub.id)}
    assert all(m.tenant_id == "org-1" for m in roster)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_access_review_pg.py::test_get_memberships_for_tenant_returns_current_roster -q`
Expected: FAIL — `AttributeError: 'AuthStore' object has no attribute 'get_memberships_for_tenant'`

- [ ] **Step 3: Add the query method**

In `store.py`, after `get_memberships_for_identity`:

```python
    def get_memberships_for_tenant(self, tenant_id: str) -> list[MembershipRecord]:
        """Current roster: all memberships in an org (auth Plan 2b — access review)."""
        rows = self._execute(
            "SELECT * FROM memberships WHERE tenant_id = %s ORDER BY created_at",
            (tenant_id,),
        )
        return [self._row_to_membership(r) for r in rows]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_access_review_pg.py::test_get_memberships_for_tenant_returns_current_roster -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ruff check src/dazzle/http/runtime/auth/store.py tests/integration/test_access_review_pg.py --fix
ruff format src/dazzle/http/runtime/auth/store.py tests/integration/test_access_review_pg.py
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_access_review_pg.py
git commit -m "feat(auth): get_memberships_for_tenant current-roster query (Plan 2b)"
```

---

## Task 2: `access_evidence.py` — snapshot replay, JML, control map, builder

**Files:**
- Create: `src/dazzle/rbac/access_evidence.py`
- Test: `tests/unit/test_access_evidence.py`

- [ ] **Step 1: Write the failing unit tests** (pure replay — feed event lists, no DB)

```python
# tests/unit/test_access_evidence.py
"""Pure point-in-time replay + JML classification + control map (auth Plan 2b)."""

from datetime import UTC, datetime

from dazzle.http.runtime.auth.membership_events import MembershipEvent, MembershipEventType
from dazzle.rbac.access_evidence import (
    ACCESS_EVIDENCE_CONTROLS,
    classify_jml,
    replay_roster,
)


def _evt(seq, etype, mid, *, roles_after=None, status_after=None, identity="u-1", when="2026-01-01"):
    return MembershipEvent(
        id=f"e{seq}",
        event_type=etype,
        membership_id=mid,
        tenant_id="org-1",
        identity_id=identity,
        actor_id=None,
        roles_before=None,
        roles_after=roles_after,
        status_before=None,
        status_after=status_after,
        reason=None,
        created_at=datetime.fromisoformat(f"{when}T00:00:00+00:00"),
        seq=seq,
    )


def test_replay_builds_roster_from_provision_and_role_change() -> None:
    events = [
        _evt(1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"),
        _evt(2, MembershipEventType.ROLE_CHANGED, "m1", roles_after=["member", "approver"]),
    ]
    roster = replay_roster(events)
    assert len(roster) == 1
    assert roster["m1"].roles == ["member", "approver"]
    assert roster["m1"].status == "active"


def test_replay_drops_removed_membership() -> None:
    events = [
        _evt(1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"),
        _evt(2, MembershipEventType.REMOVED, "m1", status_after="removed"),
    ]
    assert replay_roster(events) == {}  # leaver gone from the roster


def test_replay_keeps_suspended_member_with_status() -> None:
    events = [
        _evt(1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"),
        _evt(2, MembershipEventType.SUSPENDED, "m1", status_after="suspended"),
    ]
    roster = replay_roster(events)
    assert roster["m1"].status == "suspended"  # still has a grant, but paused


def test_replay_reprovisioned_identity_is_a_distinct_membership() -> None:
    events = [
        _evt(1, MembershipEventType.PROVISIONED, "m1", roles_after=["member"], status_after="active"),
        _evt(2, MembershipEventType.REMOVED, "m1", status_after="removed"),
        _evt(3, MembershipEventType.PROVISIONED, "m2", roles_after=["admin"], status_after="active"),
    ]
    roster = replay_roster(events)
    assert set(roster) == {"m2"}  # m1 removed; m2 is the new grant
    assert roster["m2"].roles == ["admin"]


def test_classify_jml_buckets_event_kinds() -> None:
    assert classify_jml(MembershipEventType.PROVISIONED) == "joiner"
    assert classify_jml(MembershipEventType.ROLE_CHANGED) == "mover"
    assert classify_jml(MembershipEventType.REACTIVATED) == "mover"
    assert classify_jml(MembershipEventType.SUSPENDED) == "leaver"
    assert classify_jml(MembershipEventType.REMOVED) == "leaver"


def test_control_map_covers_every_event_kind_and_the_roster() -> None:
    for kind in (
        MembershipEventType.PROVISIONED,
        MembershipEventType.ROLE_CHANGED,
        MembershipEventType.SUSPENDED,
        MembershipEventType.REACTIVATED,
        MembershipEventType.REMOVED,
    ):
        assert ACCESS_EVIDENCE_CONTROLS[kind]  # non-empty control list
    assert ACCESS_EVIDENCE_CONTROLS["roster"]  # the as-of access matrix maps too
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/unit/test_access_evidence.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.rbac.access_evidence'`

- [ ] **Step 3: Create the module**

```python
# src/dazzle/rbac/access_evidence.py
"""Access-evidence / access-review export (auth Plan 2b).

Turns the Plan 2a membership lifecycle substrate into auditor-ready evidence:
a per-org membership snapshot (current or point-in-time "as of date D",
reconstructed by replaying ``membership_events``), the Joiner/Mover/Leaver event
stream over a period, both mapped to SOC 2 / ISO 27001 controls (spec §6), and a
tamper-evidence attestation (the 2a hash-chain verification).

The membership table IS the per-org access matrix; the event stream IS every
access change. "Everyone with access to org X as of date D" and "every access
change in period P" are answered completely (not sampled) — exactly an auditor's
user-access-listing + access-review requests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from dazzle.http.runtime.auth.membership_events import MembershipEvent, MembershipEventType

# spec §6 — membership lifecycle event (and the roster itself) → control ids.
# SOC 2 CC6.x (logical access) + ISO 27001 A.5.15–18 (access control / identity /
# auth / access rights). The "roster" key maps the point-in-time access matrix.
ACCESS_EVIDENCE_CONTROLS: dict[str, list[str]] = {
    MembershipEventType.PROVISIONED: ["CC6.2", "A.5.16", "A.5.18"],  # joiner / grant
    MembershipEventType.ROLE_CHANGED: ["CC6.3", "A.5.18"],  # mover / access rights
    MembershipEventType.SUSPENDED: ["CC6.2", "CC6.3", "A.5.18"],  # leaver-ish
    MembershipEventType.REACTIVATED: ["CC6.3", "A.5.18"],  # mover
    MembershipEventType.REMOVED: ["CC6.2", "CC6.3", "A.5.18"],  # leaver / revoke
    "roster": ["CC6.1", "CC6.3", "A.5.15"],  # the as-of access matrix + review
}

_JML: dict[str, str] = {
    MembershipEventType.PROVISIONED: "joiner",
    MembershipEventType.ROLE_CHANGED: "mover",
    MembershipEventType.REACTIVATED: "mover",
    MembershipEventType.SUSPENDED: "leaver",
    MembershipEventType.REMOVED: "leaver",
}


def classify_jml(event_type: str) -> str:
    """Bucket a membership event kind into joiner / mover / leaver (or 'other')."""
    return _JML.get(event_type, "other")


@dataclass(frozen=True)
class MemberSnapshot:
    """One membership in a roster, as of the snapshot moment."""

    membership_id: str
    identity_id: str
    roles: list[str]
    status: str
    joined_at: str | None  # ISO-8601 (the provisioned event time, when replayed)


def replay_roster(events: list[MembershipEvent]) -> dict[str, MemberSnapshot]:
    """Reconstruct the roster (membership_id → MemberSnapshot) by replaying events.

    Pure: takes an already-time-filtered, seq-ordered event list and folds it.
    provisioned→add, role_changed→update roles, suspended/reactivated→status,
    removed→drop. Keyed by membership_id so a removed-then-reprovisioned identity
    is correctly two distinct grants.
    """
    roster: dict[str, MemberSnapshot] = {}
    for e in sorted(events, key=lambda x: (x.seq if x.seq is not None else 0)):
        mid = e.membership_id
        if e.event_type == MembershipEventType.PROVISIONED:
            roster[mid] = MemberSnapshot(
                membership_id=mid,
                identity_id=e.identity_id,
                roles=list(e.roles_after or []),
                status=e.status_after or "active",
                joined_at=e.created_at.isoformat() if e.created_at else None,
            )
        elif e.event_type == MembershipEventType.REMOVED:
            roster.pop(mid, None)
        elif mid in roster:
            cur = roster[mid]
            if e.event_type == MembershipEventType.ROLE_CHANGED:
                roster[mid] = MemberSnapshot(
                    mid, cur.identity_id, list(e.roles_after or []), cur.status, cur.joined_at
                )
            elif e.event_type in (
                MembershipEventType.SUSPENDED,
                MembershipEventType.REACTIVATED,
            ):
                roster[mid] = MemberSnapshot(
                    mid, cur.identity_id, cur.roles, e.status_after or cur.status, cur.joined_at
                )
    return roster


@dataclass(frozen=True)
class OrgAccessSnapshot:
    """Per-org membership roster at a moment (current or as-of)."""

    tenant_id: str
    as_of: str | None  # ISO-8601 cut-off; None = current state
    source: str  # "current" (memberships table) | "replay" (event stream)
    members: list[MemberSnapshot]


@dataclass(frozen=True)
class JmlEntry:
    """One access-change event, JML-classified, with its control mappings."""

    jml: str  # joiner | mover | leaver | other
    event_type: str
    membership_id: str
    identity_id: str
    roles_before: list[str] | None
    roles_after: list[str] | None
    status_before: str | None
    status_after: str | None
    actor_id: str | None
    reason: str | None
    at: str  # ISO-8601
    controls: list[str]


@dataclass(frozen=True)
class ChainAttestation:
    """Tamper-evidence attestation for the evidence (Plan 2a chain verify)."""

    ok: bool
    total_rows: int
    mismatched_count: int
    first_mismatch_id: str | None


@dataclass(frozen=True)
class AccessReview:
    """The full access-review evidence pack for one org."""

    tenant_id: str
    generated_at: str
    snapshot: OrgAccessSnapshot
    jml: list[JmlEntry]
    period_since: str | None
    period_until: str | None
    chain: ChainAttestation
    control_index: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-able dict (owner-attestable evidence artifact)."""
        return asdict(self)


def build_org_snapshot(
    store: Any, tenant_id: str, *, as_of: str | None = None
) -> OrgAccessSnapshot:
    """Build the roster: current memberships (as_of None) or a point-in-time replay.

    ``as_of`` is an ISO-8601 string; events with ``created_at <= as_of`` are
    replayed (the membership_events ``created_at`` is TEXT ISO-8601, lexically
    ordered). Current state reads the authoritative ``memberships`` table.
    """
    if as_of is None:
        members = [
            MemberSnapshot(
                membership_id=m.id,
                identity_id=m.identity_id,
                roles=list(m.roles),
                status=m.status,
                joined_at=m.joined_at.isoformat() if m.joined_at else None,
            )
            for m in store.get_memberships_for_tenant(tenant_id)
        ]
        return OrgAccessSnapshot(tenant_id, None, "current", members)

    events = store.get_membership_events(tenant_id=tenant_id, until=as_of)
    roster = replay_roster(events)
    return OrgAccessSnapshot(tenant_id, as_of, "replay", list(roster.values()))


def build_jml_stream(
    store: Any, tenant_id: str, *, since: str | None = None, until: str | None = None
) -> list[JmlEntry]:
    """The JML access-change stream for an org over a period (from 2a events)."""
    out: list[JmlEntry] = []
    for e in store.get_membership_events(tenant_id=tenant_id, since=since, until=until):
        out.append(
            JmlEntry(
                jml=classify_jml(e.event_type),
                event_type=e.event_type,
                membership_id=e.membership_id,
                identity_id=e.identity_id,
                roles_before=e.roles_before,
                roles_after=e.roles_after,
                status_before=e.status_before,
                status_after=e.status_after,
                actor_id=e.actor_id,
                reason=e.reason,
                at=e.created_at.isoformat() if e.created_at else "",
                controls=ACCESS_EVIDENCE_CONTROLS.get(e.event_type, []),
            )
        )
    return out


def build_access_review(
    store: Any,
    tenant_id: str,
    *,
    as_of: str | None = None,
    since: str | None = None,
    until: str | None = None,
    generated_at: str,
) -> AccessReview:
    """Assemble the full evidence pack: snapshot + JML stream + chain attestation.

    ``generated_at`` is passed in (callers stamp the wall-clock time) so this
    builder stays deterministic/testable.
    """
    snapshot = build_org_snapshot(store, tenant_id, as_of=as_of)
    jml = build_jml_stream(store, tenant_id, since=since, until=until)
    chain_result = store.verify_membership_event_chain()
    chain = ChainAttestation(
        ok=chain_result.ok,
        total_rows=chain_result.total_rows,
        mismatched_count=chain_result.mismatched_count,
        first_mismatch_id=chain_result.first_mismatch_id,
    )
    return AccessReview(
        tenant_id=tenant_id,
        generated_at=generated_at,
        snapshot=snapshot,
        jml=jml,
        period_since=since,
        period_until=until,
        chain=chain,
        control_index=dict(ACCESS_EVIDENCE_CONTROLS),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_access_evidence.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/rbac/access_evidence.py tests/unit/test_access_evidence.py --fix
ruff format src/dazzle/rbac/access_evidence.py tests/unit/test_access_evidence.py
git add src/dazzle/rbac/access_evidence.py tests/unit/test_access_evidence.py
git commit -m "feat(rbac): access-evidence builders — point-in-time roster + JML + control map (Plan 2b)"
```

---

## Task 3: Markdown renderer

**Files:**
- Modify: `src/dazzle/rbac/report.py` (add `render_access_review_markdown`)
- Test: `tests/unit/test_access_evidence.py` (extend with a render smoke test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_access_evidence.py`:

```python
def test_render_access_review_markdown_has_sections() -> None:
    from dazzle.rbac.access_evidence import (
        AccessReview,
        ChainAttestation,
        JmlEntry,
        MemberSnapshot,
        OrgAccessSnapshot,
    )
    from dazzle.rbac.report import render_access_review_markdown

    review = AccessReview(
        tenant_id="org-1",
        generated_at="2026-06-05T00:00:00+00:00",
        snapshot=OrgAccessSnapshot(
            "org-1", None, "current",
            [MemberSnapshot("m1", "u-1", ["admin"], "active", "2026-01-01T00:00:00+00:00")],
        ),
        jml=[
            JmlEntry("joiner", "provisioned", "m1", "u-1", None, ["admin"], None, "active",
                     "admin-1", None, "2026-01-01T00:00:00+00:00", ["CC6.2", "A.5.16"]),
        ],
        period_since=None,
        period_until=None,
        chain=ChainAttestation(ok=True, total_rows=1, mismatched_count=0, first_mismatch_id=None),
    )
    md = render_access_review_markdown(review)
    assert "# Access Review" in md
    assert "org-1" in md
    assert "## Membership Roster" in md
    assert "## Access Changes (Joiner / Mover / Leaver)" in md
    assert "## Control Coverage" in md
    assert "CC6.2" in md
    assert "Integrity" in md and "VERIFIED" in md  # chain ok → VERIFIED
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_access_evidence.py::test_render_access_review_markdown_has_sections -q`
Expected: FAIL — `ImportError: cannot import name 'render_access_review_markdown'`

- [ ] **Step 3: Add the renderer** to `src/dazzle/rbac/report.py` (end of file)

```python
def render_access_review_markdown(review: "AccessReview") -> str:  # noqa: F821
    """Render an access-review evidence pack to markdown (auth Plan 2b).

    Sections: roster (who has access + roles as of the snapshot moment), JML
    access-change stream, control coverage (which SOC 2 / ISO controls the
    evidence supports), and the tamper-evidence integrity attestation.
    """
    s = review.snapshot
    as_of = s.as_of or "now (current state)"
    lines: list[str] = [
        "# Access Review",
        "",
        f"- **Organization**: {review.tenant_id}",
        f"- **Generated**: {review.generated_at}",
        f"- **Snapshot as of**: {as_of} (source: {s.source})",
        f"- **Change period**: {review.period_since or '—'} → {review.period_until or '—'}",
        "",
        "## Membership Roster",
        "",
        f"_{len(s.members)} membership(s) with access to {review.tenant_id}._",
        "",
        "| membership | identity | roles | status | joined |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in sorted(s.members, key=lambda x: x.identity_id):
        roles = ", ".join(m.roles) if m.roles else "—"
        lines.append(
            f"| `{m.membership_id}` | {m.identity_id} | {roles} | {m.status} | {m.joined_at or '—'} |"
        )
    lines += [
        "",
        "## Access Changes (Joiner / Mover / Leaver)",
        "",
    ]
    if not review.jml:
        lines += ["_No access changes in the period._", ""]
    else:
        lines += [
            "| when | JML | event | identity | roles before → after | status | actor | controls |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for j in review.jml:
            rb = ", ".join(j.roles_before) if j.roles_before else "—"
            ra = ", ".join(j.roles_after) if j.roles_after else "—"
            st = f"{j.status_before or '—'} → {j.status_after or '—'}"
            lines.append(
                f"| {j.at} | {j.jml} | `{j.event_type}` | {j.identity_id} | {rb} → {ra} | "
                f"{st} | {j.actor_id or '—'} | {', '.join(j.controls)} |"
            )
        lines.append("")
    lines += ["## Control Coverage", "", "| control | evidence |", "| --- | --- |"]
    # Invert the control index: control id → the event kinds / roster that evidence it.
    control_to_sources: dict[str, list[str]] = {}
    for source, controls in review.control_index.items():
        for c in controls:
            control_to_sources.setdefault(c, []).append(source)
    for control in sorted(control_to_sources):
        lines.append(f"| **{control}** | {', '.join(sorted(control_to_sources[control]))} |")
    lines += [
        "",
        "## Evidence Integrity",
        "",
        (
            f"- **Tamper-evidence chain**: {'VERIFIED' if review.chain.ok else 'BROKEN'} "
            f"({review.chain.total_rows} event(s); {review.chain.mismatched_count} mismatch(es))"
        ),
    ]
    if not review.chain.ok:
        lines.append(f"- **First broken event**: `{review.chain.first_mismatch_id}`")
    lines.append("")
    return "\n".join(lines)
```

Add the `TYPE_CHECKING` import at the top of `report.py` (after the existing import line `from dazzle.rbac.verifier import CellResult, VerificationReport`):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.rbac.access_evidence import AccessReview
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_access_evidence.py::test_render_access_review_markdown_has_sections -q`
Expected: PASS

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/rbac/report.py tests/unit/test_access_evidence.py --fix
ruff format src/dazzle/rbac/report.py tests/unit/test_access_evidence.py
git add src/dazzle/rbac/report.py tests/unit/test_access_evidence.py
git commit -m "feat(rbac): render_access_review_markdown evidence pack (Plan 2b)"
```

---

## Task 4: `dazzle rbac access-review` CLI command

**Files:**
- Modify: `src/dazzle/cli/rbac.py` (add command, after `report_cmd` ~line 444)
- Test: `tests/integration/test_access_review_pg.py` (extend — exercise the builder end-to-end + JSON round-trip)

- [ ] **Step 1: Write the failing integration test**

Append to `tests/integration/test_access_review_pg.py`:

```python
def test_build_access_review_current_and_as_of(store_url: str) -> None:
    from dazzle.rbac.access_evidence import AccessReview, build_access_review

    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    store.update_membership_roles(m.id, ["member", "approver"], actor_id="admin-1")

    review = build_access_review(
        store, "org-1", generated_at="2026-06-05T00:00:00+00:00"
    )
    # Current roster reflects the latest roles; JML has the provision + role change.
    assert len(review.snapshot.members) == 1
    assert review.snapshot.members[0].roles == ["member", "approver"]
    assert [j.jml for j in review.jml] == ["joiner", "mover"]
    assert review.chain.ok is True
    # JSON round-trips (owner-attestable artifact).
    import json

    blob = json.dumps(review.to_dict())
    assert "org-1" in blob and "approver" in blob
    assert isinstance(review, AccessReview)


def test_access_review_as_of_excludes_later_changes(store_url: str) -> None:
    from dazzle.rbac.access_evidence import build_org_snapshot

    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    # An as-of date in the far past (before any event) → empty roster.
    snap = build_org_snapshot(store, "org-1", as_of="2020-01-01T00:00:00+00:00")
    assert snap.source == "replay"
    assert snap.members == []
    # An as-of date in the future → includes the membership.
    snap_now = build_org_snapshot(store, "org-1", as_of="2099-01-01T00:00:00+00:00")
    assert {mm.membership_id for mm in snap_now.members} == {m.id}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_access_review_pg.py -q`
Expected: the two new tests FAIL (builder produces wrong shape) until Task 2/3 are in — they pass once those land; this task adds the CLI. (If Task 2/3 already merged, these pass; run them to confirm before adding the CLI.)

- [ ] **Step 3: Add the CLI command** to `src/dazzle/cli/rbac.py` after `report_cmd`:

```python
@rbac_app.command("access-review")
def access_review_cmd(
    tenant: str = typer.Option(..., "--tenant", "-t", help="Organization (tenant) id"),
    as_of: str = typer.Option("", "--as-of", help="Roster as of ISO-8601 datetime (default: now)"),
    since: str = typer.Option("", "--since", help="JML change-period start (ISO-8601)"),
    until: str = typer.Option("", "--until", help="JML change-period end (ISO-8601)"),
    output_format: str = typer.Option("markdown", "--format", "-f", help="markdown | json"),
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
) -> None:
    """Generate an access-review evidence pack for an org (auth Plan 2b).

    Reads the live auth store: a membership roster (current, or point-in-time via
    --as-of), the Joiner/Mover/Leaver change stream over [--since, --until],
    SOC 2 / ISO 27001 control mappings, and a tamper-evidence attestation.
    """
    import json
    from datetime import UTC, datetime

    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.cli.db import _resolve_url
    from dazzle.rbac.access_evidence import build_access_review
    from dazzle.rbac.report import render_access_review_markdown

    url = _resolve_url(database_url)
    if not url:
        typer.echo("No database URL — set DATABASE_URL or pass --database-url.", err=True)
        raise typer.Exit(code=1)

    store = AuthStore(database_url=url)
    review = build_access_review(
        store,
        tenant,
        as_of=as_of or None,
        since=since or None,
        until=until or None,
        generated_at=datetime.now(UTC).isoformat(),
    )
    if output_format == "json":
        typer.echo(json.dumps(review.to_dict(), indent=2))
    else:
        typer.echo(render_access_review_markdown(review))
    # Non-zero exit if the evidence's own integrity chain is broken (audit signal).
    if not review.chain.ok:
        typer.echo(
            f"WARNING: membership_events tamper-evidence chain BROKEN "
            f"({review.chain.mismatched_count} mismatch(es))",
            err=True,
        )
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_access_review_pg.py -q`
Expected: PASS (all access-review tests)

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/cli/rbac.py tests/integration/test_access_review_pg.py --fix
ruff format src/dazzle/cli/rbac.py tests/integration/test_access_review_pg.py
git add src/dazzle/cli/rbac.py tests/integration/test_access_review_pg.py
git commit -m "feat(cli): dazzle rbac access-review command (Plan 2b)"
```

---

## Task 5: Full verification + regression

**Files:** none (verification only)

- [ ] **Step 1: mypy + full unit slice**

```bash
mypy src/dazzle
python -m pytest tests/ -m "not e2e" -q
```
Expected: mypy clean; full unit slice green. Watch the CLI-sweep / docs-drift tests — a new `dazzle rbac` subcommand may need a docs/help mention (`test_cli_sweep`, `test_docs_drift`). If one fails, add the command to the referenced doc/help index.

- [ ] **Step 2: access-review integration suite + rbac regression**

```bash
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" DATABASE_URL="postgresql://localhost:5432/postgres" \
  python -m pytest tests/integration/test_access_review_pg.py tests/integration/test_membership_events_pg.py -q
```
Expected: PASS.

- [ ] **Step 3: Manual smoke against a seeded app** (optional but recommended) — run `dazzle rbac access-review --tenant <a real org id> --format json` against a scratch DB seeded via the harness, confirm the JSON pack is well-formed.

- [ ] **Step 4: Commit any drift/regression fixes**

```bash
git add -A && git commit -m "test(rbac): adapt CLI/docs drift to access-review command (Plan 2b)"
```

---

## Task 6: Adversarial review checkpoint (MANDATORY — compliance-evidence integrity)

**Files:** none (review only)

- [ ] **Step 1: Dispatch an independent reviewer** over the 2b diff with this brief:
  - **Replay correctness**: does `replay_roster` faithfully reconstruct the roster for every event-order permutation? Off-by-one on the `as_of` cut-off (inclusive vs exclusive)? Does keying by `membership_id` correctly handle removed-then-reprovisioned, and an event for a membership whose `provisioned` is *before* the as-of window but a `role_changed` *after* (the provision must still be in-window for the member to appear)?
  - **Evidence completeness / honesty**: does the snapshot's `source` ("current" vs "replay") make the provenance explicit? Could a `current` snapshot and a replay-to-now diverge (silent inconsistency between the table and the event log)? Should the export flag that?
  - **Tamper-evidence surfacing**: is the chain attestation actually shown, and does a BROKEN chain produce a non-zero exit + visible warning (not silently rendered as a clean report)?
  - **Injection / input**: `--tenant`/`--as-of`/`--since`/`--until` flow into parameterised queries only? No SQL built from them?
  - **Silent failure**: does `build_access_review` swallow a DB error? Does an empty/garbage `as_of` string degrade safely or mis-filter?
  - **Control-map fidelity**: do the mappings match spec §6 (no over-claiming a control with no real evidence)?

- [ ] **Step 2: Fix any CRITICAL/HIGH inline; re-run suites. Record findings + fixes.**

- [ ] **Step 3: Commit hardening** — `git commit -m "fix(rbac): Plan 2b adversarial review hardening"`

---

## Task 7: CHANGELOG + ship

- [ ] **Step 1: CHANGELOG `[Unreleased]` `### Added`**:

```markdown
- **Auth Plan 2b — access-review evidence export** (plan `…auth-plan-2b-access-review-export.md`; spec §6). New `dazzle rbac access-review --tenant <org> [--as-of D] [--since D] [--until D] [--format markdown|json]` turns the Plan 2a membership lifecycle substrate into auditor-ready evidence: a per-org membership **roster** (current, or point-in-time "as of date D" reconstructed by replaying `membership_events`), the **Joiner/Mover/Leaver** access-change stream over a period, both **mapped to SOC 2 CC6.x / ISO 27001 A.5.15–18** controls, plus a **tamper-evidence attestation** (the 2a hash-chain verification; a broken chain exits non-zero). "Everyone with access to org X as of date D" and "every access change in period P" are answered completely, not sampled. New `src/dazzle/rbac/access_evidence.py` (pure replay/JML/control-map builders) + `render_access_review_markdown`; new `AuthStore.get_memberships_for_tenant`. Real-PG + pure-replay tests. **Plan 2 (compliance evidence) complete.**
```

Add a `### Agent Guidance` bullet: `dazzle rbac access-review` is the auditor export; point-in-time rosters come from event replay (needs 2a events present — run after memberships exist); a non-zero exit means the evidence chain is tampered. Control mappings live in `access_evidence.ACCESS_EVIDENCE_CONTROLS` (spec §6), not the taxonomy YAML.

- [ ] **Step 2: `/bump patch`, then `/ship`.**

---

## Self-Review

**1. Spec coverage (§6):** per-org membership snapshot → `build_org_snapshot` (current + as-of replay) ✓. "as of date D is a query" → point-in-time replay ✓. "every access change in period P is the event stream" → `build_jml_stream` over [since,until] ✓. JML = provision/role-change/deprovision → `classify_jml` ✓. mapped to controls → `ACCESS_EVIDENCE_CONTROLS` (CC6.1/6.2/6.3, A.5.15/16/18) ✓. "access reviews become a generated owner-attestable export" → markdown + JSON `to_dict` ✓. "extending the rbac compliance report" → renderer in `report.py`, command in `rbac` CLI ✓. tamper-evident → `ChainAttestation` surfaced + non-zero exit ✓. **Deferred (acknowledged):** Authenticate/session events + Privileged-use + Connection-lifecycle rows (those event sources aren't in 2a; a later slice), and the tail-truncation head-anchor (2a LOW).

**2. Placeholder scan:** every step has full code; tests have concrete assertions. No TBD. ✓

**3. Type consistency:** `MemberSnapshot`/`OrgAccessSnapshot`/`JmlEntry`/`ChainAttestation`/`AccessReview` fields match between definition (Task 2), renderer (Task 3), builder (Task 2), and tests. `build_access_review(generated_at=...)` keyword matches the CLI call. `MembershipEventType` constants reused from 2a. `verify_membership_event_chain()` returns the 2a `EventChainResult` whose `.ok/.total_rows/.mismatched_count/.first_mismatch_id` map into `ChainAttestation`. `get_membership_events(tenant_id=, since=, until=)` matches the 2a signature. ✓

**Open risk for execution:** the `as_of` replay relies on `get_membership_events(until=as_of)` filtering `created_at <= as_of` lexically — confirm ISO-8601 strings with the same offset compare correctly (they do; the substrate writes `datetime.now(UTC).isoformat()`, always `+00:00`). If callers pass a naive/different-offset `as_of`, document that it must be UTC ISO-8601.
