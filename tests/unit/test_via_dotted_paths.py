"""Dotted FK predicates inside `via` clauses for scope rules (#858).

The `via EntityName(field = target, ...)` scope form previously required
flat single-segment junction fields. AegisMark hit this when expressing
"a teacher sees a pupil iff the pupil is enrolled in a class the teacher
teaches" — a two-hop traversal from the junction:

    via ClassEnrolment(
      student_profile = id,
      teaching_group.teacher.user = current_user
    )

After this fix:
1. The parser accumulates dotted path segments on the junction-field side.
2. The predicate compiler expands dotted paths into nested `IN (SELECT ...)`
   subqueries, walking the FK graph segment-by-segment.
3. The validator resolves each segment through the FK graph and reports a
   clear `dazzle validate` error when a hop doesn't exist.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.parser import parse_modules


def _appspec(dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


_TEACHER_DSL = """module t
app T "T"

persona teacher "Teacher":
  description: "Classroom teacher"

entity User "User":
  id: uuid pk
  email: str(200)

entity StaffMember "Staff":
  id: uuid pk
  name: str(200)
  user: ref User

entity TeachingGroup "TG":
  id: uuid pk
  name: str(200)
  teacher: ref StaffMember

entity StudentProfile "SP":
  id: uuid pk
  name: str(200)
  scope:
    read: via ClassEnrolment(student_profile = id, teaching_group.teacher.user = current_user)
      for: teacher

entity ClassEnrolment "CE":
  id: uuid pk
  student_profile: ref StudentProfile
  teaching_group: ref TeachingGroup

surface student_list "Students":
  uses entity StudentProfile
  mode: list
"""


class TestParserAcceptsDottedVia:
    def test_dotted_via_parses(self, tmp_path: Path) -> None:
        """Parsing a dotted junction-field no longer errors at the `.` token."""
        spec = _appspec(_TEACHER_DSL, tmp_path)
        sp = next(e for e in spec.domain.entities if e.name == "StudentProfile")
        dotted_fields: list[str] = []
        for rule in sp.access.scopes:
            cond = rule.condition
            via = getattr(cond, "via_condition", None) if cond is not None else None
            if via is None:
                continue
            for b in via.bindings:
                if "." in b.junction_field:
                    dotted_fields.append(b.junction_field)
        assert "teaching_group.teacher.user" in dotted_fields, dotted_fields

    def test_scope_predicate_carries_dotted_path(self, tmp_path: Path) -> None:
        """The linker compiles the via into an ExistsCheck that preserves the path."""
        spec = _appspec(_TEACHER_DSL, tmp_path)
        sp = next(e for e in spec.domain.entities if e.name == "StudentProfile")
        dotted_fields: list[str] = []
        for rule in sp.access.scopes:
            pred = rule.predicate
            bindings = getattr(pred, "bindings", None) if pred is not None else None
            if not bindings:
                continue
            for b in bindings:
                if "." in b.junction_field:
                    dotted_fields.append(b.junction_field)
        assert "teaching_group.teacher.user" in dotted_fields, dotted_fields


class TestCompilerExpandsDottedPath:
    def test_emits_nested_in_subquery(self) -> None:
        """The compiled SQL for the dotted binding walks junction FK hops."""
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import ExistsBinding, ExistsCheck
        from dazzle_back.runtime.predicate_compiler import compile_predicate

        # FK graph: ClassEnrolment.teaching_group → TeachingGroup,
        # TeachingGroup.teacher → StaffMember, StaffMember.user → User
        fk_graph = FKGraph()
        fk_graph._edges["ClassEnrolment"] = {
            "student_profile": "StudentProfile",
            "teaching_group": "TeachingGroup",
        }
        fk_graph._edges["TeachingGroup"] = {"teacher": "StaffMember"}
        fk_graph._edges["StaffMember"] = {"user": "User"}

        predicate = ExistsCheck(
            target_entity="ClassEnrolment",
            bindings=[
                ExistsBinding(junction_field="student_profile", target="id", operator="="),
                ExistsBinding(
                    junction_field="teaching_group.teacher.user",
                    target="current_user",
                    operator="=",
                ),
            ],
            negated=False,
        )

        sql, params = compile_predicate(predicate, "StudentProfile", fk_graph)

        # Outer shape: EXISTS (SELECT 1 FROM "ClassEnrolment" WHERE ...)
        assert sql.startswith("EXISTS (SELECT 1 FROM")
        # The dotted binding expanded into a nested IN chain on the root FK
        assert '"teaching_group" IN (' in sql
        # Walks through TeachingGroup.teacher
        assert 'FROM "TeachingGroup"' in sql
        assert '"teacher" IN (' in sql
        # Then StaffMember.user = current_user
        assert 'FROM "StaffMember"' in sql
        assert '"user" =' in sql
        # One param bound: current_user
        assert len(params) == 1

    def test_flat_via_binding_still_works(self) -> None:
        """Non-dotted bindings keep the flat single-column shape."""
        from dazzle.core.ir.fk_graph import FKGraph
        from dazzle.core.ir.predicates import ExistsBinding, ExistsCheck
        from dazzle_back.runtime.predicate_compiler import compile_predicate

        fk_graph = FKGraph()
        predicate = ExistsCheck(
            target_entity="Membership",
            bindings=[
                ExistsBinding(junction_field="user", target="current_user", operator="="),
                ExistsBinding(junction_field="resource", target="id", operator="="),
            ],
            negated=False,
        )

        sql, _ = compile_predicate(predicate, "Resource", fk_graph)

        assert '"user" =' in sql
        # No nested IN chain for the flat path
        assert '"user" IN (' not in sql


class TestValidatorChecksDottedVia:
    def test_valid_dotted_via_produces_no_error(self, tmp_path: Path) -> None:
        spec = _appspec(_TEACHER_DSL, tmp_path)
        errors, _warnings, _rel = lint_appspec(spec)
        # There may be unrelated warnings, but no error about the via binding.
        assert not any("via binding" in e for e in errors), errors

    def test_unknown_dotted_segment_is_error(self, tmp_path: Path) -> None:
        """A path whose hop doesn't exist in the FK graph fails validate."""
        bad_dsl = """module t
app T "T"

persona teacher "Teacher":
  description: "T"

entity User "User":
  id: uuid pk

entity StaffMember "S":
  id: uuid pk
  user: ref User

entity TeachingGroup "TG":
  id: uuid pk
  teacher: ref StaffMember

entity StudentProfile "SP":
  id: uuid pk
  scope:
    read: via ClassEnrolment(student_profile = id, teaching_group.nonexistent_fk.user = current_user)
      for: teacher

entity ClassEnrolment "CE":
  id: uuid pk
  student_profile: ref StudentProfile
  teaching_group: ref TeachingGroup

surface student_list "Students":
  uses entity StudentProfile
  mode: list
"""
        spec = _appspec(bad_dsl, tmp_path)
        errors, _warnings, _rel = lint_appspec(spec)
        assert any(
            "teaching_group.nonexistent_fk.user" in e or "nonexistent_fk" in e for e in errors
        ), errors
