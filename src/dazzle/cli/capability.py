"""`dazzle capability` — manage opt-in feature capabilities (#1342)."""

import difflib
import re
import tomllib
from pathlib import Path

import typer

from dazzle.core.capabilities import (
    all_capabilities,
    get,
    is_available,
    known_capability_ids,
)

capability_app = typer.Typer(help="Manage opt-in feature capabilities.")


def _manifest_path() -> Path:
    p = Path.cwd() / "dazzle.toml"
    if not p.exists():
        typer.secho("No dazzle.toml in the current directory.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    return p


def _declared(path: Path) -> list[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return list(data.get("capabilities", {}).get("enabled", []))


def _write_enabled(path: Path, enabled: list[str]) -> None:
    """Rewrite the [capabilities] enabled list, preserving the rest of the file."""
    text = path.read_text(encoding="utf-8")
    rendered = "enabled = [" + ", ".join(f'"{c}"' for c in enabled) + "]"
    if "[capabilities]" in text:
        text = re.sub(r"enabled\s*=\s*\[[^\]]*\]", rendered, text, count=1)
    else:
        text = text.rstrip() + f"\n\n[capabilities]\n{rendered}\n"
    path.write_text(text, encoding="utf-8")


@capability_app.command("list")
def list_capabilities() -> None:
    """List every capability and its status."""
    path = Path.cwd() / "dazzle.toml"
    declared = set(_declared(path)) if path.exists() else set()
    for cap in all_capabilities():
        avail = is_available(cap)
        if cap.id in declared and avail:
            status = "active"
        elif cap.id in declared and not avail:
            status = f"DECLARED-BUT-UNAVAILABLE ({cap.remediation})"
        elif avail:
            status = "dormant (available, not enabled)"
        else:
            status = "unavailable (not enabled)"
        typer.echo(f"{cap.id:28} {cap.label:32} {status}")


@capability_app.command("enable")
def enable(capability_id: str) -> None:
    """Enable a capability: append to [capabilities] + print the activation runbook."""
    if capability_id not in known_capability_ids():
        hint = difflib.get_close_matches(capability_id, sorted(known_capability_ids()), n=1)
        suffix = f" Did you mean '{hint[0]}'?" if hint else ""
        typer.secho(f"Unknown capability '{capability_id}'.{suffix}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    path = _manifest_path()
    declared = _declared(path)
    if capability_id not in declared:
        declared.append(capability_id)
        _write_enabled(path, declared)
        typer.secho(f"✓ Enabled {capability_id}", fg=typer.colors.GREEN)
    else:
        typer.echo(f"{capability_id} already enabled.")

    cap = get(capability_id)
    assert cap is not None
    if not is_available(cap):
        typer.secho(f"\nNot installed yet — {cap.remediation}", fg=typer.colors.YELLOW)
    typer.echo(
        "\nActivation runbook:\n"
        f"  1. {cap.remediation}\n"
        "  2. Configure the connection: `dazzle auth connection create …` "
        "(see docs/reference/enterprise-sso.md)\n"
        "  3. Set DAZZLE_CONNECTION_SECRET for encrypted secret storage.\n"
        "  4. Verify readiness: `dazzle auth connection doctor <id>`."
    )


@capability_app.command("disable")
def disable(capability_id: str) -> None:
    """Remove a capability from [capabilities]."""
    path = _manifest_path()
    declared = _declared(path)
    if capability_id in declared:
        declared.remove(capability_id)
        _write_enabled(path, declared)
        typer.secho(f"✓ Disabled {capability_id}", fg=typer.colors.GREEN)
    else:
        typer.echo(f"{capability_id} was not enabled.")
