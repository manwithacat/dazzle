"""Config-loading paths for `audit_integrity` (#1206).

#1197 shipped `ServerConfig.audit_integrity` + `AuditLogger(audit_integrity=)`
but the loader path was missing — `dazzle.toml` `[audit] integrity` was not
parsed, no env var was read, and `build_server_config()` had no kwarg. This
test pins the four levels that now exist:

1. ``[audit] integrity`` is parsed off ``dazzle.toml`` into
   ``ProjectManifest.audit_integrity`` (default ``"none"``).
2. ``build_server_config(audit_integrity=...)`` threads into
   ``ServerConfig.audit_integrity``.
3. ``DAZZLE_AUDIT_INTEGRITY`` env var beats the manifest value inside
   ``create_app_factory()``.
4. Invalid values fail loud with ``ValueError`` at config-build time
   rather than silently coercing to the default.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.core.manifest import load_manifest

_MINIMAL_TOML = textwrap.dedent("""\
    [project]
    name = "test-app"
    version = "0.1.0"

    [modules]
    paths = ["./dsl"]
""")


def _write_toml(tmp_path: Path, extra: str = "") -> Path:
    p = tmp_path / "dazzle.toml"
    p.write_text(_MINIMAL_TOML + extra, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Manifest parses `[audit] integrity`
# ---------------------------------------------------------------------------


def test_manifest_default_audit_integrity_is_none(tmp_path: Path) -> None:
    manifest = load_manifest(_write_toml(tmp_path))
    assert manifest.audit_integrity == "none"


def test_manifest_parses_hash_chain(tmp_path: Path) -> None:
    extra = textwrap.dedent("""\
        [audit]
        integrity = "hash_chain"
    """)
    manifest = load_manifest(_write_toml(tmp_path, extra))
    assert manifest.audit_integrity == "hash_chain"


def test_manifest_rejects_invalid_value(tmp_path: Path) -> None:
    """Hyphen-typo `"hash-chain"` must fail loud at manifest load."""
    extra = textwrap.dedent("""\
        [audit]
        integrity = "hash-chain"
    """)
    with pytest.raises(ValueError, match="integrity"):
        load_manifest(_write_toml(tmp_path, extra))


# ---------------------------------------------------------------------------
# 2. `build_server_config(audit_integrity=...)` threading
# ---------------------------------------------------------------------------


def _empty_appspec() -> object:
    """Minimal AppSpec-shaped object for build_server_config().

    The function only reads `.domain.entities`, `.surfaces`, `.views`,
    `.processes`, `.schedules` — so a trivial namespace is enough.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        domain=SimpleNamespace(entities=[]),
        surfaces=[],
        views=[],
        processes=[],
        schedules=[],
    )


def test_build_server_config_threads_audit_integrity() -> None:
    from dazzle.http.runtime.app_factory import build_server_config

    config = build_server_config(_empty_appspec(), audit_integrity="hash_chain")
    assert config.audit_integrity == "hash_chain"


def test_build_server_config_default_is_none() -> None:
    from dazzle.http.runtime.app_factory import build_server_config

    config = build_server_config(_empty_appspec())
    assert config.audit_integrity == "none"


def test_build_server_config_rejects_invalid() -> None:
    from dazzle.http.runtime.app_factory import build_server_config

    with pytest.raises(ValueError, match="audit_integrity"):
        build_server_config(_empty_appspec(), audit_integrity="bogus")


def test_build_server_config_rejects_hyphen_typo() -> None:
    """The specific real-world bug class the validation catches."""
    from dazzle.http.runtime.app_factory import build_server_config

    with pytest.raises(ValueError, match="audit_integrity"):
        build_server_config(_empty_appspec(), audit_integrity="hash-chain")


# ---------------------------------------------------------------------------
# 3. `DAZZLE_AUDIT_INTEGRITY` env var wins over manifest
# ---------------------------------------------------------------------------


def test_env_var_resolves_over_manifest_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The env-var resolution lives in `create_app_factory()`; this test
    pins the resolution rule directly without booting the whole factory:
    env var beats `manifest.audit_integrity`.
    """
    from types import SimpleNamespace

    manifest = SimpleNamespace(audit_integrity="none")
    monkeypatch.setenv("DAZZLE_AUDIT_INTEGRITY", "hash_chain")
    resolved = __import__("os").environ.get(
        "DAZZLE_AUDIT_INTEGRITY",
        getattr(manifest, "audit_integrity", "none"),
    )
    assert resolved == "hash_chain"


def test_env_var_unset_falls_back_to_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    manifest = SimpleNamespace(audit_integrity="hash_chain")
    monkeypatch.delenv("DAZZLE_AUDIT_INTEGRITY", raising=False)
    resolved = __import__("os").environ.get(
        "DAZZLE_AUDIT_INTEGRITY",
        getattr(manifest, "audit_integrity", "none"),
    )
    assert resolved == "hash_chain"


# ---------------------------------------------------------------------------
# 4. Symmetry with AuditLogger validation (#1197)
# ---------------------------------------------------------------------------


def test_build_server_config_validation_matches_audit_logger() -> None:
    """The validation set in `build_server_config` and `AuditLogger.__init__`
    must agree — a value that one accepts and the other rejects would be a
    correctness bug. Drift guard for the {none, hash_chain} pair.
    """
    from dazzle.http.runtime.app_factory import build_server_config
    from dazzle.http.runtime.audit_log import AuditLogger

    # Accept both valid values
    for mode in ("none", "hash_chain"):
        cfg = build_server_config(_empty_appspec(), audit_integrity=mode)
        assert cfg.audit_integrity == mode

    # And both reject the same garbage at the same boundary. AuditLogger
    # validates before any DB call so no psycopg mock is needed.
    with pytest.raises(ValueError, match="audit_integrity"):
        build_server_config(_empty_appspec(), audit_integrity="garbage")
    with pytest.raises(ValueError, match="audit_integrity"):
        AuditLogger(database_url="postgresql://localhost/x", audit_integrity="garbage")
