"""Tests for auth lifecycle test generation (issue #245)."""

from __future__ import annotations

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.personas import PersonaSpec
from dazzle.testing.dsl_test_generator import DSLTestGenerator


def _pk_field() -> FieldSpec:
    return FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


def _str_field(name: str, required: bool = True) -> FieldSpec:
    mods = [FieldModifier.REQUIRED] if required else []
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.STR, max_length=200),
        modifiers=mods,
    )


def _make_appspec(
    personas: list[PersonaSpec] | None = None,
) -> AppSpec:
    entity = EntitySpec(
        name="Task",
        title="Task",
        fields=[_pk_field(), _str_field("title")],
    )
    return AppSpec(
        name="test",
        title="Test",
        domain=DomainSpec(entities=[entity]),
        surfaces=[],
        views=[],
        enums=[],
        processes=[],
        ledgers=[],
        transactions=[],
        workspaces=[],
        experiences=[],
        personas=personas or [],
        stories=[],
        webhooks=[],
        approvals=[],
        slas=[],
        islands=[],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEACHER = PersonaSpec(
    id="teacher",
    label="Teacher",
    goals=["manage classes"],
    default_workspace="teaching",
    default_route="/app/workspaces/teaching",
)

STUDENT = PersonaSpec(
    id="student",
    label="Student",
    goals=["view assignments"],
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuthLifecycleGeneration:
    """Auth lifecycle tests are generated per persona."""

    def test_no_personas_no_auth_tests(self):
        appspec = _make_appspec(personas=[])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        auth_tests = [d for d in suite.designs if "auth" in d.get("tags", [])]
        assert auth_tests == []
        assert suite.coverage.auth_personas_total == 0

    def test_generates_six_tests_per_persona(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        auth_tests = [d for d in suite.designs if "auth" in d.get("tags", [])]
        assert len(auth_tests) == 6

    def test_two_personas_twelve_auth_tests(self):
        appspec = _make_appspec(personas=[TEACHER, STUDENT])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        auth_tests = [d for d in suite.designs if "auth" in d.get("tags", [])]
        assert len(auth_tests) == 12

    def test_login_valid_test_id(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "AUTH_LOGIN_VALID_TEACHER" in ids

    def test_login_invalid_test_id(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "AUTH_LOGIN_INVALID_TEACHER" in ids

    def test_redirect_test_id(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "AUTH_REDIRECT_TEACHER" in ids

    def test_session_valid_test_id(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "AUTH_SESSION_VALID_TEACHER" in ids

    def test_session_expired_test_id(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "AUTH_SESSION_EXPIRED_TEACHER" in ids

    def test_logout_test_id(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        ids = {d["test_id"] for d in suite.designs}
        assert "AUTH_LOGOUT_TEACHER" in ids


class TestAuthRedirectRoute:
    """Auth redirect tests use persona's default_route."""

    def test_redirect_uses_default_route(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        redirect_test = next(d for d in suite.designs if d["test_id"] == "AUTH_REDIRECT_TEACHER")
        # The redirect step should assert the persona's default_route
        redirect_step = next(
            s for s in redirect_test["steps"] if s["action"] == "assert_redirect_url"
        )
        assert redirect_step["data"]["redirect_url"] == "/app/workspaces/teaching"

    def test_redirect_falls_back_to_app(self):
        """Persona without default_route gets /app as redirect target."""
        appspec = _make_appspec(personas=[STUDENT])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        redirect_test = next(d for d in suite.designs if d["test_id"] == "AUTH_REDIRECT_STUDENT")
        redirect_step = next(
            s for s in redirect_test["steps"] if s["action"] == "assert_redirect_url"
        )
        assert redirect_step["data"]["redirect_url"] == "/app"


class TestAuthCoverage:
    """Coverage tracking for auth tests."""

    def test_coverage_tracks_auth_personas(self):
        appspec = _make_appspec(personas=[TEACHER, STUDENT])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        assert suite.coverage.auth_personas_total == 2
        assert suite.coverage.auth_personas_covered == {"teacher", "student"}

    def test_coverage_to_dict_includes_auth(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        cov = suite.coverage.to_dict()
        assert "auth_personas" in cov
        assert cov["auth_personas"] == ["teacher"]
        assert cov["auth_personas_total"] == 1

    def test_no_personas_coverage_zero(self):
        appspec = _make_appspec(personas=[])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        cov = suite.coverage.to_dict()
        assert cov["auth_personas"] == []
        assert cov["auth_personas_total"] == 0


class TestAuthTestTags:
    """Auth tests have correct tags."""

    def test_login_tags(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        login_test = next(d for d in suite.designs if d["test_id"] == "AUTH_LOGIN_VALID_TEACHER")
        assert "auth" in login_test["tags"]
        assert "login" in login_test["tags"]
        assert "generated" in login_test["tags"]
        assert "dsl-derived" in login_test["tags"]

    def test_negative_login_tags(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        test = next(d for d in suite.designs if d["test_id"] == "AUTH_LOGIN_INVALID_TEACHER")
        assert "negative" in test["tags"]

    def test_logout_tags(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        test = next(d for d in suite.designs if d["test_id"] == "AUTH_LOGOUT_TEACHER")
        assert "auth" in test["tags"]
        assert "logout" in test["tags"]

    def test_all_auth_tests_have_persona(self):
        appspec = _make_appspec(personas=[TEACHER])
        gen = DSLTestGenerator(appspec)
        suite = gen.generate_all()
        auth_tests = [d for d in suite.designs if "auth" in d.get("tags", [])]
        for test in auth_tests:
            assert test["persona"] == "teacher"
