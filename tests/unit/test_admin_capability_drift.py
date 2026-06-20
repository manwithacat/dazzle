"""Drift gate: every framework admin capability is consumed by a surface, and AdminPolicy holds its
default-deny / fail-closed invariants. Catches an orphaned capability or a regressed default."""

from pathlib import Path

from dazzle.http.runtime.auth.admin_policy import CAPABILITIES, AdminPolicy

_AUTH_DIR = Path(__file__).resolve().parents[2] / "src/dazzle/http/runtime/auth"


def test_every_capability_is_consumed_by_a_route_or_guard():
    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in _AUTH_DIR.glob("*.py") if p.name != "admin_policy.py"
    )
    for cap in CAPABILITIES:
        assert f'"{cap}"' in sources or f"'{cap}'" in sources, (
            f"capability {cap!r} is defined but no surface gates on it — orphan capability"
        )


def test_default_deny_and_fallback_invariants():
    p = AdminPolicy.from_config(org_admin_roles=["org_admin"], admin_capabilities={})
    assert all(p.may(c, ["org_admin"]) for c in CAPABILITIES)  # fallback to org_admin_roles
    assert not any(p.may(c, ["nobody"]) for c in CAPABILITIES)  # default-deny
    empty = AdminPolicy.from_config(org_admin_roles=[], admin_capabilities={})
    assert not any(empty.may(c, ["anyone"]) for c in CAPABILITIES)  # fail-closed
