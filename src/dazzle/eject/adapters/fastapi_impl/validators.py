"""
FastAPI validator generation.

Generates invariant validators from entity specifications.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from dazzle.eject.generator import GeneratorResult

from .utils import snake_case

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec, InvariantSpec


def invariant_to_python(inv: InvariantSpec, entity: EntitySpec) -> str:
    """Convert invariant expression to Python code."""
    # This is a simplified implementation
    # A full implementation would properly parse the invariant expression
    _expr = inv.expression  # Reserved for future implementation
    _entity_name = entity.name  # Reserved for future implementation

    # For now, return a placeholder that shows the structure
    # In production, this would properly convert the IR expression to Python
    return "True  # TODO: Implement invariant check"


def generate_entity_validators(entity: EntitySpec) -> str:
    """Generate invariant validators for an entity."""
    name = entity.name
    snake = snake_case(name)

    # Generate validation methods for each invariant
    validation_methods = []
    validation_calls = []

    for i, inv in enumerate(entity.invariants):
        method_name = f"validate_invariant_{i}"
        message = inv.message or "Invariant violation"
        code = inv.code or f"{name.upper()}_INVARIANT_{i}"

        # Convert expression to Python (simplified)
        expr_str = invariant_to_python(inv, entity)

        method = f'''
    def {method_name}(self, entity: {name}) -> None:
        """Invariant: {expr_str}"""
        if not ({expr_str}):
            raise {name}InvariantError(
                message="{message}",
                code="{code}",
            )'''
        validation_methods.append(method)
        validation_calls.append(f"        self.{method_name}(entity)")

    methods_code = "\n".join(validation_methods)
    calls_code = "\n".join(validation_calls)

    content = dedent(f'''
        """
        Invariant validators for {name} entity.
        Generated from DSL - DO NOT EDIT.
        """
        from ..models.{snake} import {name}


        class {name}InvariantError(Exception):
            """Raised when a {name} invariant is violated."""

            def __init__(self, message: str, code: str):
                super().__init__(message)
                self.code = code


        class {name}InvariantValidator:
            """Validate {name} invariants."""

            def validate(self, entity: {name}) -> None:
                """Validate all invariants. Raises {name}InvariantError on failure."""
        {calls_code}
        {methods_code}

            def is_valid(self, entity: {name}) -> tuple[bool, list[str]]:
                """Check all invariants without raising. Returns (valid, errors)."""
                errors = []
                try:
                    self.validate(entity)
                except {name}InvariantError as e:
                    errors.append(f"[{{e.code}}] {{e}}")
                return len(errors) == 0, errors
    ''')

    return content.strip()


class ValidatorGenerator:
    """Generates invariant validators for FastAPI adapter."""

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        write_file_fn: Callable[[Path, str], None],
        ensure_dir_fn: Callable[[Path], None],
    ) -> None:
        self.spec = spec
        self.output_dir = output_dir
        self.backend_dir = output_dir / "backend"
        self._write_file = write_file_fn
        self._ensure_dir = ensure_dir_fn

    def generate_validators(self) -> GeneratorResult:
        """Generate invariant validators."""
        result = GeneratorResult()

        validators_dir = self.backend_dir / "validators"
        self._ensure_dir(validators_dir)

        imports = ['"""Invariant validators."""\n']

        for entity in self.spec.domain.entities:
            if entity.invariants:
                validator_content = generate_entity_validators(entity)
                validator_path = validators_dir / f"{snake_case(entity.name)}_invariants.py"
                self._write_file(validator_path, validator_content)
                result.add_file(validator_path)

                imports.append(
                    f"from .{snake_case(entity.name)}_invariants import {entity.name}InvariantValidator"
                )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = validators_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result
