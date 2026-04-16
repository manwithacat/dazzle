"""Cycle 248 — persona backed_by / link_via (EX-045 closed).

Tests the DSL grammar extension, IR storage, and linker validation
for the ``backed_by`` / ``link_via`` fields on PersonaSpec.
"""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import FieldModifier, FieldTypeKind

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestPersonaBackedByParser:
    """Grammar accepts ``backed_by:`` and ``link_via:`` inside persona blocks."""

    def _parse_personas(self, dsl_body: str) -> list[ir.PersonaSpec]:
        dsl = f"""
module testapp
app testapp "Test App"

entity Tester "Tester":
  id: uuid pk
  name: str(100) required
  email: email required

entity Device "Device":
  id: uuid pk
  name: str(100) required

{dsl_body}
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        return list(fragment.personas)

    def test_backed_by_parsed(self) -> None:
        personas = self._parse_personas(
            'persona tester "Field Tester":\n  description: "Tests devices"\n  backed_by: Tester\n'
        )
        assert len(personas) == 1
        assert personas[0].backed_by == "Tester"
        assert personas[0].link_via == "email"  # default

    def test_link_via_override(self) -> None:
        personas = self._parse_personas(
            'persona tester "Field Tester":\n  backed_by: Tester\n  link_via: id\n'
        )
        assert personas[0].backed_by == "Tester"
        assert personas[0].link_via == "id"

    def test_no_backed_by_leaves_none(self) -> None:
        personas = self._parse_personas('persona admin "Admin":\n  description: "Full access"\n')
        assert personas[0].backed_by is None
        assert personas[0].link_via == "email"

    def test_backed_by_coexists_with_other_fields(self) -> None:
        personas = self._parse_personas(
            'persona tester "Field Tester":\n'
            '  description: "Tests devices"\n'
            "  proficiency: novice\n"
            "  backed_by: Tester\n"
            "  link_via: name\n"
        )
        p = personas[0]
        assert p.description == "Tests devices"
        assert p.proficiency_level == "novice"
        assert p.backed_by == "Tester"
        assert p.link_via == "name"


# ---------------------------------------------------------------------------
# Linker validation
# ---------------------------------------------------------------------------


class TestPersonaBackedByValidation:
    """Linker validates backed_by entity and link_via field existence."""

    def _make_appspec(self, personas, entities=None):
        if entities is None:
            entities = [
                ir.EntitySpec(
                    name="Tester",
                    title="Tester",
                    fields=[
                        ir.FieldSpec(
                            name="id",
                            type=ir.FieldType(kind=FieldTypeKind.UUID),
                            modifiers=[FieldModifier.PK],
                        ),
                        ir.FieldSpec(
                            name="name",
                            type=ir.FieldType(kind=FieldTypeKind.STR, max_length=100),
                        ),
                        ir.FieldSpec(
                            name="email",
                            type=ir.FieldType(kind=FieldTypeKind.EMAIL),
                        ),
                    ],
                ),
            ]
        return ir.AppSpec(
            name="test",
            title="Test",
            module="test",
            domain=ir.DomainSpec(entities=entities),
            surfaces=[],
            workspaces=[],
            personas=personas,
        )

    def _validate(self, appspec):
        from dazzle.core.validator import _validate_persona_backed_by

        return _validate_persona_backed_by(appspec)

    def test_valid_backed_by_produces_no_errors(self) -> None:
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="tester", label="Tester", backed_by="Tester"),
            ]
        )
        errors = self._validate(appspec)
        assert errors == []

    def test_backed_by_nonexistent_entity(self) -> None:
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="tester", label="Tester", backed_by="Ghost"),
            ]
        )
        errors = self._validate(appspec)
        assert len(errors) == 1
        assert "Ghost" in errors[0]
        assert "does not exist" in errors[0]

    def test_link_via_nonexistent_field(self) -> None:
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="tester", label="Tester", backed_by="Tester", link_via="phone"),
            ]
        )
        errors = self._validate(appspec)
        assert len(errors) == 1
        assert "phone" in errors[0]
        assert "no field named" in errors[0]

    def test_duplicate_backed_by_entity(self) -> None:
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="tester", label="Tester", backed_by="Tester"),
                ir.PersonaSpec(id="senior", label="Senior Tester", backed_by="Tester"),
            ]
        )
        errors = self._validate(appspec)
        assert len(errors) == 1
        assert "already claims" in errors[0]

    def test_no_backed_by_no_errors(self) -> None:
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="admin", label="Admin"),
            ]
        )
        errors = self._validate(appspec)
        assert errors == []

    def test_link_via_id_valid(self) -> None:
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="tester", label="Tester", backed_by="Tester", link_via="id"),
            ]
        )
        errors = self._validate(appspec)
        assert errors == []

    def test_multiple_personas_different_entities(self) -> None:
        entities = [
            ir.EntitySpec(
                name="Tester",
                title="Tester",
                fields=[
                    ir.FieldSpec(
                        name="id",
                        type=ir.FieldType(kind=FieldTypeKind.UUID),
                        modifiers=[FieldModifier.PK],
                    ),
                    ir.FieldSpec(name="email", type=ir.FieldType(kind=FieldTypeKind.EMAIL)),
                ],
            ),
            ir.EntitySpec(
                name="Device",
                title="Device",
                fields=[
                    ir.FieldSpec(
                        name="id",
                        type=ir.FieldType(kind=FieldTypeKind.UUID),
                        modifiers=[FieldModifier.PK],
                    ),
                    ir.FieldSpec(
                        name="name", type=ir.FieldType(kind=FieldTypeKind.STR, max_length=100)
                    ),
                ],
            ),
        ]
        appspec = self._make_appspec(
            personas=[
                ir.PersonaSpec(id="tester", label="Tester", backed_by="Tester"),
                ir.PersonaSpec(id="device_owner", label="Owner", backed_by="Device", link_via="id"),
            ],
            entities=entities,
        )
        errors = self._validate(appspec)
        assert errors == []
