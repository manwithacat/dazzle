"""Backup and restore commands for Dazzle projects (#441)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import typer

from dazzle.core.manifest import load_manifest

backup_app = typer.Typer(help="Backup and restore project data.")


def _resolve_database_url(manifest_path: Path) -> str:
    """Resolve DATABASE_URL from env or manifest."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        try:
            mf = load_manifest(manifest_path)
            url = mf.database.url
            if url.startswith("env:"):
                url = os.environ.get(url[4:], "")
        except Exception:
            pass
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _parse_pg_url(url: str) -> dict[str, str]:
    """Parse a PostgreSQL URL into components for pg_dump/pg_restore."""
    parsed = urlparse(url)
    result: dict[str, str] = {}
    if parsed.hostname:
        result["host"] = parsed.hostname
    if parsed.port:
        result["port"] = str(parsed.port)
    if parsed.username:
        result["username"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password
    if parsed.path and parsed.path != "/":
        result["dbname"] = parsed.path.lstrip("/")
    return result


def _build_pg_env(pg: dict[str, str]) -> dict[str, str]:
    """Build environment dict with PGPASSWORD set."""
    env = os.environ.copy()
    if "password" in pg:
        env["PGPASSWORD"] = pg["password"]
    return env


def _build_pg_args(pg: dict[str, str]) -> list[str]:
    """Build common pg_dump/pg_restore connection args."""
    args: list[str] = []
    if "host" in pg:
        args.extend(["--host", pg["host"]])
    if "port" in pg:
        args.extend(["--port", pg["port"]])
    if "username" in pg:
        args.extend(["--username", pg["username"]])
    if "dbname" in pg:
        args.append(pg["dbname"])
    return args


@backup_app.command(name="create")
def backup_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
    data_only: bool = typer.Option(False, "--data-only", help="Skip uploads directory"),
    fmt: str = typer.Option("custom", "--format", "-f", help="pg_dump format: custom or plain"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be backed up"),
) -> None:
    """Create a backup of the project database and uploads."""
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    database_url = _resolve_database_url(manifest_path)
    if not database_url:
        typer.echo("ERROR: No DATABASE_URL found. Set it in environment or dazzle.toml.", err=True)
        raise typer.Exit(code=1)

    # Load project info
    project_name = "dazzle"
    framework_version = "unknown"
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
        framework_version = mf.version
    except Exception:
        pass

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    uploads_dir = project_root / "uploads"
    has_uploads = uploads_dir.is_dir() and any(uploads_dir.iterdir()) and not data_only

    if dry_run:
        typer.echo("Backup dry run:")
        typer.echo(f"  Project:   {project_name}")
        typer.echo(f"  Database:  {database_url[:40]}...")
        typer.echo(f"  Format:    {fmt}")
        typer.echo(f"  Uploads:   {'yes' if has_uploads else 'no (skipped)'}")
        typer.echo(f"  Output:    backup-{project_name}-{timestamp}.tar.gz")
        return

    # Check pg_dump is available
    if not shutil.which("pg_dump"):
        typer.echo("ERROR: pg_dump not found. Install PostgreSQL client tools.", err=True)
        raise typer.Exit(code=1)

    pg = _parse_pg_url(database_url)
    env = _build_pg_env(pg)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Run pg_dump
        dump_file = tmp / "database.dump"
        dump_format = "c" if fmt == "custom" else "p"
        cmd = [
            "pg_dump",
            "--data-only",
            f"--format={dump_format}",
            f"--file={dump_file}",
            *_build_pg_args(pg),
        ]
        typer.echo("Dumping database...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            typer.echo(f"ERROR: pg_dump failed: {result.stderr}", err=True)
            raise typer.Exit(code=1)

        # Copy uploads if present
        if has_uploads:
            typer.echo("Copying uploads...")
            shutil.copytree(uploads_dir, tmp / "uploads")

        # Write metadata
        metadata: dict[str, Any] = {
            "project_name": project_name,
            "framework_version": framework_version,
            "timestamp": datetime.now(UTC).isoformat(),
            "format": fmt,
            "has_uploads": has_uploads,
        }
        (tmp / "metadata.json").write_text(json.dumps(metadata, indent=2))

        # Package into tar.gz
        if output:
            archive_path = output
        else:
            archive_path = Path(f"backup-{project_name}-{timestamp}.tar.gz")

        with tarfile.open(archive_path, "w:gz") as tar:
            for item in tmp.iterdir():
                tar.add(item, arcname=item.name)

        typer.echo(f"Backup created: {archive_path}")
        typer.echo(f"  Size: {archive_path.stat().st_size / 1024:.0f} KB")


@backup_app.command(name="restore")
def restore_command(
    from_path: Path = typer.Option(..., "--from", help="Backup archive to restore from"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be restored"),
) -> None:
    """Restore a project from a backup archive."""
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    if not from_path.exists():
        typer.echo(f"ERROR: Backup file not found: {from_path}", err=True)
        raise typer.Exit(code=1)

    database_url = _resolve_database_url(manifest_path)
    if not database_url:
        typer.echo("ERROR: No DATABASE_URL found. Set it in environment or dazzle.toml.", err=True)
        raise typer.Exit(code=1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Extract archive
        with tarfile.open(from_path, "r:gz") as tar:
            tar.extractall(tmp)

        # Read metadata
        meta_path = tmp / "metadata.json"
        if not meta_path.exists():
            typer.echo("ERROR: Invalid backup archive (missing metadata.json)", err=True)
            raise typer.Exit(code=1)

        metadata = json.loads(meta_path.read_text())

        if dry_run:
            typer.echo("Restore dry run:")
            typer.echo(f"  Backup from:   {metadata.get('timestamp', 'unknown')}")
            typer.echo(f"  Project:       {metadata.get('project_name', 'unknown')}")
            typer.echo(f"  Version:       {metadata.get('framework_version', 'unknown')}")
            typer.echo(f"  Format:        {metadata.get('format', 'unknown')}")
            typer.echo(f"  Has uploads:   {metadata.get('has_uploads', False)}")
            typer.echo(f"  Target DB:     {database_url[:40]}...")
            return

        # Check tools
        dump_file = tmp / "database.dump"
        fmt = metadata.get("format", "custom")

        if fmt == "custom":
            tool = "pg_restore"
            if not shutil.which(tool):
                typer.echo(f"ERROR: {tool} not found. Install PostgreSQL client tools.", err=True)
                raise typer.Exit(code=1)
        else:
            tool = "psql"
            if not shutil.which(tool):
                typer.echo(f"ERROR: {tool} not found. Install PostgreSQL client tools.", err=True)
                raise typer.Exit(code=1)

        pg = _parse_pg_url(database_url)
        env = _build_pg_env(pg)

        # Restore database
        typer.echo("Restoring database...")
        if fmt == "custom":
            cmd = [
                "pg_restore",
                "--data-only",
                "--no-owner",
                "--no-privileges",
                str(dump_file),
                *[arg for arg in ["--dbname", pg.get("dbname", "")] if pg.get("dbname")],
            ]
            # Add connection args (without dbname which is in --dbname)
            if "host" in pg:
                cmd.extend(["--host", pg["host"]])
            if "port" in pg:
                cmd.extend(["--port", pg["port"]])
            if "username" in pg:
                cmd.extend(["--username", pg["username"]])
        else:
            cmd = ["psql", *_build_pg_args(pg), "-f", str(dump_file)]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            typer.echo(f"WARNING: Restore had issues: {result.stderr}", err=True)

        # Restore uploads
        uploads_src = tmp / "uploads"
        if uploads_src.is_dir():
            uploads_dst = project_root / "uploads"
            typer.echo("Restoring uploads...")
            if uploads_dst.exists():
                shutil.rmtree(uploads_dst)
            shutil.copytree(uploads_src, uploads_dst)

        typer.echo("Restore complete.")
