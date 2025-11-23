"""
Base generator classes for modular code generation.

Generators are responsible for creating specific artifacts:
- ModelsGenerator: Database models
- ViewsGenerator: View/controller logic
- TemplatesGenerator: HTML templates
- etc.

Each generator focuses on one aspect, making them easier to:
- Understand
- Test
- Modify
- Reuse across backends
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...core import ir


@dataclass
class GeneratorResult:
    """
    Result from a generator execution.

    Attributes:
        files_created: List of file paths that were created/modified
        artifacts: Data to share with other generators or hooks
        errors: Any non-fatal errors encountered
        warnings: Any warnings to display to user
    """

    files_created: list[Path] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Whether generation succeeded (no errors)."""
        return len(self.errors) == 0

    def add_file(self, path: Path) -> None:
        """Record a file that was created."""
        self.files_created.append(path)

    def add_artifact(self, key: str, value: Any) -> None:
        """Add an artifact for other generators/hooks."""
        self.artifacts[key] = value

    def add_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Record a warning."""
        self.warnings.append(warning)

    def merge(self, other: "GeneratorResult") -> None:
        """Merge another result into this one."""
        self.files_created.extend(other.files_created)
        self.artifacts.update(other.artifacts)
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


class Generator(ABC):
    """
    Base class for all generators.

    A generator creates specific artifacts from the AppSpec.

    Example:
        class ModelsGenerator(Generator):
            def generate(self) -> GeneratorResult:
                result = GeneratorResult()

                # Build models.py content
                code = self._build_models_code()

                # Write file
                file_path = self.output_dir / "app" / "models.py"
                file_path.write_text(code)
                result.add_file(file_path)

                # Record model names for other generators
                result.add_artifact("model_names", [e.name for e in self.spec.entities])

                return result
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path):
        """
        Initialize generator.

        Args:
            spec: Application specification
            output_dir: Root output directory for generated files
        """
        self.spec = spec
        self.output_dir = output_dir

    @abstractmethod
    def generate(self) -> GeneratorResult:
        """
        Generate artifacts.

        Returns:
            GeneratorResult with files created and artifacts
        """
        pass

    def _ensure_dir(self, path: Path) -> None:
        """Ensure a directory exists."""
        path.mkdir(parents=True, exist_ok=True)

    def _write_file(self, path: Path, content: str) -> None:
        """Write content to a file, creating parent directories if needed."""
        self._ensure_dir(path.parent)
        path.write_text(content)


class CompositeGenerator(Generator):
    """
    Generator that runs multiple sub-generators.

    Useful for organizing related generators together.

    Example:
        class DjangoAppGenerator(CompositeGenerator):
            def get_generators(self) -> List[Generator]:
                return [
                    ModelsGenerator(self.spec, self.output_dir),
                    FormsGenerator(self.spec, self.output_dir),
                    ViewsGenerator(self.spec, self.output_dir),
                ]
    """

    @abstractmethod
    def get_generators(self) -> list[Generator]:
        """
        Get the list of sub-generators to run.

        Returns:
            List of Generator instances
        """
        pass

    def generate(self) -> GeneratorResult:
        """
        Run all sub-generators and merge results.

        Returns:
            Combined GeneratorResult from all sub-generators
        """
        combined = GeneratorResult()

        for generator in self.get_generators():
            result = generator.generate()
            combined.merge(result)

            # Stop if a generator had errors
            if not result.success:
                break

        return combined
