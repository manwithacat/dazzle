"""Unit tests for scripts/improve_github_inbox.py classification helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "improve_github_inbox.py"

pytestmark = pytest.mark.gate


def _load():
    spec = importlib.util.spec_from_file_location("improve_github_inbox", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def inbox():
    return _load()


def test_consumer_bug_external_author(inbox):
    assert inbox.is_consumer_issue(
        login="acme-dev",
        owner_login="manwithacat",
        labels=["needs-triage"],
        title="Crash on dazzle serve with empty workspace",
    )


def test_owner_not_consumer(inbox):
    assert not inbox.is_consumer_issue(
        login="manwithacat",
        owner_login="manwithacat",
        labels=["bug"],
        title="Crash on serve",
    )


def test_dependabot_detect(inbox):
    assert inbox.is_dependabot("app/dependabot")
    assert inbox.is_dependabot("dependabot[bot]")
    assert not inbox.is_dependabot("some-human")


def test_summarize_checks_ready(inbox):
    rollup = [
        {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "type-check", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "claude-review", "status": "COMPLETED", "conclusion": "SKIPPED"},
    ]
    s = inbox.summarize_checks(rollup)
    assert s["ready"] is True
    assert s["failed"] == 0


def test_summarize_checks_failed(inbox):
    rollup = [
        {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {
            "name": "INTERACTION_WALK",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
        },
    ]
    s = inbox.summarize_checks(rollup)
    assert s["ready"] is False
    assert s["failed"] == 1
    assert "INTERACTION_WALK" in s["failed_names"]


def test_classify_dependabot_ready_primary(inbox):
    issues = []
    prs = [
        {
            "number": 1588,
            "title": "chore(ci): bump actions/setup-python",
            "author": {"login": "app/dependabot", "is_bot": True},
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "statusCheckRollup": [
                {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
                {"name": "Python Tests (py3.12)", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
            "headRefName": "dependabot/github_actions/actions/setup-python-6",
            "url": "https://github.com/manwithacat/dazzle/pull/1588",
        }
    ]
    out = inbox.classify(issues=issues, prs=prs, owner_login="manwithacat")
    assert out["heat"] == "dependabot_merge"
    assert out["counts"]["dependabot_ready"] == 1
    assert out["primary"]["kind"] == "dependabot_merge"
    assert out["primary"]["pr"] == 1588


def test_classify_consumer_bug_primary(inbox):
    issues = [
        {
            "number": 99,
            "title": "Regression: export fails with TypeError",
            "author": {"login": "downstream-user"},
            "labels": [{"name": "needs-triage"}],
            "url": "https://example/99",
        }
    ]
    out = inbox.classify(issues=issues, prs=[], owner_login="manwithacat")
    assert out["heat"] == "consumer_bug"
    assert out["counts"]["consumer_bugs"] >= 1
    assert out["primary"]["kind"] == "consumer_issue"
    assert out["primary"]["issue"] == 99


def test_classify_owner_bug_primary_and_heat(inbox):
    """Owner/pilot bugs must heat the inbox so /improve claims them (not idle)."""
    issues = [
        {
            "number": 1590,
            "title": "HM steps section: dz-step-connector inside flex item crushes columns",
            "author": {"login": "manwithacat"},
            "labels": [
                {"name": "bug"},
                {"name": "framework"},
                {"name": "pilot:cyfuture"},
                {"name": "cyfuture"},
            ],
            "url": "https://github.com/manwithacat/dazzle/issues/1590",
        },
        {
            "number": 1591,
            "title": "HM site nav: dz-nav-items no wrap/hamburger causes mobile overflow",
            "author": {"login": "manwithacat"},
            "labels": [
                {"name": "bug"},
                {"name": "pilot:cyfuture"},
            ],
            "url": "https://github.com/manwithacat/dazzle/issues/1591",
        },
    ]
    out = inbox.classify(issues=issues, prs=[], owner_login="manwithacat")
    assert out["heat"] == "owner_bug"
    assert out["counts"]["owner_bugs"] == 2
    assert out["primary"] is not None
    assert out["primary"]["kind"] == "owner_issue"
    assert out["primary"]["issue"] == 1590
    assert out["primary"]["playbook"] == "improve/strategies/consumer_issues.md"
    kinds = {r["kind"] for r in out["recommended"]}
    assert "owner_issue" in kinds
    assert len([r for r in out["recommended"] if r["kind"] == "owner_issue"]) == 2


def test_classify_consumer_bug_outranks_owner_bug(inbox):
    issues = [
        {
            "number": 10,
            "title": "Owner-only regression",
            "author": {"login": "manwithacat"},
            "labels": [{"name": "bug"}],
            "url": "https://example/10",
        },
        {
            "number": 11,
            "title": "Crash on serve from customer",
            "author": {"login": "acme-dev"},
            "labels": [{"name": "bug"}],
            "url": "https://example/11",
        },
    ]
    out = inbox.classify(issues=issues, prs=[], owner_login="manwithacat")
    assert out["heat"] == "consumer_bug"
    assert out["primary"]["kind"] == "consumer_issue"
    assert out["primary"]["issue"] == 11
