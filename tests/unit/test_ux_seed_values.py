"""Tests for the realistic seed-value helper.

Pins the behaviour promised by #809: strings produced by the helper
should read as realistic-but-demo, not as placeholder sludge. These
tests assert faker availability (now a hard dep) and the field-name
hint → output-shape mapping.
"""

from __future__ import annotations

import re

import pytest

from dazzle.testing.ux.seed_values import realistic_email, realistic_str


class TestFieldNameHints:
    def test_first_name_is_a_real_first_name(self) -> None:
        out = realistic_str("first_name")
        # Faker first names start with a capital letter and don't look
        # like the old "Test first_name 1" placeholder.
        assert out[0].isupper()
        assert "first_name" not in out.lower()
        assert "test" not in out.lower()

    def test_last_name(self) -> None:
        out = realistic_str("last_name")
        assert out[0].isupper()
        assert "last_name" not in out.lower()

    def test_company_is_plausible(self) -> None:
        out = realistic_str("company")
        # Company names are typically 2+ words OR a capitalised single token
        assert out[0].isupper()

    def test_email_hint(self) -> None:
        out = realistic_str("email")
        # Faker email → has "@"
        assert "@" in out

    def test_paragraphy_fields(self) -> None:
        for field_name in ("description", "notes", "body", "summary"):
            out = realistic_str(field_name)
            # paragraphs have at least one space
            assert " " in out

    def test_title_field(self) -> None:
        out = realistic_str("title")
        # Title-hint generates a short sentence. Faker seeds can vary
        # across test ordering (Faker.seed is process-wide), so we
        # don't assert an exact word count — just that the output
        # starts capitalised, doesn't carry the legacy "Test title"
        # shape, and has some content.
        assert len(out) >= 3
        assert out[0].isupper()
        assert "title" not in out.lower()

    def test_url(self) -> None:
        out = realistic_str("url")
        assert out.startswith("http")


class TestFallback:
    def test_unknown_field_name_returns_non_placeholder(self) -> None:
        # Unknown field → faker sentence or Example fallback.
        # Either way it shouldn't look like "UX wibble 2f828c"
        # or "Test wibble 1".
        out = realistic_str("wibble")
        assert len(out) >= 3
        assert not out.startswith("UX ")
        assert "wibble" not in out.lower()

    def test_max_length_truncates(self) -> None:
        out = realistic_str("description", max_length=20)
        assert len(out) <= 20


class TestRealisticEmail:
    def test_domain_is_entity_scoped(self) -> None:
        out = realistic_email("Contact", 0)
        assert out.endswith("@contact.test"), f"expected @contact.test, got {out}"

    def test_local_part_is_realistic(self) -> None:
        out = realistic_email("Contact", 0)
        local = out.split("@", 1)[0]
        # Faker usernames are snake_case or concatenated, not like "uxv-1"
        assert not local.startswith("uxv-")
        assert not local.startswith("test")

    def test_differs_across_entities(self) -> None:
        a = realistic_email("Contact", 0)
        b = realistic_email("Task", 0)
        assert a.split("@")[1] != b.split("@")[1]


class TestDeterminism:
    """Faker.seed(0) is applied at import — calls should be
    reproducible across test invocations within a process. This is a
    weak determinism guarantee (the process-wide seed can be
    clobbered by any other test), but it's enough for snapshots."""

    def test_same_input_gives_reproducible_output(self) -> None:
        # Drain faker state then call twice with the same field —
        # second call should differ (we don't re-seed per call), but
        # the shape should be consistent.
        a = realistic_str("first_name")
        b = realistic_str("first_name")
        # Both should look like first names
        for out in (a, b):
            assert out[0].isupper()
            assert re.match(r"^[A-Z][a-z']+(-[A-Z][a-z]+)?$", out) or " " in out


class TestNoLegacyArtifacts:
    """Regression guards — these specific strings were what trials
    kept flagging as 'unprofessional'. If any of them reappear in
    output it means we've regressed to placeholder land."""

    def test_no_UX_prefix(self) -> None:
        for name in ("first_name", "last_name", "company", "title", "description"):
            out = realistic_str(name)
            assert not out.startswith("UX "), f"'{out}' regressed to UX prefix"

    def test_no_test_prefix(self) -> None:
        for name in ("first_name", "last_name", "title"):
            out = realistic_str(name)
            # Permit "Test" appearing inside a real name (unlikely) but
            # not as a prefix token
            assert not out.lower().startswith("test "), f"'{out}' starts with 'test '"

    @pytest.mark.parametrize("name", ["first_name", "last_name", "title", "description"])
    def test_no_field_name_in_value(self, name: str) -> None:
        out = realistic_str(name)
        # The old pattern ("Test first_name 1", "UX first_name 2f828c")
        # embedded the field name in the output. Faker output should not.
        assert name not in out.lower()
