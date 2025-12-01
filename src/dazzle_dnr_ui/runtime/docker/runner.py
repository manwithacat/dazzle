"""
Docker runner for DNR applications.

Contains the DockerRunner class and DockerRunConfig for running
DNR applications in Docker containers.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .templates import (
    DNR_BACKEND_DOCKERFILE,
    DNR_COMPOSE_TEMPLATE,
    DNR_DOCKERIGNORE,
    DNR_FRONTEND_DOCKERFILE,
    generate_dockerfile,
)
from .utils import is_docker_available

if TYPE_CHECKING:
    pass


def _get_container_package_path() -> Path:
    """Get the path to the container runtime package."""
    # The container package is at dazzle_dnr_ui/runtime/container/
    return Path(__file__).parent.parent / "container"


def _copy_container_package(dest_dir: Path) -> None:
    """
    Copy the container runtime package to the Docker build context.

    Args:
        dest_dir: Destination directory for the build context
    """
    container_src = _get_container_package_path()
    container_dest = dest_dir / "container"

    if container_dest.exists():
        shutil.rmtree(container_dest)

    # Copy all Python files from the container package
    container_dest.mkdir(exist_ok=True)
    for py_file in container_src.glob("*.py"):
        shutil.copy2(py_file, container_dest / py_file.name)


@dataclass
class DockerRunConfig:
    """Configuration for running DNR in Docker."""

    project_path: Path
    frontend_port: int = 3000
    api_port: int = 8000
    container_name: str | None = None
    project_name: str | None = None  # From manifest [project].name - used for stack naming
    image_name: str = "dazzle-dnr"
    test_mode: bool = False
    auth_enabled: bool = False
    rebuild: bool = False
    detach: bool = False
    single_container: bool = False  # Legacy mode: combined frontend + backend


class DockerRunner:
    """
    Runs DNR applications in Docker containers.

    Provides docker-first infrastructure for Dazzle development.
    """

    def __init__(self, config: DockerRunConfig):
        """
        Initialize the Docker runner.

        Args:
            config: Docker run configuration
        """
        self.config = config
        self.project_path = config.project_path.resolve()

        # Use project_name from manifest if provided, otherwise fall back to directory name
        # This allows multiple instances of the same project (in different directories) to coexist
        base_name = config.project_name or self.project_path.name

        # Derive container/stack name from project name
        if config.container_name:
            self.container_name = config.container_name
        else:
            self.container_name = f"dazzle-{base_name}"

        # Image name includes project context
        self.image_name = f"{config.image_name}:{base_name}"

    def run(self) -> int:
        """
        Run the DNR application in Docker container(s).

        Uses split containers (frontend + backend) by default.
        Use single_container=True for legacy combined mode.

        Returns:
            Exit code from Docker run
        """
        mode = "single-container" if self.config.single_container else "split containers"
        print("\n" + "=" * 60)
        print(f"  DAZZLE NATIVE RUNTIME (DNR) - Docker Mode ({mode})")
        print("=" * 60)
        print()

        # Check Docker availability
        if not is_docker_available():
            print("[DNR] ERROR: Docker is not available")
            print("[DNR] Please install Docker or use --local flag")
            return 1

        if self.config.single_container:
            # Legacy single-container mode
            self._stop_existing_container()

            if self.config.rebuild or not self._image_exists():
                if not self._build_image():
                    return 1

            return self._run_container()
        else:
            # New split containers mode using docker-compose
            return self._run_split_containers()

    def _image_exists(self) -> bool:
        """Check if the Docker image already exists."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.image_name],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _stop_existing_container(self) -> None:
        """Stop and remove any existing container with the same name."""
        try:
            subprocess.run(
                ["docker", "stop", self.container_name],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["docker", "rm", self.container_name],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            pass  # Container may not exist

    def _build_image(self) -> bool:
        """
        Build the Docker image.

        Returns:
            True if build succeeded
        """
        print(f"[DNR] Building Docker image: {self.image_name}")
        print()

        # First, generate the specs from DSL
        print("[DNR] Generating specs from DSL...")
        try:
            backend_spec, ui_spec, html_content = self._generate_specs()
        except Exception as e:
            print(f"[DNR] ERROR: Failed to generate specs: {e}")
            return False

        # Create temporary build context
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir)

            # Generate Dockerfile
            dockerfile_content = generate_dockerfile(
                frontend_port=self.config.frontend_port,
                api_port=self.config.api_port,
            )
            (build_dir / "Dockerfile").write_text(dockerfile_content)

            # Generate .dockerignore
            (build_dir / ".dockerignore").write_text(DNR_DOCKERIGNORE)

            # Write pre-generated specs
            import json

            (build_dir / "backend_spec.json").write_text(json.dumps(backend_spec, indent=2))
            (build_dir / "ui_spec.json").write_text(json.dumps(ui_spec, indent=2))

            # Create static directory and write HTML
            static_dir = build_dir / "static"
            static_dir.mkdir(exist_ok=True)
            (static_dir / "index.html").write_text(html_content)

            # Copy container runtime package
            _copy_container_package(build_dir)

            # Build image
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "build",
                        "-t",
                        self.image_name,
                        str(build_dir),
                    ],
                    timeout=300,  # 5 minute timeout
                )
                if result.returncode != 0:
                    print("[DNR] ERROR: Docker build failed")
                    return False
            except subprocess.TimeoutExpired:
                print("[DNR] ERROR: Docker build timed out")
                return False
            except FileNotFoundError:
                print("[DNR] ERROR: Docker not found")
                return False

        print()
        print(f"[DNR] Image built: {self.image_name}")
        return True

    def _generate_specs(self) -> tuple[dict[str, Any], dict[str, Any], str]:
        """
        Generate backend spec, UI spec, and HTML from DSL files.

        Returns:
            Tuple of (backend_spec_dict, ui_spec_dict, html_content)
        """
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import generate_single_html

        manifest_path = self.project_path / "dazzle.toml"
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(self.project_path, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Convert to backend and UI specs (pass shell config from manifest)
        backend_spec = convert_appspec_to_backend(appspec)
        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)

        # Generate HTML
        html_content = generate_single_html(ui_spec)

        return (
            backend_spec.model_dump(by_alias=True),
            ui_spec.model_dump(by_alias=True),
            html_content,
        )

    def _run_container(self) -> int:
        """
        Run the Docker container.

        Returns:
            Exit code from docker run
        """
        print()
        print(f"[DNR] Starting container: {self.container_name}")
        print()

        # Build docker run command
        cmd = [
            "docker",
            "run",
            "--name",
            self.container_name,
            "-p",
            f"{self.config.frontend_port}:{self.config.frontend_port}",
            "-p",
            f"{self.config.api_port}:{self.config.api_port}",
        ]

        # Mount data directory for persistence
        data_dir = self.project_path / ".dazzle"
        data_dir.mkdir(exist_ok=True)
        cmd.extend(["-v", f"{data_dir}:/app/.dazzle"])

        # Add test mode if enabled
        if self.config.test_mode:
            cmd.extend(["-e", "DNR_TEST_MODE=1"])

        # Detach mode or interactive mode
        if self.config.detach:
            cmd.append("-d")
        else:
            # Only use -it if we have a TTY, otherwise just run attached
            import sys

            if sys.stdin.isatty():
                cmd.append("-it")
            cmd.append("--rm")

        # Add image name
        cmd.append(self.image_name)

        # Note: Test mode is handled via DNR_TEST_MODE environment variable
        # The entrypoint.py script reads this and enables test endpoints

        print(f"[DNR] Frontend: http://localhost:{self.config.frontend_port}")
        print(f"[DNR] API Docs: http://localhost:{self.config.api_port}/docs")
        print()

        if self.config.detach:
            print(f"[DNR] Running in background (container: {self.container_name})")
            print(f"[DNR] Stop with: docker stop {self.container_name}")
        else:
            print("Press Ctrl+C to stop")
            print("-" * 60)

        print()

        try:
            result = subprocess.run(cmd)
            return result.returncode
        except KeyboardInterrupt:
            print("\n[DNR] Shutting down...")
            self._stop_existing_container()
            return 0

    def _run_split_containers(self) -> int:
        """
        Run split frontend and backend containers using docker-compose.

        Returns:
            Exit code from docker compose
        """
        import json

        print("[DNR] Setting up split containers (frontend + backend)...")
        print()

        # Generate specs from DSL
        print("[DNR] Generating specs from DSL...")
        try:
            backend_spec, ui_spec_dict, _ = self._generate_specs()
        except Exception as e:
            print(f"[DNR] ERROR: Failed to generate specs: {e}")
            return 1

        # Create persistent build directory in project
        build_dir = self.project_path / ".dazzle" / "docker"
        if self.config.rebuild and build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        # Backend context
        backend_dir = build_dir / "backend"
        backend_dir.mkdir(exist_ok=True)

        backend_dockerfile = DNR_BACKEND_DOCKERFILE.format(
            api_port=self.config.api_port,
        )
        (backend_dir / "Dockerfile").write_text(backend_dockerfile)
        (backend_dir / "backend_spec.json").write_text(json.dumps(backend_spec, indent=2))
        (backend_dir / "ui_spec.json").write_text(json.dumps(ui_spec_dict, indent=2))
        # Copy container runtime package
        _copy_container_package(backend_dir)

        # Frontend context - generate Vite project
        frontend_dir = build_dir / "frontend"
        if frontend_dir.exists():
            shutil.rmtree(frontend_dir)
        frontend_dir.mkdir(exist_ok=True)

        print("[DNR] Generating Vite project for frontend...")
        from dazzle_dnr_ui.runtime.vite_generator import ViteGenerator
        from dazzle_dnr_ui.specs import UISpec

        ui_spec = UISpec(**ui_spec_dict)
        generator = ViteGenerator(ui_spec)
        generator.write_to_directory(frontend_dir)

        # Add frontend Dockerfile
        frontend_dockerfile = DNR_FRONTEND_DOCKERFILE.format(
            frontend_port=self.config.frontend_port,
        )
        (frontend_dir / "Dockerfile").write_text(frontend_dockerfile)

        # Generate docker-compose.yaml
        volume_name = f"{self.container_name}-data".replace("-", "_")
        compose_content = DNR_COMPOSE_TEMPLATE.format(
            container_name=self.container_name,
            api_port=self.config.api_port,
            frontend_port=self.config.frontend_port,
            test_mode="1" if self.config.test_mode else "0",
            auth_enabled="1" if self.config.auth_enabled else "0",
            volume_name=volume_name,
        )
        compose_file = build_dir / "docker-compose.yaml"
        compose_file.write_text(compose_content)

        # Stop existing containers
        print("[DNR] Stopping any existing containers...")
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down"],
            capture_output=True,
        )

        # Build and run with docker-compose
        print("[DNR] Building containers...")
        build_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "build"],
            cwd=str(build_dir),
        )
        if build_result.returncode != 0:
            print("[DNR] ERROR: Docker compose build failed")
            return 1

        print()
        print(f"[DNR] Frontend: http://localhost:{self.config.frontend_port}")
        print(f"[DNR] API Docs: http://localhost:{self.config.api_port}/docs")
        print()

        if self.config.detach:
            print("[DNR] Running in background...")
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "up", "-d"],
                cwd=str(build_dir),
            )
            if result.returncode == 0:
                print(
                    f"[DNR] Containers started: {self.container_name}-backend, {self.container_name}-frontend"
                )
                print(f"[DNR] Stop with: docker compose -f {compose_file} down")
            return result.returncode
        else:
            print("Press Ctrl+C to stop")
            print("-" * 60)
            print()

            try:
                result = subprocess.run(
                    ["docker", "compose", "-f", str(compose_file), "up"],
                    cwd=str(build_dir),
                )
                return result.returncode
            except KeyboardInterrupt:
                print("\n[DNR] Shutting down...")
                subprocess.run(
                    ["docker", "compose", "-f", str(compose_file), "down"],
                    cwd=str(build_dir),
                )
                return 0


# =============================================================================
# Convenience Functions
# =============================================================================


def run_in_docker(
    project_path: Path | str,
    frontend_port: int = 3000,
    api_port: int = 8000,
    test_mode: bool = False,
    auth_enabled: bool = False,
    rebuild: bool = False,
    detach: bool = False,
    single_container: bool = False,
    project_name: str | None = None,
) -> int:
    """
    Run a DNR application in Docker.

    By default, runs frontend and backend in separate containers.
    Use single_container=True for legacy combined mode.

    Args:
        project_path: Path to the Dazzle project
        frontend_port: Frontend server port
        api_port: Backend API port
        test_mode: Enable test endpoints
        auth_enabled: Enable authentication endpoints
        rebuild: Force rebuild of Docker image
        detach: Run in background
        single_container: Use legacy single-container mode
        project_name: Project name from manifest (used for stack naming)

    Returns:
        Exit code
    """
    config = DockerRunConfig(
        project_path=Path(project_path),
        frontend_port=frontend_port,
        api_port=api_port,
        test_mode=test_mode,
        auth_enabled=auth_enabled,
        rebuild=rebuild,
        detach=detach,
        single_container=single_container,
        project_name=project_name,
    )
    runner = DockerRunner(config)
    return runner.run()


def stop_docker_container(
    project_path: Path | str,
    project_name: str | None = None,
) -> bool:
    """
    Stop a running DNR Docker container.

    Args:
        project_path: Path to the Dazzle project
        project_name: Project name from manifest (used for container naming)

    Returns:
        True if container was stopped
    """
    base_name = project_name or Path(project_path).resolve().name
    container_name = f"dazzle-{base_name}"
    try:
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
