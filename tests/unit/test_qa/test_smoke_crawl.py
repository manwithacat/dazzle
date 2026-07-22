"""Unit tests for L2.5 smoke crawl oracles (no Playwright)."""

from __future__ import annotations

from dazzle.qa.smoke_crawl import (
    SmokeHit,
    SmokeIssue,
    evaluate_page_oracles,
    evaluate_structure_oracles,
    hit_to_friction,
)


def test_http_404_is_product_high() -> None:
    issues = evaluate_page_oracles(
        http_status=404,
        title="Page Not Found — Simple Task",
        main_text="Not Found",
    )
    codes = {i.code for i in issues}
    assert "http_error" in codes
    assert any(i.ownership == "product" and i.severity == "high" for i in issues)


def test_403_without_matrix_is_rbac_expected() -> None:
    issues = evaluate_page_oracles(
        http_status=403,
        title="Access Denied",
        main_text="forbidden",
        expected_rbac_deny=None,
    )
    assert issues
    assert all(i.ownership == "rbac_expected" for i in issues if i.code == "http_error")


def test_empty_main_short_chrome_not_flagged() -> None:
    # Nav chrome strip — enough words, not a white screen
    issues = evaluate_page_oracles(
        http_status=200,
        title="App",
        main_text="Lead Team Overview Task Board People",
    )
    assert not any(i.code == "empty_main" and i.ownership == "product" for i in issues)


def test_empty_main_true_white_screen() -> None:
    issues = evaluate_page_oracles(
        http_status=200,
        title="App",
        main_text="  ",
    )
    assert any(i.code == "empty_main" and i.ownership == "product" for i in issues)


def test_structure_duplicate_region() -> None:
    issues = evaluate_structure_oracles(
        duplicate_region_ids=["region-needs_review"],
        nested_refresh_count=0,
    )
    assert issues and issues[0].code == "structure"
    assert issues[0].ownership == "framework"


def test_hit_to_friction_auto_seed_shape() -> None:
    hit = SmokeHit(
        url="/team",
        name="landing",
        kind="landing",
        phase="landing",
        ok=False,
        http_status=404,
        title="Page Not Found",
        issues=[
            SmokeIssue(
                code="http_error",
                detail="HTTP 404",
                ownership="product",
                severity="high",
            )
        ],
        ownership_hint="product",
    )
    row = hit_to_friction(hit)
    assert row is not None
    assert row["category"] == "bug"
    assert row["ownership"] == "product"
    assert row["url"] == "/team"
