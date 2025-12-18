"""
Temporal worker entry point for DAZZLE processes.

This module provides the main entry point for running a Temporal worker
that executes DAZZLE ProcessSpec workflows.

Usage:
    # From project directory
    python -m dazzle.process.worker

    # With environment variables
    TEMPORAL_ADDRESS=localhost:7233 python -m dazzle.process.worker

    # Via Docker Compose (recommended)
    docker-compose -f docker-compose.temporal.yml up temporal-worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dazzle.process.worker")


async def main() -> None:
    """Main entry point for the Temporal worker."""
    # Load environment configuration
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "dazzle")
    project_root = Path(os.environ.get("DAZZLE_PROJECT_ROOT", "."))

    logger.info("DAZZLE Temporal Worker")
    logger.info(f"  Temporal: {temporal_address}")
    logger.info(f"  Namespace: {namespace}")
    logger.info(f"  Task Queue: {task_queue}")
    logger.info(f"  Project Root: {project_root.absolute()}")

    # Check Temporal SDK availability
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        logger.error("Temporal SDK not installed. " "Install with: pip install dazzle[temporal]")
        sys.exit(1)

    # Load DSL and build AppSpec
    try:
        from dazzle.core.dsl_parser import parse_modules
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
    except ImportError as e:
        logger.error(f"Failed to import DAZZLE core modules: {e}")
        sys.exit(1)

    # Load project manifest
    manifest_path = project_root / "dazzle.toml"
    if not manifest_path.exists():
        logger.error(f"Project manifest not found: {manifest_path}")
        logger.info("Run 'dazzle init' to create a new project")
        sys.exit(1)

    manifest = load_manifest(manifest_path)
    logger.info(f"Loaded project: {manifest.name}")

    # Parse DSL files
    dsl_files = discover_dsl_files(project_root, manifest)
    if not dsl_files:
        logger.error("No DSL files found in project")
        sys.exit(1)

    logger.info(f"Found {len(dsl_files)} DSL files")

    modules = parse_modules(dsl_files)
    app_spec = build_appspec(modules, str(project_root))

    # Get process specs
    processes = app_spec.processes if hasattr(app_spec, "processes") else []
    if not processes:
        logger.warning("No process specs found in DSL")
        logger.info("Define processes in your DSL to use the workflow engine")

    logger.info(f"Found {len(processes)} process definitions")

    # Connect to Temporal
    logger.info(f"Connecting to Temporal at {temporal_address}...")
    try:
        client = await Client.connect(temporal_address, namespace=namespace)
        logger.info("Connected to Temporal")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        sys.exit(1)

    # Create adapter and register processes
    from dazzle.core.process.activities import get_all_activities
    from dazzle.core.process.temporal_adapter import TemporalAdapter

    # Parse host and port from address
    if ":" in temporal_address:
        host, port_str = temporal_address.rsplit(":", 1)
        port = int(port_str)
    else:
        host = temporal_address
        port = 7233

    adapter = TemporalAdapter(
        host=host,
        port=port,
        namespace=namespace,
        task_queue=task_queue,
        client=client,
    )

    # Register all processes
    for process in processes:
        await adapter.register_process(process)
        logger.info(f"Registered process: {process.name}")

    # Collect workflows and activities
    workflows = list(adapter._workflows.values())
    activities = list(adapter._activities) + get_all_activities()

    if not workflows:
        logger.warning("No workflows registered. Worker will wait for process registrations.")

    # Create and run worker
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=workflows,
        activities=activities,
    )

    logger.info(
        f"Starting worker on queue '{task_queue}' "
        f"with {len(workflows)} workflows and {len(activities)} activities"
    )
    logger.info("Press Ctrl+C to stop")

    try:
        await worker.run()
    except asyncio.CancelledError:
        logger.info("Worker shutdown requested")
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    finally:
        logger.info("Worker stopped")


def run() -> None:
    """Synchronous entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
