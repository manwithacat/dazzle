"""
Base generator classes for AWS CDK code generation.

These classes mirror the eject system's Generator pattern,
adapted for infrastructure code generation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core import ir

    from .analyzer import AWSRequirements
    from .config import DeploymentConfig


# =============================================================================
# Generator Result
# =============================================================================


@dataclass
class CDKGeneratorResult:
    """Result from CDK code generation."""

    files_created: list[Path] = field(default_factory=list)
    stack_names: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if generation was successful."""
        return len(self.errors) == 0

    def add_file(self, path: Path) -> None:
        """Add a generated file to the result."""
        self.files_created.append(path)

    def add_stack(self, name: str) -> None:
        """Add a generated stack to the result."""
        self.stack_names.append(name)

    def add_artifact(self, key: str, value: Any) -> None:
        """Add an artifact for other generators to use."""
        self.artifacts[key] = value

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def merge(self, other: CDKGeneratorResult) -> None:
        """Merge another result into this one."""
        self.files_created.extend(other.files_created)
        self.stack_names.extend(other.stack_names)
        self.artifacts.update(other.artifacts)
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


# =============================================================================
# Base Generator
# =============================================================================


class CDKGenerator(ABC):
    """
    Base class for CDK code generators.

    Generators take AppSpec + AWSRequirements + Config and produce
    CDK Python code files.
    """

    def __init__(
        self,
        spec: ir.AppSpec,
        aws_reqs: AWSRequirements,
        config: DeploymentConfig,
        output_dir: Path,
    ):
        self.spec = spec
        self.aws_reqs = aws_reqs
        self.config = config
        self.output_dir = output_dir

    @abstractmethod
    def generate(self) -> CDKGeneratorResult:
        """
        Generate CDK code.

        Returns:
            CDKGeneratorResult with generated files and metadata
        """
        pass

    def _ensure_dir(self, path: Path) -> None:
        """Ensure a directory exists."""
        path.mkdir(parents=True, exist_ok=True)

    def _write_file(self, path: Path, content: str) -> None:
        """Write content to a file."""
        self._ensure_dir(path.parent)
        path.write_text(content)

    def _get_app_name(self) -> str:
        """Get sanitized application name."""
        name = self.spec.name.lower()
        # Replace spaces and special chars with hyphens
        name = "".join(c if c.isalnum() else "-" for c in name)
        # Remove consecutive hyphens
        while "--" in name:
            name = name.replace("--", "-")
        return name.strip("-")

    def _get_stack_prefix(self) -> str:
        """Get stack name prefix."""
        return self.config.output.stack_name_prefix or self._get_app_name()


# =============================================================================
# Stack Generator
# =============================================================================


class StackGenerator(CDKGenerator):
    """
    Base class for generating a single CDK stack.

    Each stack generator produces one Python file containing
    a CDK Stack class.
    """

    @property
    @abstractmethod
    def stack_name(self) -> str:
        """Get the stack name (e.g., 'Network', 'Data', 'Compute')."""
        pass

    @property
    def stack_class_name(self) -> str:
        """Get the Python class name for the stack."""
        return f"{self.stack_name}Stack"

    @property
    def stack_file_name(self) -> str:
        """Get the Python file name for the stack."""
        return f"{self.stack_name.lower()}_stack.py"

    def should_generate(self) -> bool:
        """Check if this stack should be generated based on requirements."""
        return True

    def generate(self) -> CDKGeneratorResult:
        """Generate the stack file."""
        result = CDKGeneratorResult()

        if not self.should_generate():
            return result

        try:
            code = self._generate_stack_code()
            stack_path = self.output_dir / "stacks" / self.stack_file_name

            self._write_file(stack_path, code)
            result.add_file(stack_path)
            result.add_stack(self.stack_name)

        except Exception as e:
            result.add_error(f"Failed to generate {self.stack_name} stack: {e}")

        return result

    @abstractmethod
    def _generate_stack_code(self) -> str:
        """Generate the Python code for the stack."""
        pass

    def _generate_header(self) -> str:
        """Generate the file header with imports."""
        return f'''"""
{self.stack_name} stack for {self.spec.name}.

Generated by: dazzle deploy generate
DO NOT EDIT - Changes will be overwritten.
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct
'''

    def _indent(self, code: str, spaces: int = 8) -> str:
        """Indent code by the specified number of spaces."""
        indent = " " * spaces
        lines = code.split("\n")
        return "\n".join(indent + line if line.strip() else line for line in lines)


# =============================================================================
# Composite Generator
# =============================================================================


class CompositeGenerator(CDKGenerator):
    """
    Generator that composes multiple sub-generators.

    Runs sub-generators in sequence and merges their results.
    """

    @abstractmethod
    def get_generators(self) -> list[CDKGenerator]:
        """Get the list of sub-generators to run."""
        pass

    def generate(self) -> CDKGeneratorResult:
        """Run all sub-generators and merge results."""
        combined = CDKGeneratorResult()

        for generator in self.get_generators():
            result = generator.generate()
            combined.merge(result)

            # Stop on first error
            if not result.success:
                break

        return combined


__all__ = [
    "CDKGeneratorResult",
    "CDKGenerator",
    "StackGenerator",
    "CompositeGenerator",
]
