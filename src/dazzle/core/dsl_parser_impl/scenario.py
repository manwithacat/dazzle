"""
Scenario and Demo parsing for DAZZLE DSL.

Handles parsing of scenario and demo blocks for the Dazzle Bar
developer overlay system.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class ScenarioParserMixin:
    """
    Mixin providing scenario and demo block parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any

    def parse_persona(self) -> ir.PersonaSpec:
        """
        Parse persona declaration.

        Syntax:
            persona teacher "Teacher":
              description: "A classroom teacher"
              goals: "Grade papers", "Track attendance"
              proficiency: expert
              default_workspace: classroom_view
              default_route: "/classes"
        """
        self.expect(TokenType.PERSONA)
        persona_id = self.expect_identifier_or_keyword().value
        label = self.expect(TokenType.STRING).value if self.match(TokenType.STRING) else persona_id

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description: str | None = None
        goals: list[str] = []
        proficiency: str = "intermediate"
        default_workspace: str | None = None
        default_route: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # description: "..."
            if self.match(TokenType.DESCRIPTION):
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # goals: "goal1", "goal2"
            elif self.match(TokenType.GOALS):
                self.advance()
                self.expect(TokenType.COLON)
                goals = self._parse_string_list()
                self.skip_newlines()

            # proficiency: novice | intermediate | expert
            elif self.match(TokenType.PROFICIENCY):
                self.advance()
                self.expect(TokenType.COLON)
                proficiency = self.expect_identifier_or_keyword().value
                if proficiency not in ("novice", "intermediate", "expert"):
                    token = self.current_token()
                    raise make_parse_error(
                        f"Invalid proficiency level: {proficiency}. Must be novice, intermediate, or expert",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # default_workspace: workspace_name
            elif (
                self.match(TokenType.IDENTIFIER)
                and self.current_token().value == "default_workspace"
            ):
                self.advance()
                self.expect(TokenType.COLON)
                default_workspace = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # default_route: "/path"
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "default_route":
                self.advance()
                self.expect(TokenType.COLON)
                default_route = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                # Skip unknown fields
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.PersonaSpec(
            id=persona_id,
            label=label,
            description=description,
            goals=goals,
            proficiency_level=proficiency,  # type: ignore[arg-type]
            default_workspace=default_workspace,
            default_route=default_route,
        )

    def parse_scenario(self) -> ir.ScenarioSpec:
        """
        Parse scenario declaration.

        Syntax:
            scenario busy_term "Busy Term":
              description: "Mid-year state with active workloads"

              for persona teacher:
                start_route: "/classes"
                seed_script: "scenarios/busy_term_teacher.json"

              for persona student:
                start_route: "/my-assignments"
        """
        self.expect(TokenType.SCENARIO)
        scenario_id = self.expect_identifier_or_keyword().value
        name = self.expect(TokenType.STRING).value if self.match(TokenType.STRING) else scenario_id

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description: str | None = None
        seed_data_path: str | None = None
        persona_entries: list[ir.PersonaScenarioEntry] = []
        demo_fixtures: list[ir.DemoFixture] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # description: "..."
            if self.match(TokenType.DESCRIPTION):
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # seed_script: "path/to/data.json"
            elif self.match(TokenType.SEED_SCRIPT):
                self.advance()
                self.expect(TokenType.COLON)
                seed_data_path = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # for persona <name>:
            elif self.match(TokenType.FOR):
                entry = self._parse_persona_scenario_entry()
                persona_entries.append(entry)

            # demo: (inline demo block within scenario)
            elif self.match(TokenType.DEMO):
                demo_fixtures.extend(self._parse_inline_demo())

            else:
                # Skip unknown fields
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ScenarioSpec(
            id=scenario_id,
            name=name,
            description=description,
            persona_entries=persona_entries,
            seed_data_path=seed_data_path,
            demo_fixtures=demo_fixtures,
        )

    def _parse_persona_scenario_entry(self) -> ir.PersonaScenarioEntry:
        """
        Parse per-persona scenario entry.

        Syntax:
            for persona teacher:
              start_route: "/classes"
              seed_script: "scenarios/busy_term_teacher.json"
        """
        self.expect(TokenType.FOR)
        self.expect(TokenType.PERSONA)
        persona_id = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        start_route: str = "/"
        seed_script: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # start_route: "/path"
            if self.match(TokenType.START_ROUTE):
                self.advance()
                self.expect(TokenType.COLON)
                start_route = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # seed_script: "path/to/data.json"
            elif self.match(TokenType.SEED_SCRIPT):
                self.advance()
                self.expect(TokenType.COLON)
                seed_script = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                # Skip unknown fields
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.PersonaScenarioEntry(
            persona_id=persona_id,
            start_route=start_route,
            seed_script=seed_script,
        )

    def parse_demo(self) -> list[ir.DemoFixture]:
        """
        Parse top-level demo block.

        Syntax:
            demo:
              Task:
                - title: "Grade assignments", status: "pending"
                - title: "Prepare lecture", status: "done"
              Student:
                - name: "Alice", grade: 85
        """
        return self._parse_inline_demo()

    def _parse_inline_demo(self) -> list[ir.DemoFixture]:
        """
        Parse inline demo block (shared between top-level and scenario-embedded).
        """
        self.expect(TokenType.DEMO)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        fixtures: list[ir.DemoFixture] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # EntityName:
            if self.match(TokenType.IDENTIFIER):
                entity_name = self.current_token().value
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()

                records = self._parse_demo_records()
                fixtures.append(ir.DemoFixture(entity=entity_name, records=records))

            else:
                # Skip unknown content
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return fixtures

    def _parse_demo_records(self) -> list[dict[str, Any]]:
        """
        Parse list of demo records for an entity.

        Syntax:
            - title: "Grade assignments", status: "pending"
            - title: "Prepare lecture", status: "done"
        """
        records: list[dict[str, Any]] = []

        # Check for INDENT (records are indented under entity)
        if self.match(TokenType.INDENT):
            self.advance()

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break

                # Each record starts with -
                if self.match(TokenType.MINUS):
                    self.advance()
                    record = self._parse_demo_record()
                    records.append(record)
                    self.skip_newlines()
                else:
                    # Skip unknown content
                    self.advance()
                    self.skip_newlines()

            self.expect(TokenType.DEDENT)

        return records

    def _parse_demo_record(self) -> dict[str, Any]:
        """
        Parse a single demo record (field: value pairs).

        Syntax:
            title: "Grade assignments", status: "pending", completed: false

        Note: Field names can be keywords (like 'subject', 'description', 'status')
        so we use expect_identifier_or_keyword() instead of just checking for IDENTIFIER.
        """
        record: dict[str, Any] = {}

        # Parse field: value pairs until newline
        while True:
            if self.match(TokenType.NEWLINE) or self.match(TokenType.DEDENT):
                break

            # field_name: value - field names can be keywords too
            if self.match(TokenType.IDENTIFIER) or self._is_keyword_as_field():
                field_name = self.current_token().value
                self.advance()
                self.expect(TokenType.COLON)
                value = self._parse_demo_value()
                record[field_name] = value

                # Check for comma (more fields)
                if self.match(TokenType.COMMA):
                    self.advance()
                else:
                    break
            else:
                break

        return record

    def _is_keyword_as_field(self) -> bool:
        """Check if current token is a keyword that can be used as a field name."""
        # Common field names that are also keywords in the DSL
        # Only include TokenTypes that actually exist
        keyword_field_types = [
            TokenType.SUBJECT,
            TokenType.DESCRIPTION,
            TokenType.STATUS,
            TokenType.EMAIL,
        ]
        return any(self.match(t) for t in keyword_field_types)

    def _parse_demo_value(self) -> Any:
        """
        Parse a demo field value.

        Supports: strings, numbers, booleans
        """
        if self.match(TokenType.STRING):
            value = self.current_token().value
            self.advance()
            return value
        elif self.match(TokenType.NUMBER):
            value = self.current_token().value
            self.advance()
            # Try to parse as int or float
            try:
                if "." in value:
                    return float(value)
                return int(value)
            except ValueError:
                return value
        elif self.match(TokenType.TRUE):
            self.advance()
            return True
        elif self.match(TokenType.FALSE):
            self.advance()
            return False
        else:
            # Treat as identifier (for enum values, etc.)
            value = self.expect_identifier_or_keyword().value
            return value

    def _parse_string_list(self) -> list[str]:
        """Parse a comma-separated list of strings."""
        strings: list[str] = []

        while True:
            if self.match(TokenType.STRING):
                strings.append(self.current_token().value)
                self.advance()

                if self.match(TokenType.COMMA):
                    self.advance()
                else:
                    break
            else:
                break

        return strings
