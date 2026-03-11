"""
Rhythm parser mixin for DAZZLE DSL.

Parses rhythm blocks with phase/scene structure.

DSL Syntax (v0.39.0):
    rhythm onboarding "New User Onboarding":
      persona: new_user
      cadence: "quarterly"

      phase discovery:
        scene browse "Browse Courses":
          on: course_list
          action: filter, browse
          entity: Course
          expects: "visible_results"
          story: "ST-020"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class RhythmParserMixin:
    """Parser mixin for rhythm blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _source_location: Any

    def parse_rhythm(self) -> ir.RhythmSpec:
        """
        Parse a rhythm block.

        Grammar:
            rhythm IDENTIFIER STRING? COLON NEWLINE INDENT
              persona COLON IDENTIFIER NEWLINE
              [cadence COLON STRING NEWLINE]
              (phase IDENTIFIER COLON NEWLINE INDENT
                (scene IDENTIFIER STRING? COLON NEWLINE INDENT
                  on COLON IDENTIFIER NEWLINE
                  [action COLON identifier_list NEWLINE]
                  [entity COLON IDENTIFIER NEWLINE]
                  [expects COLON STRING NEWLINE]
                  [story COLON (IDENTIFIER | STRING) NEWLINE]
                DEDENT)*
              DEDENT)*
            DEDENT
        """
        loc = self._source_location()

        name = self.expect_identifier_or_keyword().value
        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        persona = None
        cadence = None
        phases: list[ir.PhaseSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.PERSONA):
                self.advance()
                self.expect(TokenType.COLON)
                persona = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif self.match(TokenType.PHASE):
                self.advance()
                phases.append(self._parse_rhythm_phase())

            else:
                token = self.current_token()
                if token.value == "cadence":
                    self.advance()
                    self.expect(TokenType.COLON)
                    cadence = self.expect(TokenType.STRING).value
                    self.skip_newlines()
                else:
                    self.advance()
                    if self.match(TokenType.COLON):
                        self.advance()
                        self._skip_rhythm_field()

        self.expect(TokenType.DEDENT)

        if persona is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Rhythm missing required 'persona' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.RhythmSpec(
            name=name,
            title=title,
            persona=persona,
            cadence=cadence,
            phases=phases,
            source=loc,
        )

    def _parse_rhythm_phase(self) -> ir.PhaseSpec:
        """Parse a phase block within a rhythm."""
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        scenes: list[ir.SceneSpec] = []
        kind: ir.PhaseKind | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.SCENE):
                self.advance()
                scenes.append(self._parse_rhythm_scene())
            else:
                token = self.current_token()
                if token.value == "kind":
                    self.advance()
                    self.expect(TokenType.COLON)
                    kind_value = self.expect_identifier_or_keyword().value
                    try:
                        kind = ir.PhaseKind(kind_value)
                    except ValueError:
                        kind = None
                    self.skip_newlines()
                else:
                    self.advance()
                    if self.match(TokenType.COLON):
                        self.advance()
                        self._skip_rhythm_field()

        self.expect(TokenType.DEDENT)

        return ir.PhaseSpec(name=name, kind=kind, scenes=scenes, source=loc)

    def _parse_rhythm_scene(self) -> ir.SceneSpec:
        """Parse a scene block within a phase."""
        loc = self._source_location()

        name = self.expect_identifier_or_keyword().value
        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        surface = None
        actions: list[str] = []
        entity = None
        expects = None
        story = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "on":
                self.advance()
                self.expect(TokenType.COLON)
                surface = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif field_name == "action":
                self.advance()
                self.expect(TokenType.COLON)
                actions = self._parse_rhythm_identifier_list()
                self.skip_newlines()

            elif field_name == "entity":
                self.advance()
                self.expect(TokenType.COLON)
                entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif field_name == "expects":
                self.advance()
                self.expect(TokenType.COLON)
                expects = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "story":
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.STRING):
                    story = self.advance().value
                else:
                    story = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            else:
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_rhythm_field()

        self.expect(TokenType.DEDENT)

        if surface is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Scene missing required 'on' field (surface reference)",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.SceneSpec(
            name=name,
            title=title,
            surface=surface,
            actions=actions,
            entity=entity,
            expects=expects,
            story=story,
            source=loc,
        )

    def _parse_rhythm_identifier_list(self) -> list[str]:
        """Parse comma-separated identifiers: submit, browse."""
        items: list[str] = []
        items.append(self.expect_identifier_or_keyword().value)

        while self.match(TokenType.COMMA):
            self.advance()
            items.append(self.expect_identifier_or_keyword().value)

        return items

    def _skip_rhythm_field(self) -> None:
        """Skip tokens until we reach the next field or end of block."""
        while not self.match(
            TokenType.PHASE,
            TokenType.SCENE,
            TokenType.PERSONA,
            TokenType.DEDENT,
            TokenType.EOF,
            TokenType.NEWLINE,
        ):
            self.advance()
        self.skip_newlines()
