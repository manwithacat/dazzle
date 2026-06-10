"""
Scenario and Demo parsing for DAZZLE DSL.

Handles parsing of scenario and demo blocks.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


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
        _parse_construct_header: Any

    def _skip_unknown_or_raise_for_renamed_keyword(self) -> None:
        """Tolerate unknown tokens for forward-compat, but catch the
        cyfuture-pilot footgun: an unmigrated `for ...:` would otherwise
        be silently consumed here and re-dispatch the next token as a
        top-level construct, producing a misleading downstream error
        (typically "Duplicate persona" with the same module name on
        both sides). Raise with an actionable hint when the unknown
        token is `for`.
        """
        tok = self.current_token()
        if tok.type == TokenType.FOR:
            raise make_parse_error(
                "`for` is not valid here. PR #998 renamed `for ...:` → "
                "`as ...:` in persona/scope binding contexts. Run:\n"
                "  sed -i '' -E 's/^([[:space:]]+)for/\\1as/' <dsl-file>",
                self.file,
                tok.line,
                tok.column,
            )
        # #1358: these near-miss key names were silently swallowed for months
        # (support_tickets shipped three inert scenarios). The whole indented
        # block under the unknown key gets consumed token-by-token by the
        # tolerate path, so the author gets zero signal — raise instead.
        if tok.type == TokenType.IDENTIFIER and tok.value in {
            "persona_entries",
            "personas",
            "seed_data_path",
        }:
            hint = (
                'use `seed_script: "<path>"`'
                if tok.value == "seed_data_path"
                else "declare one `as persona <name>:` block per persona"
            )
            raise make_parse_error(
                f"`{tok.value}:` is not a scenario key — {hint}.",
                self.file,
                tok.line,
                tok.column,
            )
        # Unknown but not a renamed-keyword footgun: tolerate.
        self.advance()
        self.skip_newlines()

    def parse_persona(self) -> ir.PersonaSpec:
        """Parse a ``persona <id> ["Label"]:`` declaration.

        Refactored to dispatch-table style (follow-on to #1098 — was the
        #1099 spike target). 3 token-keyed (description/goals/proficiency)
        + 5 IDENT-text-matched (default_workspace/default_route/backed_by/
        link_via/interactive) per-keyword parsers. Unknown-keyword path
        retains the renamed-keyword footgun guard (catches an unmigrated
        ``for ...:`` and raises a #998-actionable error).

        Syntax::

            persona teacher "Teacher":
              description: "A classroom teacher"
              goals: "Grade papers", "Track attendance"
              proficiency: expert
              default_workspace: classroom_view
              default_route: "/classes"
              backed_by: Teacher
              link_via: email
        """
        persona_id, label, _ = self._parse_construct_header(
            TokenType.PERSONA, allow_keyword_name=True
        )
        if label is None:
            label = persona_id

        state = _PersonaState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_PERSONA_KEYWORDS,
            ident_keywords=_PERSONA_IDENT_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_persona,
        )
        self.expect(TokenType.DEDENT)
        return _build_persona(persona_id, label, state)

    def parse_scenario(self) -> ir.ScenarioSpec:
        """
        Parse scenario declaration.

        Syntax:
            scenario busy_term "Busy Term":
              description: "Mid-year state with active workloads"

              as persona teacher:
                start_route: "/classes"
                seed_script: "scenarios/busy_term_teacher.json"

              as persona student:
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

            # as persona <name>: — persona-scoped scenario entry. Renamed
            # from `for persona ...:` to remove the overloaded `for`
            # keyword; `as` is a binding-style introducer matching the
            # other persona/scope contexts.
            elif self.match(TokenType.AS):
                entry = self._parse_persona_scenario_entry()
                persona_entries.append(entry)

            # demo: (inline demo block within scenario)
            elif self.match(TokenType.DEMO):
                demo_fixtures.extend(self._parse_inline_demo())

            else:
                self._skip_unknown_or_raise_for_renamed_keyword()

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
            as persona teacher:
              start_route: "/classes"
              seed_script: "scenarios/busy_term_teacher.json"
        """
        self.expect(TokenType.AS)
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
                self._skip_unknown_or_raise_for_renamed_keyword()

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
        """Parse a string list — supports both inline and multi-line forms.

        Inline form (single line, comma-separated)::

            goals: "Grade papers", "Track attendance"

        Multi-line form (YAML-style indented dash)::

            goals:
              - "Grade papers"
              - "Track attendance"
              - "Plan lessons"

        The multi-line form is detected by the presence of a NEWLINE
        immediately after the `:` (i.e. before any STRING token). Both
        forms coexist; DSL authors may use whichever is ergonomic.

        Fixed in cycle 225 — the prior implementation silently returned
        an empty list for multi-line input and left the ``-`` tokens
        unconsumed, which cascaded into the containing block dropping
        all subsequent fields. This was the root cause of EX-035's
        dead-end navigation finding: fieldtest_hub personas declared
        their ``goals:`` as multi-line lists and consequently lost their
        ``default_workspace`` declarations, which in turn made
        ``_root_redirect`` fall back to ``workspaces[0]`` — the wrong
        workspace for every non-admin persona.
        """
        strings: list[str] = []

        # Multi-line form: after the `:` we see one or more NEWLINEs
        # followed by an INDENT, then a sequence of `- "value"` entries.
        if self.match(TokenType.NEWLINE):
            self.skip_newlines()
            if self.match(TokenType.INDENT):
                self.advance()
                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break
                    if self.match(TokenType.MINUS):
                        self.advance()
                        if self.match(TokenType.STRING):
                            strings.append(self.current_token().value)
                            self.advance()
                        self.skip_newlines()
                    else:
                        # Unexpected token inside a list — skip it so
                        # one malformed entry doesn't abort the whole
                        # block. The containing parser will still see
                        # the DEDENT that terminates the list.
                        self.advance()
                self.expect(TokenType.DEDENT)
            return strings

        # Inline form: comma-separated strings on the current line.
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


# ============================================================ #
# parse_persona — keyword-dispatch decomposition (#1099 spike target) #
# ============================================================ #
#
# The 131-line monolith was replaced (v0.70.20) with the dispatch
# pattern shipped in #1097 — completing the spike's promise. Three
# token-keyed parsers + five IDENT-text-matched parsers + the
# renamed-keyword footgun guard for unknown keywords.


_PROFICIENCY_VALUES = ("novice", "intermediate", "expert")


@dataclass
class _PersonaState:
    """Accumulator for :meth:`ScenarioParserMixin.parse_persona`."""

    description: str | None = None
    goals: list[str] = field(default_factory=list)
    proficiency: str = "intermediate"
    default_workspace: str | None = None
    default_route: str | None = None
    backed_by: str | None = None
    link_via: str = "email"
    interactive: bool = True
    role: str | None = None  # #1147: explicit role override
    nav_ref: str | None = None  # #1324: uses nav <name>


# ---------- Token-keyed keyword parsers ---------- #


def _p_kw_description(parser: Any, state: _PersonaState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.description = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _p_kw_goals(parser: Any, state: _PersonaState) -> None:
    """``goals: "goal1", "goal2"`` — list of quoted strings."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.goals = parser._parse_string_list()
    parser.skip_newlines()


def _p_kw_proficiency(parser: Any, state: _PersonaState) -> None:
    """``proficiency: novice|intermediate|expert`` — validated at parse time."""
    parser.advance()
    parser.expect(TokenType.COLON)
    value = parser.expect_identifier_or_keyword().value
    if value not in _PROFICIENCY_VALUES:
        token = parser.current_token()
        raise make_parse_error(
            f"Invalid proficiency level: {value}. Must be novice, intermediate, or expert",
            parser.file,
            token.line,
            token.column,
        )
    state.proficiency = value
    parser.skip_newlines()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _p_kw_default_workspace(parser: Any, state: _PersonaState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.default_workspace = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _p_kw_default_route(parser: Any, state: _PersonaState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.default_route = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _p_kw_backed_by(parser: Any, state: _PersonaState) -> None:
    """``backed_by: EntityName`` — closes EX-045 (cycle 248)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.backed_by = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _p_kw_link_via(parser: Any, state: _PersonaState) -> None:
    """``link_via: field_name`` — backed_by link column (cycle 248, EX-045)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.link_via = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _p_kw_role(parser: Any, state: _PersonaState) -> None:
    """``role: <identifier>`` — RBAC role this persona maps to (#1147).

    Decouples persona display identity (``id``, ``label``) from the
    role name used in ``permit:``/``scope:``/``as:`` clauses. Lets
    two personas share a role while keeping distinct UX presence.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    state.role = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _p_kw_interactive(parser: Any, state: _PersonaState) -> None:
    """``interactive: true|false`` — flag the persona as interactive (#780)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        state.interactive = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        state.interactive = False
    else:
        token = parser.current_token()
        raise make_parse_error(
            f"Expected true or false for interactive, got {token.value}",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _p_kw_uses_nav(parser: Any, state: _PersonaState) -> None:
    """``uses nav <name>`` — bind the persona's single nav definition (#1324)."""
    parser.advance()  # consume `uses`
    if not parser.match(TokenType.NAV):
        token = parser.current_token()
        raise make_parse_error(
            "Expected `nav` after `uses` in a persona block (`uses nav <name>`)",
            parser.file,
            token.line,
            token.column,
        )
    parser.advance()  # consume `nav`
    state.nav_ref = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


# ---------- Dispatch tables ---------- #


_PERSONA_KEYWORDS: dict[TokenType, KeywordParser[_PersonaState]] = {
    TokenType.DESCRIPTION: _p_kw_description,
    TokenType.GOALS: _p_kw_goals,
    TokenType.PROFICIENCY: _p_kw_proficiency,
    TokenType.USES: _p_kw_uses_nav,
}


_PERSONA_IDENT_KEYWORDS: dict[str, KeywordParser[_PersonaState]] = {
    "default_workspace": _p_kw_default_workspace,
    "default_route": _p_kw_default_route,
    "backed_by": _p_kw_backed_by,
    "link_via": _p_kw_link_via,
    "interactive": _p_kw_interactive,
    "role": _p_kw_role,
}


def _on_unknown_persona(parser: Any) -> None:
    """Defer to the mixin's renamed-keyword footgun guard.

    Wrapped here so the dispatch-helper's ``_ParserLike`` Protocol
    type doesn't need to know about the mixin-specific helper.
    Parser argument is typed Any to bypass the Protocol.
    """
    parser._skip_unknown_or_raise_for_renamed_keyword()


# ---------- Builder ---------- #


def _build_persona(persona_id: str, label: str, state: _PersonaState) -> ir.PersonaSpec:
    return ir.PersonaSpec(
        id=persona_id,
        label=label,
        description=state.description,
        goals=state.goals,
        proficiency_level=state.proficiency,  # type: ignore[arg-type]
        default_workspace=state.default_workspace,
        default_route=state.default_route,
        backed_by=state.backed_by,
        link_via=state.link_via,
        interactive=state.interactive,
        role=state.role,
        nav_ref=state.nav_ref,
    )
