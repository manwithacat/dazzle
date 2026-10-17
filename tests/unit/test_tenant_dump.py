"""Pure helpers + CLI refusal matrix of the tenant-aware dump (#1788).

The real-Postgres proof (bound dumps, sectioned restore, recount) is
``tests/integration/test_tenant_dump_pg.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.cli.db import db_app
from dazzle.db.tenant_dump import (
    GLOBAL_TENANT,
    MANIFEST_NAME,
    DumpError,
    DumpManifest,
    DumpPosture,
    DumpRefusal,
    RestoreCheckResult,
    TenantEntry,
    assert_argv_clean,
    classify_tables,
    compare_counts,
    dump_file_names,
    dump_refusal,
    filter_toc,
    pg_client_env,
    pg_dump_argv,
    read_manifest,
    registry_postures,
    same_database,
)

runner = CliRunner()

_URL = "postgresql://app:s3cret-pw@db.example.test:5433/appdb?sslmode=require"
_T1 = "11111111-1111-1111-1111-111111111111"
_T2 = "22222222-2222-2222-2222-222222222222"

# Captured from `pg_restore -l` of a tenant_rls fixture dump (pg_dump 18.6, server 17).
_TOC = """\
;
; Archive created at 2026-10-17 04:27:54 BST
;     Format: CUSTOM
;
; Selected TOC Entries:
;
219; 1259 12434636 TABLE public Member dazzle_owner
217; 1259 12434620 TABLE public Workspace dazzle_owner
227; 1259 12434769 SEQUENCE public membership_events_seq_seq dazzle_owner
4038; 0 12434627 TABLE DATA public DeployHistory dazzle_owner
4039; 0 12434636 TABLE DATA public Member dazzle_owner
4041; 0 12434672 TABLE DATA public Project dazzle_owner
4037; 0 12434620 TABLE DATA public Workspace dazzle_owner
4046; 0 12434757 TABLE DATA public organizations dazzle_owner
4043; 0 12434715 TABLE DATA public users dazzle_owner
4065; 0 0 SEQUENCE SET public membership_events_seq_seq dazzle_owner
3869; 2606 12434648 FK CONSTRAINT public Member Member_tenant_id_fkey dazzle_owner
4024; 0 12434636 ROW SECURITY public Member dazzle_owner
4029; 3256 12434885 POLICY public Project scope_select dazzle_owner
""".splitlines()


# ── classification ──────────────────────────────────────────────────────


def _classify(live: dict[str, tuple[bool, bool]]):
    return classify_tables(
        live,
        scoped={"Member", "Project"},
        app_entities={"Member", "Project", "Workspace"},
        registry=registry_postures(),
    )


def test_classification_splits_fenced_and_reports_unaccounted() -> None:
    result = _classify(
        {
            "Member": (True, True),
            "Project": (True, True),
            "Workspace": (False, False),
            "organizations": (False, False),
            "alembic_version": (False, False),
            "legacy_import": (False, False),
        }
    )
    assert result.rls_tables == ["Member", "Project"]
    assert result.non_rls_tables == [
        "Workspace",
        "alembic_version",
        "legacy_import",
        "organizations",
    ]
    assert result.unaccounted == ["legacy_import"]


@pytest.mark.parametrize(
    ("live", "needle"),
    [
        ({"Member": (True, False)}, "Member: tenant-scoped in the DSL"),
        ({"Member": (False, False)}, "Member: tenant-scoped in the DSL"),
        ({"Workspace": (True, True)}, "Workspace: RLS is enabled live but"),
        ({"users": (True, True)}, "registry posture non_fenced"),
    ],
)
def test_classification_refuses_posture_disagreement(
    live: dict[str, tuple[bool, bool]], needle: str
) -> None:
    with pytest.raises(DumpRefusal, match=needle):
        _classify(live)


def test_registry_postures_cover_the_tenant_source() -> None:
    assert registry_postures()["organizations"] == "non_fenced"


# ── refusal matrix, file naming, identity ───────────────────────────────


@pytest.mark.parametrize(
    ("bypass", "role", "tenants", "needle"),
    [
        (True, None, 2, "the connected role is a superuser"),
        (True, "app_backup", 2, "role 'app_backup' is a superuser"),
        (False, None, 0, "no tenants"),
        (False, None, 2, None),
        (False, "app_backup", 1, None),
    ],
)
def test_dump_refusal_matrix(bypass: bool, role: str | None, tenants: int, needle: str | None):
    reason = dump_refusal(role_bypasses=bypass, role=role, tenant_count=tenants)
    if needle is None:
        assert reason is None
    else:
        assert reason is not None and needle in reason


def test_dump_file_names_sanitise_and_deduplicate() -> None:
    names = dump_file_names(
        [(_T1, "Acme Ltd/../x"), (_T2, "Acme Ltd/../x"), ("t3", None), ("t4", "manifest")]
    )
    assert names == {
        _T1: "Acme-Ltd-..-x.dump",
        _T2: f"{_T2}.dump",
        "t3": "t3.dump",
        "t4": "t4.dump",
    }


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        (("localhost", "app"), ("127.0.0.1", "app"), True),
        (("", "app"), ("/tmp", "app"), True),
        (("DB.example", "app"), ("db.example", "app"), True),
        (("localhost", "app"), ("localhost", "app_restore"), False),
        (("db1", "app"), ("db2", "app"), False),
    ],
)
def test_same_database(a: tuple[str, str], b: tuple[str, str], same: bool) -> None:
    assert same_database(a, b) is same


@pytest.mark.parametrize(
    ("forced", "bypass", "blocked"),
    [(["Member"], False, True), (["Member"], True, False), ([], False, False)],
)
def test_dump_posture_blocked(forced: list[str], bypass: bool, blocked: bool) -> None:
    assert DumpPosture(forced_tables=forced, role_bypasses_rls=bypass).plain_dump_blocked is blocked


# ── TOC filter ──────────────────────────────────────────────────────────


def _toc_names(lines: list[str]) -> list[str]:
    return [" ".join(line.split()[3:-1]) for line in lines]


def test_first_dump_loads_all_data_and_sequences() -> None:
    keep = filter_toc(_TOC, rls_tables=["Member", "Project"], first=True)
    assert _toc_names(keep) == [
        "TABLE DATA public DeployHistory",
        "TABLE DATA public Member",
        "TABLE DATA public Project",
        "TABLE DATA public Workspace",
        "TABLE DATA public organizations",
        "TABLE DATA public users",
        "SEQUENCE SET public membership_events_seq_seq",
    ]


def test_other_dumps_load_only_fenced_table_data() -> None:
    keep = filter_toc(_TOC, rls_tables=["Member", "Project"], first=False)
    assert _toc_names(keep) == ["TABLE DATA public Member", "TABLE DATA public Project"]


# ── manifest compare + files ────────────────────────────────────────────


def _manifest(**over: object) -> DumpManifest:
    data: dict[str, object] = {
        "label": "nightly",
        "created_at": "2026-10-17T00:00:00Z",
        "dazzle_version": "0.120.0",
        "alembic_version": "abc123",
        "source_host": "db.example.test",
        "source_dbname": "appdb",
        "pg_server_version": "17.11",
        "pg_dump_version": "pg_dump (PostgreSQL) 18.6",
        "partition_key": "tenant_id",
        "tenant_entity": "Workspace",
        "tenants": [TenantEntry(id=_T1, slug="a", file="a.dump")],
        "rls_tables": ["Member"],
        "non_rls_tables": ["users"],
        "counts": {_T1: {"Member": 2}},
        "globals": {"users": 5},
        "files": {"a.dump": 3},
    }
    data.update(over)
    return DumpManifest.model_validate(data)


@pytest.mark.parametrize(
    ("counts", "globals_", "expected"),
    [
        ({_T1: {"Member": 2}}, {"users": 5}, []),
        ({_T1: {"Member": 0}}, {"users": 5}, [("Member", _T1, 2, 0)]),
        ({}, {}, [("Member", _T1, 2, None), ("users", GLOBAL_TENANT, 5, None)]),
    ],
)
def test_compare_counts(counts, globals_, expected) -> None:
    got = compare_counts(_manifest(), counts, globals_)
    assert [(m.table, m.tenant, m.expected, m.actual) for m in got] == expected


def test_read_manifest_checks_completeness(tmp_path: Path) -> None:
    with pytest.raises(DumpRefusal, match="no manifest.json"):
        read_manifest(tmp_path)
    (tmp_path / MANIFEST_NAME).write_text(_manifest().model_dump_json())
    with pytest.raises(DumpError, match="a.dump is missing"):
        read_manifest(tmp_path)
    (tmp_path / "a.dump").write_bytes(b"abc")
    assert read_manifest(tmp_path).label == "nightly"


# ── client env / argv: the URL never reaches a command line ─────────────


def test_env_carries_connection_and_binding_never_argv(tmp_path: Path) -> None:
    env = pg_client_env(
        {"PATH": "/bin", "PGHOST": "stale", "PGOPTIONS": "-c x=1"},
        _URL,
        tenant_id=_T1,
        role="app_backup",
    )
    assert env["PGHOST"] == "db.example.test"
    assert env["PGPORT"] == "5433"
    assert env["PGDATABASE"] == "appdb"
    assert env["PGUSER"] == "app"
    assert env["PGPASSWORD"] == "s3cret-pw"
    assert env["PGSSLMODE"] == "require"
    assert env["PGOPTIONS"] == f"-c dazzle.tenant_id={_T1} -c role=app_backup"
    assert env["PATH"] == "/bin"

    argv = pg_dump_argv(None, tmp_path / "a.dump", "00000003-1")
    assert "--enable-row-security" in argv and "--snapshot=00000003-1" in argv
    assert_argv_clean(argv, _URL)
    assert not any("s3cret" in a or "db.example" in a for a in argv)
    with pytest.raises(DumpError, match="credentials"):
        assert_argv_clean([*argv, _URL], _URL)
    with pytest.raises(DumpError, match="credentials"):
        assert_argv_clean([*argv, "--password=s3cret-pw"], _URL)


@pytest.mark.parametrize(
    ("url", "kwargs", "needle"),
    [
        (_URL, {"tenant_id": "x -c role=postgres"}, "invalid tenant id"),
        (_URL, {"role": "x; DROP"}, "invalid role"),
        (_URL + "&options=-c%20row_security%3Doff", {}, "must not carry 'options'"),
    ],
)
def test_env_rejects_option_smuggling(url: str, kwargs: dict[str, str], needle: str) -> None:
    with pytest.raises(DumpError, match=needle):
        pg_client_env({}, url, **kwargs)


# ── CLI refusal matrix (DB calls stubbed) ───────────────────────────────


def _appspec(shared: bool) -> MagicMock:
    from dazzle.core.ir import TenancyMode

    appspec = MagicMock()
    if shared:
        appspec.tenancy.isolation.mode = TenancyMode.SHARED_SCHEMA
    else:
        appspec.tenancy = None
    appspec.domain.entities = []
    return appspec


@pytest.mark.parametrize(
    ("shared", "drift", "run_effect", "code", "needle"),
    [
        (False, [], None, 2, "no row-level tenancy"),
        (True, [{"entity": "Member", "issues": ["RLS not forced"]}], None, 2, "drifted"),
        (True, [], DumpRefusal("the connected role is a superuser"), 2, "superuser"),
        (True, [], DumpRefusal("no tenants in `organizations`"), 2, "no tenants"),
        (True, [], DumpError("pg_dump for tenant x failed"), 1, "failed"),
    ],
)
def test_dump_cli_refusals(
    tmp_path: Path, shared: bool, drift: list, run_effect: Exception | None, code: int, needle: str
) -> None:
    with (
        patch("dazzle.cli.db.load_project_appspec", return_value=_appspec(shared)),
        patch("dazzle.cli.db._resolve_url", return_value=_URL),
        patch("dazzle.cli.db._live_rls_drift", return_value=drift),
        patch("dazzle.cli.db.run_dump", side_effect=run_effect) as run_dump,
    ):
        result = runner.invoke(db_app, ["dump", "--out", str(tmp_path)])
    assert result.exit_code == code, result.output
    assert needle in result.output
    assert run_dump.called is (run_effect is not None)


@pytest.mark.parametrize(
    ("effect", "code", "needle"),
    [
        (DumpRefusal("the target is the dump's source database"), 2, "source database"),
        (DumpRefusal("the target already has 3 table(s)"), 2, "3 table(s)"),
        (DumpError("pg_restore data from a.dump failed"), 1, "failed"),
        (
            RestoreCheckResult(
                label="n",
                checks=2,
                rows=1,
                steps=[],
                mismatches=compare_counts(_manifest(), {}, {}),
            ),
            1,
            "2 of 2 counts differ",
        ),
        (RestoreCheckResult(label="n", checks=2, rows=7, steps=[], mismatches=[]), 0, "match"),
    ],
)
def test_restore_check_cli_exit_codes(tmp_path: Path, effect: object, code: int, needle: str):
    kwargs = {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect}
    with patch("dazzle.cli.db.run_restore_check", **kwargs):
        result = runner.invoke(
            db_app, ["restore-check", "--from", str(tmp_path), "--target-url", _URL]
        )
    assert result.exit_code == code, result.output
    assert needle in result.output


@pytest.mark.parametrize("command", ["snapshot", "restore"])
def test_plain_snapshot_refuses_under_filtered_force_rls(tmp_path: Path, command: str) -> None:
    posture = DumpPosture(forced_tables=["Member"], role_bypasses_rls=False)

    def _run(coro):  # consume the coroutine handed to asyncio.run
        coro.close()
        return posture

    with patch("dazzle.cli.db.asyncio.run", side_effect=_run):
        result = runner.invoke(
            db_app, [command, "pre", "--database-url", _URL, "--project", str(tmp_path)]
        )
    assert result.exit_code == 2, result.output
    assert "dazzle db dump" in result.output
