"""Tests for PA-LLM-10 — magic-string-typing (ID-shaped parameters)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_magic_string_id,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: ID-shaped param names + bare str annotation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "expected_count", "expected_snippet"),
    [
        pytest.param(
            "def f(user_id: str) -> User: ...\n",
            1,
            "user_id: str",
            id="user-id-str-param",
        ),
        pytest.param(
            "def f(tenant_uuid: str) -> None: ...\n",
            1,
            None,
            id="tenant-uuid-str-param",
        ),
        pytest.param(
            "def f(id: str) -> None: ...\n",
            1,
            None,
            id="bare-id-param",
        ),
        pytest.param(
            # `api_key: str` fires (in-scope; noisier but documented).
            "def f(api_key: str) -> None: ...\n",
            1,
            None,
            id="key-suffix",
        ),
        pytest.param(
            # `auth_token: str` fires (in-scope; noisier but documented).
            "def f(auth_token: str) -> None: ...\n",
            1,
            None,
            id="token-suffix",
        ),
        pytest.param(
            # `str | None` annotation fires.
            "def f(user_id: str | None) -> None: ...\n",
            1,
            None,
            id="str-pipe-none",
        ),
        pytest.param(
            # `Optional[str]` annotation fires.
            "from typing import Optional\ndef f(user_id: Optional[str]) -> None: ...\n",
            1,
            None,
            id="optional-str",
        ),
        pytest.param(
            # `self` is skipped; the ID-shaped method param fires.
            "class C:\n    def m(self, user_id: str) -> None: ...\n",
            1,
            None,
            id="method-id-param",
        ),
        pytest.param(
            "async def fetch(user_id: str) -> None: ...\n",
            1,
            None,
            id="async-fn-id-param",
        ),
        pytest.param(
            # Each ID-shaped str param produces its own finding.
            "def f(user_id: str, tenant_id: str) -> None: ...\n",
            2,
            None,
            id="multiple-ids-multiple-hits",
        ),
    ],
)
def test_id_shaped_str_param_fires(
    src: str, expected_count: int, expected_snippet: str | None
) -> None:
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == expected_count
    if expected_snippet is not None:
        assert hits[0].snippet == expected_snippet


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src",
    [
        pytest.param(
            # `user_id: UserId` (branded) does not fire.
            "from typing import NewType\n"
            "UserId = NewType('UserId', str)\n"
            "def f(user_id: UserId) -> None: ...\n",
            id="branded-newtype",
        ),
        pytest.param(
            # Integer IDs are out of scope (separate detector if ever).
            "def f(user_id: int) -> None: ...\n",
            id="int-annotation",
        ),
        pytest.param(
            # A `str` param with a name that doesn't match the ID regex doesn't fire.
            "def f(name: str, description: str) -> None: ...\n",
            id="non-id-param",
        ),
        pytest.param(
            # `self` is excluded even though it's never str-typed (defensive).
            "class C:\n    def m(self) -> None: ...\n",
            id="self-param",
        ),
        pytest.param(
            # Synthesized __init__ on @dataclass-decorated classes does not fire.
            "from dataclasses import dataclass\n@dataclass\nclass User:\n    user_id: str\n",
            id="dataclass-init",
        ),
        pytest.param(
            # @dataclass(frozen=True, slots=True) is also skipped.
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class User:\n"
            "    user_id: str\n",
            id="frozen-dataclass",
        ),
        pytest.param(
            # Untyped parameter is out of scope (mypy catches separately).
            "def f(user_id) -> None: ...\n",
            id="no-annotation",
        ),
    ],
)
def test_false_positive_guard_no_fire(src: str) -> None:
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
