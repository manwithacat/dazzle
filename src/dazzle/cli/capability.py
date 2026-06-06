"""`dazzle capability` — manage opt-in feature capabilities (#1342)."""

import re
import tomllib
from pathlib import Path

import typer

from dazzle.core.capabilities import (
    all_capabilities,
    get,
    is_available,
    known_capability_ids,
    suggest_capability,
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
    """Set the ``enabled`` list inside the ``[capabilities]`` table, preserving the
    rest of the file (comments included).

    Section-aware: only an ``enabled =`` line *within* the ``[capabilities]`` table
    is touched (never one in another table). If the table exists without an
    ``enabled`` key, the key is inserted under its header; if the table is absent,
    it is appended.
    """
    rendered = "enabled = [" + ", ".join(f'"{c}"' for c in enabled) + "]"
    lines = path.read_text(encoding="utf-8").splitlines()

    header = next((i for i, ln in enumerate(lines) if ln.strip() == "[capabilities]"), None)
    if header is None:
        text = "\n".join(lines).rstrip() + f"\n\n[capabilities]\n{rendered}\n"
        path.write_text(text, encoding="utf-8")
        return

    # Scan the section body (until the next table header or EOF).
    body_end = header + 1
    while body_end < len(lines) and not lines[body_end].lstrip().startswith("["):
        body_end += 1
    for i in range(header + 1, body_end):
        if re.match(r"\s*enabled\s*=", lines[i]):
            lines[i] = rendered  # replace the existing key
            break
    else:
        lines.insert(header + 1, rendered)  # section present, no enabled key
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        hint = suggest_capability(capability_id)
        suffix = f" Did you mean '{hint}'?" if hint else ""
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
