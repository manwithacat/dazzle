"""
Ejection runner - orchestrates the code generation process.

The EjectionRunner coordinates all adapters to generate a complete
standalone application from an AppSpec.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.eject.generator import GeneratorResult

from .adapters import AdapterRegistry
from .config import EjectionConfig, load_ejection_config

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

# Version of the ejection toolchain
EJECTION_VERSION = "0.7.2"

# Patterns that indicate Dazzle runtime dependencies
FORBIDDEN_PYTHON_IMPORTS = [
    r"^\s*from\s+dazzle\s+import",
    r"^\s*from\s+dazzle\.",
    r"^\s*import\s+dazzle\b",
    r"^\s*from\s+dazzle_dnr",
    r"^\s*import\s+dazzle_dnr",
]

FORBIDDEN_JS_IMPORTS = [
    r'from\s+["\']@dazzle/',
    r'from\s+["\']dazzle',
    r'import\s+.*\s+from\s+["\']@dazzle/',
    r'require\s*\(\s*["\']@dazzle/',
    r'require\s*\(\s*["\']dazzle',
]

FORBIDDEN_TEMPLATE_MARKERS = [
    r"#\s*BEGIN\s+DAZZLE",
    r"#\s*END\s+DAZZLE",
    r"//\s*DAZZLE-OVERRIDE",
    r"<!--\s*DAZZLE-",
    r"\{\{\s*dazzle\.",
]

FORBIDDEN_RUNTIME_LOADERS = [
    r"load_dsl\s*\(",
    r"parse_appspec\s*\(",
    r"load_appspec\s*\(",
    r"\.dsl[\"']\s*\)",
    r"AppSpec\.from_",
]


class EjectionRunner:
    """
    Orchestrates the ejection process.

    Coordinates backend, frontend, testing, and CI adapters
    to generate a complete standalone application.
    """

    def __init__(
        self,
        spec: AppSpec,
        project_root: Path,
        config: EjectionConfig | None = None,
    ):
        """
        Initialize the ejection runner.

        Args:
            spec: The application specification
            project_root: Root directory of the DAZZLE project
            config: Optional ejection configuration (loaded from dazzle.toml if not provided)
        """
        self.spec = spec
        self.project_root = project_root

        # Load config from dazzle.toml if not provided
        if config is None:
            toml_path = project_root / "dazzle.toml"
            config = load_ejection_config(toml_path)

        self.config = config
        self.output_dir = config.get_output_path(project_root)

    def run(
        self,
        backend: bool = True,
        frontend: bool = True,
        testing: bool = True,
        ci: bool = True,
        clean: bool | None = None,
        verify: bool = True,
    ) -> EjectionResult:
        """
        Run the ejection process.

        Args:
            backend: Generate backend code
            frontend: Generate frontend code
            testing: Generate test code
            ci: Generate CI configuration
            clean: Clean output directory before generating (uses config if None)
            verify: Run post-ejection verification to ensure independence

        Returns:
            EjectionResult with generated files and any errors
        """
        result = EjectionResult()

        # Clean output directory if requested
        should_clean = clean if clean is not None else self.config.output.clean
        if should_clean and self.output_dir.exists():
            shutil.rmtree(self.output_dir)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate backend
        if backend:
            result.merge(self._generate_backend())

        # Generate frontend
        if frontend:
            result.merge(self._generate_frontend())

        # Generate testing
        if testing:
            result.merge(self._generate_testing())

        # Generate CI
        if ci:
            result.merge(self._generate_ci())

        # Generate shared files
        result.merge(self._generate_shared_files())

        # Generate ejection metadata
        result.merge(self._generate_ejection_metadata())

        # Write all files
        result.write_files()

        # Run verification if requested and no errors so far
        if verify and result.success:
            verification = self.verify()
            result.verified = verification.verified
            result.verification_errors = verification.errors
            if not verification.verified:
                for error in verification.errors:
                    result.add_error(f"[verification] {error}")

        return result

    def verify(self) -> VerificationResult:
        """
        Verify that ejected code is independent from Dazzle.

        Scans all generated files for:
        - Forbidden Dazzle imports
        - Runtime DSL/AppSpec loaders
        - Template merge markers

        Returns:
            VerificationResult with verification status and any violations
        """
        result = VerificationResult()

        if not self.output_dir.exists():
            result.add_error("Output directory does not exist")
            return result

        # Scan Python files
        for py_file in self.output_dir.rglob("*.py"):
            self._verify_python_file(py_file, result)

        # Scan JavaScript/TypeScript files
        for pattern in ["*.js", "*.ts", "*.tsx", "*.jsx"]:
            for js_file in self.output_dir.rglob(pattern):
                self._verify_js_file(js_file, result)

        # Scan all text files for template markers
        for pattern in ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.html", "*.yaml", "*.yml"]:
            for file in self.output_dir.rglob(pattern):
                self._verify_no_template_markers(file, result)

        return result

    def _verify_python_file(self, path: Path, result: VerificationResult) -> None:
        """Verify a Python file has no Dazzle dependencies."""
        try:
            content = path.read_text()
        except Exception:
            return

        rel_path = path.relative_to(self.output_dir)

        # Check for forbidden imports
        for pattern in FORBIDDEN_PYTHON_IMPORTS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(
                    f"{rel_path}:{line_num}: Forbidden Dazzle import: {match.group().strip()}"
                )

        # Check for runtime loaders
        for pattern in FORBIDDEN_RUNTIME_LOADERS:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(
                    f"{rel_path}:{line_num}: Runtime DSL/AppSpec loader detected: {match.group()}"
                )

    def _verify_js_file(self, path: Path, result: VerificationResult) -> None:
        """Verify a JavaScript/TypeScript file has no Dazzle dependencies."""
        try:
            content = path.read_text()
        except Exception:
            return

        rel_path = path.relative_to(self.output_dir)

        # Check for forbidden imports
        for pattern in FORBIDDEN_JS_IMPORTS:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(
                    f"{rel_path}:{line_num}: Forbidden Dazzle import: {match.group().strip()}"
                )

    def _verify_no_template_markers(self, path: Path, result: VerificationResult) -> None:
        """Verify a file has no template merge markers."""
        try:
            content = path.read_text()
        except Exception:
            return

        rel_path = path.relative_to(self.output_dir)

        for pattern in FORBIDDEN_TEMPLATE_MARKERS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(
                    f"{rel_path}:{line_num}: Template marker detected: {match.group()}"
                )

    def _generate_ejection_metadata(self) -> EjectionResult:
        """Generate .ejection.json metadata file."""
        result = EjectionResult()

        metadata = {
            "generated_by": "dazzle",
            "dazzle_version": EJECTION_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "app_name": self.spec.name,
            "config": {
                "backend": self.config.backend.framework.value,
                "frontend": self.config.frontend.framework.value,
                "testing": {
                    "contract": self.config.testing.contract.value,
                    "unit": self.config.testing.unit.value,
                },
                "ci": self.config.ci.template.value,
            },
        }

        result.add_file(
            self.output_dir / ".ejection.json",
            json.dumps(metadata, indent=2) + "\n",
        )

        return result

    def _generate_backend(self) -> EjectionResult:
        """Generate backend code using configured adapter."""
        result = EjectionResult()

        framework = self.config.backend.framework.value
        adapter_class = AdapterRegistry.get_backend(framework)

        if adapter_class is None:
            result.add_error(f"Unknown backend framework: {framework}")
            return result

        backend_dir = self.output_dir / "backend"
        adapter = adapter_class(self.spec, backend_dir, self.config.backend)

        try:
            gen_result = adapter.generate()
            result.merge_generator_result(gen_result, "backend")
        except Exception as e:
            result.add_error(f"Backend generation failed: {e}")

        return result

    def _generate_frontend(self) -> EjectionResult:
        """Generate frontend code using configured adapter."""
        result = EjectionResult()

        framework = self.config.frontend.framework.value
        adapter_class = AdapterRegistry.get_frontend(framework)

        if adapter_class is None:
            result.add_error(f"Unknown frontend framework: {framework}")
            return result

        frontend_dir = self.output_dir / "frontend"
        adapter = adapter_class(self.spec, frontend_dir, self.config.frontend)

        try:
            gen_result = adapter.generate()
            result.merge_generator_result(gen_result, "frontend")
        except Exception as e:
            result.add_error(f"Frontend generation failed: {e}")

        return result

    def _generate_testing(self) -> EjectionResult:
        """Generate test code using configured adapters."""
        result = EjectionResult()

        # Contract testing
        if self.config.testing.contract.value != "none":
            contract_tool = self.config.testing.contract.value
            adapter_class = AdapterRegistry.get_testing(contract_tool)

            if adapter_class:
                adapter = adapter_class(
                    self.spec,
                    self.output_dir / "backend",
                    self.config.testing,
                )
                try:
                    gen_result = adapter.generate()
                    result.merge_generator_result(gen_result, "testing")
                except Exception as e:
                    result.add_error(f"Contract testing generation failed: {e}")

        # Unit testing
        if self.config.testing.unit.value != "none":
            unit_tool = self.config.testing.unit.value
            adapter_class = AdapterRegistry.get_testing(unit_tool)

            if adapter_class:
                adapter = adapter_class(
                    self.spec,
                    self.output_dir / "backend",
                    self.config.testing,
                )
                try:
                    gen_result = adapter.generate()
                    result.merge_generator_result(gen_result, "testing")
                except Exception as e:
                    result.add_error(f"Unit testing generation failed: {e}")

        return result

    def _generate_ci(self) -> EjectionResult:
        """Generate CI configuration using configured adapter."""
        result = EjectionResult()

        if self.config.ci.template.value == "none":
            return result

        template = self.config.ci.template.value
        adapter_class = AdapterRegistry.get_ci(template)

        if adapter_class is None:
            result.add_error(f"Unknown CI template: {template}")
            return result

        adapter = adapter_class(self.spec, self.output_dir, self.config.ci)

        try:
            gen_result = adapter.generate()
            result.merge_generator_result(gen_result, "ci")
        except Exception as e:
            result.add_error(f"CI generation failed: {e}")

        return result

    def _generate_shared_files(self) -> EjectionResult:
        """Generate shared project files."""
        result = EjectionResult()

        # Root README
        result.add_file(self.output_dir / "README.md", self._generate_readme())

        # Docker Compose
        result.add_file(
            self.output_dir / "docker-compose.yml",
            self._generate_docker_compose(),
        )

        # Docker Compose for development
        result.add_file(
            self.output_dir / "docker-compose.dev.yml",
            self._generate_docker_compose_dev(),
        )

        # Makefile
        result.add_file(self.output_dir / "Makefile", self._generate_makefile())

        # .gitignore
        result.add_file(self.output_dir / ".gitignore", self._generate_gitignore())

        # .env.example
        result.add_file(self.output_dir / ".env.example", self._generate_env_example())

        return result

    def _generate_readme(self) -> str:
        """Generate root README."""
        return f"""# {self.spec.name}

{self.spec.description or "Generated from DAZZLE specification."}

## Generated by DAZZLE Ejection Toolchain v0.7.2

This application was generated from a DAZZLE DSL specification.

## Quick Start

```bash
# Start development environment
docker compose -f docker-compose.dev.yml up

# Or run locally
make dev
```

## Project Structure

```
.
├── backend/           # FastAPI backend
│   ├── app/          # Application code
│   │   ├── models/   # SQLAlchemy models
│   │   ├── schemas/  # Pydantic schemas
│   │   ├── routers/  # API endpoints
│   │   ├── services/ # Business logic
│   │   ├── guards/   # State machine guards
│   │   ├── validators/ # Invariant validators
│   │   └── access/   # Access control
│   └── tests/        # Backend tests
├── frontend/         # React frontend
│   └── src/
│       └── api/      # Generated API client
└── docker-compose.yml
```

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Testing

```bash
# Backend tests
cd backend
pytest tests/

# Contract tests
schemathesis run http://localhost:8000/openapi.json
```

## API Documentation

When the backend is running:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## License

MIT
"""

    def _generate_docker_compose(self) -> str:
        """Generate production docker-compose.yml."""
        app_name = self.spec.name.lower().replace(" ", "-")

        return f"""# Docker Compose for production
# Generated by DAZZLE Ejection Toolchain v0.7.2

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://app:app@db:5432/{app_name}
      - CORS_ORIGINS=http://localhost:3000
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - VITE_API_URL=http://localhost:8000
    ports:
      - "3000:80"
    depends_on:
      - backend

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=app
      - POSTGRES_DB={app_name}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d {app_name}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
"""

    def _generate_docker_compose_dev(self) -> str:
        """Generate development docker-compose.yml."""
        app_name = self.spec.name.lower().replace(" ", "-")

        return f"""# Docker Compose for development
# Generated by DAZZLE Ejection Toolchain v0.7.2

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://app:app@db:5432/{app_name}
      - CORS_ORIGINS=http://localhost:3000
      - DEBUG=true
    volumes:
      - ./backend/app:/app/app
    depends_on:
      db:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --reload

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
    volumes:
      - ./frontend/src:/app/src
    depends_on:
      - backend
    command: npm run dev -- --host

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=app
      - POSTGRES_DB={app_name}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d {app_name}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
"""

    def _generate_makefile(self) -> str:
        """Generate Makefile with common commands."""
        return """# Makefile
# Generated by DAZZLE Ejection Toolchain v0.7.2

.PHONY: help dev test lint build clean

help:
\t@echo "Available commands:"
\t@echo "  make dev      - Start development environment"
\t@echo "  make test     - Run all tests"
\t@echo "  make lint     - Run linters"
\t@echo "  make build    - Build production containers"
\t@echo "  make clean    - Clean up containers and volumes"

dev:
\tdocker compose -f docker-compose.dev.yml up

test:
\tcd backend && pytest tests/
\tcd frontend && npm test

lint:
\tcd backend && ruff check . && ruff format --check .
\tcd frontend && npm run lint

build:
\tdocker compose build

clean:
\tdocker compose down -v
\tdocker compose -f docker-compose.dev.yml down -v

# Backend specific
backend-dev:
\tcd backend && uvicorn app.main:app --reload

backend-test:
\tcd backend && pytest tests/ -v

backend-lint:
\tcd backend && ruff check . && ruff format --check .

# Frontend specific
frontend-dev:
\tcd frontend && npm run dev

frontend-test:
\tcd frontend && npm test

frontend-lint:
\tcd frontend && npm run lint
"""

    def _generate_gitignore(self) -> str:
        """Generate .gitignore."""
        return """# Generated by DAZZLE Ejection Toolchain v0.7.2

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
ENV/
env/
.eggs/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Node
node_modules/
dist/
.npm
.pnpm-store/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Environment
.env
.env.local
.env.*.local

# Docker
.docker/

# Misc
*.log
.DS_Store
Thumbs.db
"""

    def _generate_env_example(self) -> str:
        """Generate .env.example."""
        app_name = self.spec.name.lower().replace(" ", "-")

        return f"""# Environment variables
# Generated by DAZZLE Ejection Toolchain v0.7.2

# Database
DATABASE_URL=postgresql://app:app@localhost:5432/{app_name}

# API
CORS_ORIGINS=http://localhost:3000
DEBUG=true

# Frontend
VITE_API_URL=http://localhost:8000
"""


class VerificationResult:
    """
    Result of ejection verification.

    Tracks whether the ejected code is independent from Dazzle.
    """

    def __init__(self):
        self.errors: list[str] = []

    def add_error(self, message: str) -> None:
        """Add a verification error."""
        self.errors.append(message)

    @property
    def verified(self) -> bool:
        """Check if verification passed (no errors)."""
        return len(self.errors) == 0


class EjectionResult:
    """
    Result of an ejection operation.

    Tracks generated files, errors, and warnings.
    """

    def __init__(self):
        self.files: dict[Path, str] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.verified: bool = False
        self.verification_errors: list[str] = []

    def add_file(self, path: Path, content: str) -> None:
        """Add a file to be written."""
        self.files[path] = content

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def merge(self, other: EjectionResult) -> None:
        """Merge another result into this one."""
        self.files.update(other.files)
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def merge_generator_result(
        self,
        result: GeneratorResult,
        category: str,
    ) -> None:
        """Merge a GeneratorResult into this EjectionResult."""
        for path, content in result.files.items():
            self.files[path] = content

        for error in result.errors:
            self.errors.append(f"[{category}] {error}")

        for warning in result.warnings:
            self.warnings.append(f"[{category}] {warning}")

    def write_files(self) -> None:
        """Write all files to disk."""
        for path, content in self.files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    @property
    def success(self) -> bool:
        """Check if ejection was successful (no errors)."""
        return len(self.errors) == 0

    def summary(self) -> str:
        """Get a summary of the ejection result."""
        lines = []

        if self.success:
            lines.append(f"Successfully generated {len(self.files)} files")
        else:
            lines.append(f"Ejection failed with {len(self.errors)} errors")

        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")

        return "\n".join(lines)
