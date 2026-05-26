"""Tests for PA-LLM-10 — magic-string-typing (ID-shaped parameters)."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_magic_string_id,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: ID-shaped param names + bare str annotation
# ---------------------------------------------------------------------------


def test_user_id_str_param_fires() -> None:
    src = "def f(user_id: str) -> User: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].snippet == "user_id: str"


def test_tenant_uuid_str_param_fires() -> None:
    src = "def f(tenant_uuid: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_bare_id_param_fires() -> None:
    src = "def f(id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_key_suffix_fires() -> None:
    """`api_key: str` fires (in-scope; noisier but documented)."""
    src = "def f(api_key: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_token_suffix_fires() -> None:
    """`auth_token: str` fires (in-scope; noisier but documented)."""
    src = "def f(auth_token: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_str_pipe_none_fires() -> None:
    """`str | None` annotation fires."""
    src = "def f(user_id: str | None) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_optional_str_fires() -> None:
    """`Optional[str]` annotation fires."""
    src = "from typing import Optional\ndef f(user_id: Optional[str]) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_method_id_param_fires() -> None:
    """`self` is skipped; the ID-shaped method param fires."""
    src = "class C:\n    def m(self, user_id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_async_fn_id_param_fires() -> None:
    src = "async def fetch(user_id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_multiple_ids_yield_multiple_hits() -> None:
    """Each ID-shaped str param produces its own finding."""
    src = "def f(user_id: str, tenant_id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 2


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


def test_branded_newtype_no_fire() -> None:
    """`user_id: UserId` (branded) does not fire."""
    src = (
        "from typing import NewType\n"
        "UserId = NewType('UserId', str)\n"
        "def f(user_id: UserId) -> None: ...\n"
    )
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_int_annotation_no_fire() -> None:
    """Integer IDs are out of scope (separate detector if ever)."""
    src = "def f(user_id: int) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_non_id_param_no_fire() -> None:
    """A `str` param with a name that doesn't match the ID regex doesn't fire."""
    src = "def f(name: str, description: str) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_self_param_no_fire() -> None:
    """`self` is excluded even though it's never str-typed (defensive)."""
    src = "class C:\n    def m(self) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_dataclass_init_no_fire() -> None:
    """Synthesized __init__ on @dataclass-decorated classes does not fire."""
    src = "from dataclasses import dataclass\n@dataclass\nclass User:\n    user_id: str\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_frozen_dataclass_no_fire() -> None:
    """@dataclass(frozen=True, slots=True) is also skipped."""
    src = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class User:\n"
        "    user_id: str\n"
    )
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_no_annotation_no_fire() -> None:
    """Untyped parameter is out of scope (mypy catches separately)."""
    src = "def f(user_id) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_suppression_on_def(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-10` on the def line suppresses all params in that signature."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f(user_id: str, tenant_id: str) -> None:  # noqa: PA-LLM-10 - opaque\n    pass\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_magic_string_typing(appspec=None) == []  # type: ignore[arg-type]


def test_noqa_suppression_on_param_line(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-10` on the parameter line (multi-line signature) suppresses."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f(\n"
        "    user_id: str,  # noqa: PA-LLM-10 - opaque\n"
        "    tenant_id: str,\n"
        ") -> None:\n"
        "    pass\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_magic_string_typing(appspec=None)  # type: ignore[arg-type]
    # user_id is suppressed by the param-line noqa; tenant_id still fires.
    assert len(findings) == 1
    assert "tenant_id" in findings[0].title


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "transfers.py").write_text(
        "def transfer(source_id: str, destination_id: str, amount: int) -> None:\n    pass\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_magic_string_typing(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 2
    for f in findings:
        assert f.heuristic_id == "PA-LLM-10"
        assert f.catalogue_entry == "magic-string-typing"
        assert f.remediation is not None
        assert any(
            "docs/counter-priors/magic-string-typing.md" in ref for ref in f.remediation.references
        )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text("def f(user_id: str) -> None: ...\n")
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_magic_string_typing(appspec=None) == []  # type: ignore[arg-type]


def test_skips_pydantic_basemodel_subclass_1275(tmp_path: Path) -> None:
    """#1275: Pydantic `BaseModel` synthesises `__init__` via its
    metaclass, so `_has_dataclass_decorator` doesn't catch it. ID-shaped
    field annotations on the model would otherwise fire PA-LLM-10
    spuriously (the model's own validation is the canonical guard;
    the agent should treat these the same as @dataclass).

    Covers three import shapes the helper recognises:
      - `from pydantic import BaseModel` → `class Foo(BaseModel):`
      - `import pydantic` → `class Foo(pydantic.BaseModel):`
      - aliased import → `class Foo(Pdt.BaseModel):`
    """
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "models.py").write_text(
        "from pydantic import BaseModel\n"
        "import pydantic\n"
        "import pydantic as pdt\n"
        "\n"
        "class User(BaseModel):\n"
        "    user_id: str\n"
        "    tenant_id: str\n"
        "\n"
        "class Tenant(pydantic.BaseModel):\n"
        "    tenant_id: str\n"
        "    parent_id: str\n"
        "\n"
        "class Aliased(pdt.BaseModel):\n"
        "    record_id: str\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_magic_string_typing(appspec=None)  # type: ignore[arg-type]
    assert findings == [], (
        f"PA-LLM-10 must skip Pydantic BaseModel subclasses (#1275); got {findings}"
    )


def test_basemodel_subclass_still_audits_module_level_fns_1275(tmp_path: Path) -> None:
    """The skip is scoped to the class body — module-level functions in
    the same file still get audited normally. This pins that the
    line-range gate doesn't accidentally swallow the whole file."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "models.py").write_text(
        "from pydantic import BaseModel\n"
        "\n"
        "class User(BaseModel):\n"
        "    user_id: str\n"
        "\n"
        "def get_user(user_id: str) -> None:\n"  # NOT inside the model — should fire
        "    pass\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_magic_string_typing(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1, (
        f"Module-level `get_user(user_id: str)` should still fire PA-LLM-10; "
        f"the BaseModel skip only covers the class body. Got: {findings}"
    )
