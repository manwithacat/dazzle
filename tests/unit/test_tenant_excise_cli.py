"""The excise CLI refuses a non-test org without --force (RLS Phase E.1)."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from dazzle.cli.tenant import excise_command


def test_excise_refuses_non_test_org_without_force() -> None:
    fake_conn = MagicMock()
    fake_conn.execute.return_value.fetchone.return_value = (False, "prod")
    with (
        patch(
            "dazzle.cli.tenant._excise_context",
            return_value=(MagicMock(), "postgresql://x"),
        ),
        patch("psycopg.connect") as pc,
    ):
        pc.return_value.__enter__.return_value = fake_conn
        with pytest.raises(typer.Exit) as exc:
            excise_command(tenant_id="prod-org", dry_run=False, force=False, database_url="")
    assert exc.value.exit_code == 2
