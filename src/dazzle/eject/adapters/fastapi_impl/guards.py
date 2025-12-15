"""
FastAPI guard generation.

Generates state machine transition guards from entity specifications.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Callable

from dazzle.eject.generator import GeneratorResult

from .utils import pascal_case, snake_case

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec


def generate_entity_guards(entity: EntitySpec) -> str:
    """Generate state machine guards for an entity."""
    name = entity.name
    snake = snake_case(name)
    sm = entity.state_machine

    if not sm:
        return ""

    # Find the status field
    status_field = sm.status_field
    status_enum = f"{name}{pascal_case(status_field)}"

    # Build valid transitions map
    transitions_code = "    VALID_TRANSITIONS = {\n"
    transitions_by_from: dict[str, list[str]] = {}
    for trans in sm.transitions:
        from_state = trans.from_state
        to_state = trans.to_state
        if from_state not in transitions_by_from:
            transitions_by_from[from_state] = []
        transitions_by_from[from_state].append(to_state)

    for from_state, to_states in transitions_by_from.items():
        if from_state == "*":
            continue  # Handle wildcard separately
        to_list = ", ".join(f"{status_enum}.{s.upper()}" for s in to_states)
        transitions_code += f"        {status_enum}.{from_state.upper()}: [{to_list}],\n"
    transitions_code += "    }"

    # Build guard checks
    guard_checks = []
    for trans in sm.transitions:
        for guard in trans.guards:
            if guard.requires_field:
                check = f'''
        if from_status == {status_enum}.{trans.from_state.upper()} and to_status == {status_enum}.{trans.to_state.upper()}:
            if entity.{guard.requires_field} is None:
                return False, "{guard.requires_field} is required for this transition"'''
                guard_checks.append(check)
            elif guard.requires_role:
                check = f'''
        if from_status == {status_enum}.{trans.from_state.upper()} and to_status == {status_enum}.{trans.to_state.upper()}:
            if not context.has_role("{guard.requires_role}"):
                return False, "Only {guard.requires_role} can perform this transition"'''
                guard_checks.append(check)

    guard_checks_code = "\n".join(guard_checks) if guard_checks else ""

    content = dedent(f'''
        """
        State machine guards for {name} entity.
        Generated from DSL - DO NOT EDIT.
        """
        from ..models.{snake} import {name}, {status_enum}
        from ..access.context import RequestContext


        class TransitionError(Exception):
            """Raised when a state transition is not allowed."""
            pass


        class {name}TransitionGuard:
            """Enforce valid state transitions for {name}."""

        {transitions_code}

            def can_transition(
                self,
                entity: {name},
                to_status: {status_enum},
                context: RequestContext,
            ) -> tuple[bool, str | None]:
                """Check if transition is allowed. Returns (allowed, error_message)."""
                from_status = entity.{status_field}

                # Check if transition is valid
                valid_targets = self.VALID_TRANSITIONS.get(from_status, [])
                if to_status not in valid_targets:
                    return False, f"Cannot transition from {{from_status}} to {{to_status}}"

                # Check guards{guard_checks_code}

                return True, None

            def assert_transition(
                self,
                entity: {name},
                to_status: {status_enum},
                context: RequestContext,
            ) -> None:
                """Raise exception if transition not allowed."""
                allowed, error = self.can_transition(entity, to_status, context)
                if not allowed:
                    raise TransitionError(error)
    ''')

    return content.strip()


class GuardGenerator:
    """Generates state machine guards for FastAPI adapter."""

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

    def generate_guards(self) -> GeneratorResult:
        """Generate state machine transition guards."""
        result = GeneratorResult()

        guards_dir = self.backend_dir / "guards"
        self._ensure_dir(guards_dir)

        imports = ['"""State machine transition guards."""\n']

        for entity in self.spec.domain.entities:
            if entity.state_machine:
                guard_content = generate_entity_guards(entity)
                guard_path = guards_dir / f"{snake_case(entity.name)}_transitions.py"
                self._write_file(guard_path, guard_content)
                result.add_file(guard_path)

                imports.append(
                    f"from .{snake_case(entity.name)}_transitions import {entity.name}TransitionGuard"
                )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = guards_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result
