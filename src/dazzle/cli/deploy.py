"""
Deployment commands for DAZZLE CLI.

Commands for generating and managing AWS CDK infrastructure code.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

deploy_app = typer.Typer(
    help="Generate and manage AWS infrastructure",
    no_args_is_help=True,
)

console = Console()


def _load_spec(project_dir: Path) -> AppSpec:
    """Load and parse the AppSpec from a project directory."""
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    # Load manifest and discover DSL files
    manifest_path = (project_dir / "dazzle.toml").resolve()
    root = manifest_path.parent
    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(root, manifest)

    if not dsl_files:
        console.print("[red]No DSL files found in project[/red]")
        raise typer.Exit(1)

    modules = parse_modules(dsl_files)
    spec = build_appspec(modules, manifest.project_root)

    return spec


@deploy_app.command(name="generate")
def deploy_generate(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--project",
            "-p",
            help="Project directory containing DSL files",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for generated CDK code",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Preview what would be generated without writing files",
        ),
    ] = False,
) -> None:
    """
    Generate AWS CDK code from DAZZLE specification.

    This command analyzes your DSL files and generates standalone AWS CDK
    Python code that can deploy your application to AWS.

    Example:
        dazzle deploy generate --project ./my-app
        cd my-app/infra && cdk deploy --all
    """
    from dazzle.deploy import DeploymentRunner
    from dazzle.deploy.config import load_deployment_config

    console.print("\n[bold]Dazzle Deploy[/bold] - Generating AWS CDK code\n")

    # Load AppSpec
    with console.status("Parsing DSL files..."):
        spec = _load_spec(project_dir)

    console.print(f"  App: [cyan]{spec.name}[/cyan]")
    console.print(f"  Entities: {len(spec.domain.entities)}")
    console.print(f"  Channels: {len(spec.channels)}")
    console.print()

    # Load config
    config = load_deployment_config(project_dir / "dazzle.toml")

    if output:
        config.output.directory = str(output)

    # Create runner
    runner = DeploymentRunner(spec, project_dir, config)

    # Show plan
    console.print("[bold]Infrastructure Plan:[/bold]\n")
    plan = runner.plan()

    # Show requirements table
    reqs_table = Table(title="AWS Services")
    reqs_table.add_column("Service", style="cyan")
    reqs_table.add_column("Required", style="green")

    reqs = plan["requirements"]
    reqs_table.add_row("VPC", "Yes" if reqs["vpc"] else "No")
    reqs_table.add_row("ECS Fargate", "Yes" if reqs["ecs"] else "No")
    reqs_table.add_row("RDS PostgreSQL", "Yes" if reqs["rds"] else "No")
    reqs_table.add_row("S3", "Yes" if reqs["s3"] else "No")
    reqs_table.add_row("SQS", "Yes" if reqs["sqs"] else "No")
    reqs_table.add_row("EventBridge", "Yes" if reqs["eventbridge"] else "No")
    reqs_table.add_row("TigerBeetle (EC2)", "Yes" if reqs.get("tigerbeetle") else "No")
    reqs_table.add_row("CloudWatch", "Yes")

    console.print(reqs_table)
    console.print()

    # Show stacks
    console.print("[bold]Stacks to generate:[/bold]")
    for stack in plan["stacks"]:
        console.print(f"  - {stack}")
    console.print()

    if dry_run:
        console.print("[yellow]DRY RUN - No files will be written[/yellow]\n")
        result = runner.run(dry_run=True)

        console.print("[bold]Would generate:[/bold]")
        for f in result.artifacts.get("estimated_files", []):
            console.print(f"  - {f}")
        return

    # Generate
    with console.status("Generating CDK code..."):
        result = runner.run()

    if not result.success:
        console.print("\n[red]Generation failed:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)

    # Show results
    console.print(
        Panel(
            f"[green]Generated {len(result.files_created)} files[/green]\n\n"
            f"Output: [cyan]{runner.output_dir}[/cyan]\n"
            f"Stacks: {', '.join(result.stacks_generated)}",
            title="Success",
        )
    )

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. cd {runner.output_dir}")
    console.print("  2. pip install -r requirements.txt")
    console.print("  3. cdk bootstrap  # First time only")
    console.print("  4. cdk deploy --all")


@deploy_app.command(name="plan")
def deploy_plan(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--project",
            "-p",
            help="Project directory containing DSL files",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
) -> None:
    """
    Preview infrastructure requirements without generating code.

    Shows what AWS resources would be created based on your DSL.
    """
    from dazzle.deploy import DeploymentRunner
    from dazzle.deploy.config import load_deployment_config

    console.print("\n[bold]Dazzle Deploy[/bold] - Infrastructure Plan\n")

    # Load AppSpec
    with console.status("Parsing DSL files..."):
        spec = _load_spec(project_dir)

    # Load config
    config = load_deployment_config(project_dir / "dazzle.toml")

    # Create runner
    runner = DeploymentRunner(spec, project_dir, config)
    plan = runner.plan()

    # Show app info
    console.print(f"  App: [cyan]{plan['app_name']}[/cyan]")
    console.print(f"  Environment: [yellow]{plan['environment']}[/yellow]")
    console.print(f"  Region: [blue]{plan['region']}[/blue]")
    console.print()

    # Show compute config
    compute = plan["config"]["compute"]
    console.print("[bold]Compute Configuration:[/bold]")
    console.print(f"  Size: {compute['size']} ({compute['cpu']} CPU, {compute['memory']}MB)")
    console.print(f"  Capacity: {compute['min_capacity']} - {compute['max_capacity']} tasks")
    console.print(f"  Spot: {'Yes' if compute['use_spot'] else 'No'}")
    console.print()

    # Show database config
    db = plan["config"]["database"]
    console.print("[bold]Database Configuration:[/bold]")
    console.print(f"  Size: {db['size']}")
    console.print(f"  Multi-AZ: {'Yes' if db['multi_az'] else 'No'}")
    console.print()

    # Show requirements
    reqs = plan["requirements"]
    console.print("[bold]AWS Services Required:[/bold]")

    services = [
        ("VPC", reqs["vpc"]),
        ("ECS Fargate", reqs["ecs"]),
        ("ECR", reqs["ecr"]),
        ("RDS PostgreSQL", reqs["rds"]),
        ("S3", reqs["s3"]),
        ("SQS", reqs["sqs"]),
        ("EventBridge", reqs["eventbridge"]),
        ("SES", reqs["ses"]),
        ("ElastiCache", reqs["elasticache"]),
        ("TigerBeetle (EC2)", reqs.get("tigerbeetle", False)),
        ("CloudWatch", True),
    ]

    for service, required in services:
        if required:
            console.print(f"  [green]✓[/green] {service}")
        else:
            console.print(f"  [dim]○ {service}[/dim]")

    console.print()

    # Show TigerBeetle configuration if needed
    if "tigerbeetle" in plan:
        tb = plan["tigerbeetle"]
        console.print("[bold]TigerBeetle Configuration:[/bold]")
        console.print(f"  Nodes: {tb['node_count']} x {tb['instance_type']}")
        console.print(f"  Storage: {tb['volume_size_gb']}GB @ {tb['volume_iops']} IOPS")
        console.print(f"  Ledgers: {tb['ledger_count']}")
        if tb.get("ledger_names"):
            for name in tb["ledger_names"]:
                console.print(f"    - {name}")
        if tb.get("currencies"):
            console.print(f"  Currencies: {', '.join(tb['currencies'])}")
        console.print()

    # Show stacks
    console.print("[bold]CDK Stacks:[/bold]")
    for stack in plan["stacks"]:
        console.print(f"  - {stack}")


@deploy_app.command(name="status")
def deploy_status(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--project",
            "-p",
            help="Project directory containing DSL files",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
) -> None:
    """
    Check deployment configuration and status.

    Shows whether CDK code has been generated and configuration status.
    """
    from dazzle.deploy.config import load_deployment_config

    console.print("\n[bold]Dazzle Deploy[/bold] - Status\n")

    # Check for dazzle.toml
    toml_path = project_dir / "dazzle.toml"
    if toml_path.exists():
        console.print(f"  [green]✓[/green] Configuration: {toml_path}")
        config = load_deployment_config(toml_path)
        console.print(f"    Provider: {config.provider}")
        console.print(f"    Environment: {config.environment}")
        console.print(f"    Region: {config.region.value}")
    else:
        console.print("  [yellow]○[/yellow] Configuration: Not found (using defaults)")
        config = load_deployment_config(toml_path)

    console.print()

    # Check for generated code
    output_dir = config.output.get_output_path(project_dir)
    app_py = output_dir / "app.py"

    if app_py.exists():
        console.print(f"  [green]✓[/green] CDK code: {output_dir}")

        # Count files
        py_files = list(output_dir.rglob("*.py"))
        console.print(f"    Files: {len(py_files)} Python files")

        # Check for stacks
        stacks_dir = output_dir / "stacks"
        if stacks_dir.exists():
            stack_files = list(stacks_dir.glob("*_stack.py"))
            console.print(f"    Stacks: {len(stack_files)}")
    else:
        console.print("  [yellow]○[/yellow] CDK code: Not generated")
        console.print("    Run: dazzle deploy generate")

    console.print()

    # Check for AWS CLI
    import shutil

    aws_cli = shutil.which("aws")
    if aws_cli:
        console.print(f"  [green]✓[/green] AWS CLI: {aws_cli}")
    else:
        console.print("  [red]✗[/red] AWS CLI: Not found")

    # Check for CDK CLI
    cdk_cli = shutil.which("cdk")
    if cdk_cli:
        console.print(f"  [green]✓[/green] CDK CLI: {cdk_cli}")
    else:
        console.print("  [yellow]○[/yellow] CDK CLI: Not found")
        console.print("    Install: npm install -g aws-cdk")


@deploy_app.command(name="validate")
def deploy_validate(
    infra_dir: Annotated[
        Path,
        typer.Argument(
            help="Directory containing generated CDK code",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ],
) -> None:
    """
    Validate generated CDK code can synthesize.

    Runs 'cdk synth' to verify the generated stacks are valid.
    """
    import subprocess

    console.print("\n[bold]Dazzle Deploy[/bold] - Validating CDK code\n")

    app_py = infra_dir / "app.py"
    if not app_py.exists():
        console.print(f"[red]Error: No app.py found in {infra_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"  Directory: {infra_dir}")

    with console.status("Running cdk synth..."):
        try:
            result = subprocess.run(
                ["cdk", "synth", "--quiet"],
                cwd=infra_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                console.print("\n[green]✓ CDK synthesis successful[/green]")
            else:
                console.print("\n[red]✗ CDK synthesis failed[/red]")
                console.print(result.stderr)
                raise typer.Exit(1)

        except FileNotFoundError:
            console.print("\n[red]Error: CDK CLI not found[/red]")
            console.print("Install with: npm install -g aws-cdk")
            raise typer.Exit(1)

        except subprocess.TimeoutExpired:
            console.print("\n[red]Error: CDK synthesis timed out[/red]")
            raise typer.Exit(1)


@deploy_app.command(name="preflight")
def deploy_preflight(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--project",
            "-p",
            help="Project directory containing DSL files",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
    infra_dir: Annotated[
        Path | None,
        typer.Option(
            "--infra",
            "-i",
            help="Infrastructure directory (defaults to project/infra)",
        ),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Validation mode: static_only, plan_only, or sandbox_apply",
        ),
    ] = "static_only",
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for reports",
        ),
    ] = None,
    report_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Report format(s): json, md, or both",
        ),
    ] = "both",
    fail_on_high: Annotated[
        bool,
        typer.Option(
            "--fail-on-high/--no-fail-on-high",
            help="Exit with error on HIGH severity findings",
        ),
    ] = True,
    fail_on_warn: Annotated[
        bool,
        typer.Option(
            "--fail-on-warn/--no-fail-on-warn",
            help="Exit with error on WARN severity findings",
        ),
    ] = False,
    skip_stages: Annotated[
        str | None,
        typer.Option(
            "--skip",
            help="Comma-separated list of stages to skip",
        ),
    ] = None,
) -> None:
    """
    Run pre-flight validation on generated CDK code.

    Validates CloudFormation templates against security best practices,
    policy guardrails, and linting rules before deployment.

    Modes:
    - static_only: No AWS credentials required (default)
    - plan_only: Includes AWS API calls for validation
    - sandbox_apply: Full sandbox deployment test

    Example:
        dazzle deploy preflight --project ./my-app
        dazzle deploy preflight --mode plan_only --output ./reports
    """
    from dazzle.deploy.preflight import (
        PreflightConfig,
        PreflightMode,
        PreflightRunner,
        generate_report,
    )

    console.print("\n[bold]Dazzle Pre-Flight[/bold] - Validating CDK code\n")

    # Parse mode
    try:
        preflight_mode = PreflightMode(mode)
    except ValueError:
        console.print(f"[red]Invalid mode: {mode}[/red]")
        console.print("Valid modes: static_only, plan_only, sandbox_apply")
        raise typer.Exit(1)

    # Parse skip stages
    stages_to_skip = []
    if skip_stages:
        stages_to_skip = [s.strip() for s in skip_stages.split(",")]

    # Create config
    config = PreflightConfig(
        mode=preflight_mode,
        skip_stages=stages_to_skip,
        fail_on_high=fail_on_high,
        fail_on_warn=fail_on_warn,
    )

    # Resolve paths
    project_path = project_dir.resolve()
    infra_path = infra_dir.resolve() if infra_dir else project_path / "infra"

    console.print(f"  Project: [cyan]{project_path}[/cyan]")
    console.print(f"  Infrastructure: [cyan]{infra_path}[/cyan]")
    console.print(f"  Mode: [yellow]{preflight_mode.value}[/yellow]")
    console.print()

    # Create and run the preflight runner
    runner = PreflightRunner(
        project_root=project_path,
        infra_dir=infra_path,
        config=config,
    )

    with console.status("Running pre-flight checks..."):
        report = runner.run()

    # Display results
    summary = report.summary
    if summary:
        status_color = {
            "passed": "green",
            "blocked": "yellow",
            "failed": "red",
        }.get(summary.status, "white")

        console.print(
            Panel(
                f"[{status_color}]{summary.status.upper()}[/{status_color}]\n\n"
                f"Findings: {summary.total_findings} "
                f"(🔴 {summary.critical_count} / 🟠 {summary.high_count} / "
                f"🟡 {summary.warn_count} / 🔵 {summary.info_count})\n\n"
                f"Stages: {summary.stages_passed} passed, "
                f"{summary.stages_failed} failed, "
                f"{summary.stages_skipped} skipped",
                title=f"Pre-Flight Report ({report.run_id})",
            )
        )

        # Show next actions
        if summary.next_actions:
            console.print("\n[bold]Next Actions:[/bold]")
            for action in summary.next_actions:
                console.print(f"  → {action}")

    # Generate reports
    if output_dir or report_format != "none":
        report_path = output_dir or (project_path / "reports")

        formats = []
        if report_format in ("json", "both"):
            formats.append("json")
        if report_format in ("md", "both"):
            formats.append("md")

        if formats:
            generated = generate_report(report, report_path, formats)
            console.print("\n[bold]Reports:[/bold]")
            for fmt, path in generated.items():
                console.print(f"  {fmt.upper()}: [cyan]{path}[/cyan]")

    # Show critical findings
    critical_findings = [
        f for s in report.stages for f in s.findings if f.severity.value == "critical"
    ]

    if critical_findings:
        console.print("\n[bold red]Critical Findings:[/bold red]")
        for finding in critical_findings[:5]:  # Show first 5
            console.print(f"  🔴 [{finding.code}] {finding.message}")
            if finding.remediation:
                console.print(f"     → {finding.remediation}")
        if len(critical_findings) > 5:
            console.print(f"  ... and {len(critical_findings) - 5} more")

    # Exit with appropriate code
    if summary and not summary.can_proceed:
        raise typer.Exit(1)
