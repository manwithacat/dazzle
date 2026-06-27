"""#1495 follow-on (ADR-0047) — `dazzle inspect db-artifacts` lens over the registry."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dazzle.cli.inspect import inspect_app

runner = CliRunner()


def test_db_artifacts_text() -> None:
    res = runner.invoke(inspect_app, ["db-artifacts"])
    assert res.exit_code == 0
    assert "_dazzle_event_inbox" in res.stdout
    assert "{prefix}events" in res.stdout
    assert "framework_internal" in res.stdout


def test_db_artifacts_json() -> None:
    res = runner.invoke(inspect_app, ["db-artifacts", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    names = {a["name"] for a in payload["artifacts"]}
    assert "_dazzle_event_inbox" in names
    inbox = next(a for a in payload["artifacts"] if a["name"] == "_dazzle_event_inbox")
    assert inbox["boot_ddl_gated"] is True
    assert inbox["in_baseline"] is True


def test_db_artifacts_class_filter() -> None:
    res = runner.invoke(inspect_app, ["db-artifacts", "--class", "event_bus_transport", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    classes = {a["cls"] for a in payload["artifacts"]}
    assert classes == {"event_bus_transport"}


def test_db_artifacts_exposes_gating_fields() -> None:
    """The JSON surfaces the gating + tracked-debt fields per artifact. After the
    #1496-#1499 drain, refresh_tokens is gated and carries no debt; the
    known_ungated_issue field is present (None) so future debt is visible."""
    res = runner.invoke(inspect_app, ["db-artifacts", "--json"])
    payload = json.loads(res.stdout)
    rt = next(a for a in payload["artifacts"] if a["name"] == "refresh_tokens")
    assert rt["boot_ddl_gated"] is True
    assert rt["known_ungated_issue"] is None
    assert "known_ungated_issue" in rt  # field always present for future debt
