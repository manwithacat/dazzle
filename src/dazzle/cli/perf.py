"""``dazzle perf`` Typer sub-app."""

from __future__ import annotations

import typer

from dazzle.cli.perf_impl.list import list_command
from dazzle.cli.perf_impl.show import show_command
from dazzle.cli.perf_impl.trace import trace_command

perf_app = typer.Typer(help="On-demand local OpenTelemetry tracing.")
perf_app.command(name="list")(list_command)
perf_app.command(name="show")(show_command)
perf_app.command(name="trace")(trace_command)
