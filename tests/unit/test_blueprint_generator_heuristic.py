"""Tests for ``_strategy_value_obviously_wrong`` — #821.

Blueprint authoring drift regularly produces strategy/field-intent
mismatches. The heuristic guard drops obviously-bad values so rows
land in the DB with the offending field NULL rather than crashing
the seed on a type-cast failure.
"""

from __future__ import annotations

from dazzle.core.ir.demo_blueprint import FieldPattern, FieldStrategy
from dazzle.demo_data.blueprint_generator import _strategy_value_obviously_wrong


def _pat(field_name: str, strategy: FieldStrategy) -> FieldPattern:
    return FieldPattern(field_name=field_name, strategy=strategy)


class TestStrategyValueWrong:
    """Catches the common blueprint authoring-drift patterns."""

    def test_date_relative_on_date_field_is_ok(self) -> None:
        p = _pat("created_at", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is False

    def test_date_relative_on_ref_field_is_wrong(self) -> None:
        p = _pat("created_by", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is True

    def test_date_relative_on_numeric_field_is_wrong(self) -> None:
        p = _pat("error_rate", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is True

    def test_date_relative_on_url_field_is_wrong(self) -> None:
        p = _pat("avatar_url", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is True

    def test_lorem_on_ref_field_is_wrong(self) -> None:
        """E.g. assigned_to (ref User) populated by free_text_lorem."""
        p = _pat("assigned_to", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "Aut fugit.") is True

    def test_uuid_on_ref_field_is_ok(self) -> None:
        p = _pat("assigned_to", FieldStrategy.FOREIGN_KEY)
        assert _strategy_value_obviously_wrong(p, "550e8400-e29b-41d4-a716-446655440000") is False

    def test_lorem_on_text_field_is_ok(self) -> None:
        p = _pat("description", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "Some description text") is False

    def test_non_date_string_on_date_field_is_ok(self) -> None:
        """Only the YYYY-MM-DD shape triggers date-mismatch; other
        strings on date-looking fields are not rejected by this
        heuristic."""
        p = _pat("deadline", FieldStrategy.STATIC_LIST)
        assert _strategy_value_obviously_wrong(p, "later") is False

    def test_none_value_not_flagged(self) -> None:
        p = _pat("created_by", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, None) is False

    def test_created_by_detected_as_ref_name(self) -> None:
        p = _pat("created_by", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "lorem") is True

    def test_foreign_id_suffix_detected_as_ref(self) -> None:
        p = _pat("system_id", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "lorem") is True


class TestEmailFromNameFallback:
    """Regression guard for today's tool-sweep finding. The
    ``email_from_name`` generator previously fell back to the literal
    string ``"user"`` when ``source_field`` didn't resolve, producing
    the same ``user@example.test`` for every row and crashing seeds
    on the unique-email constraint. Every blueprint auto-proposed by
    ``dazzle.mcp.server.handlers.demo_data`` used
    ``source_field: 'full_name'`` but no auto-proposed entity had a
    ``full_name`` field — so every seed silently produced collisions."""

    def _make_generator(self):
        from dazzle.core.ir.demo_blueprint import DemoDataBlueprint
        from dazzle.demo_data.blueprint_generator import BlueprintDataGenerator

        # Minimal blueprint — field-level generation is blueprint-agnostic
        # for these strategies; the constructor just needs something valid.
        return BlueprintDataGenerator(
            blueprint=DemoDataBlueprint(
                project_id="test",
                domain_description="test",
                entities=[],
            )
        )

    def test_email_from_name_falls_back_to_name_when_source_field_missing(self) -> None:
        """When ``source_field`` (say 'full_name') doesn't resolve,
        the generator MUST try 'name' as the next fallback before
        giving up. Prior behaviour: silent 'user' default."""
        gen = self._make_generator()
        pattern = FieldPattern(
            field_name="email",
            strategy=FieldStrategy.EMAIL_FROM_NAME,
            params={"source_field": "full_name", "domains": ["example.test"]},
        )
        context = {"name": "Jane Doe"}  # no `full_name`
        result = gen.generate_field_value(pattern, context)
        assert result.startswith("jane.doe."), f"expected name fallback, got: {result}"
        assert result.endswith("@example.test")

    def test_email_from_name_falls_back_to_first_last_concat(self) -> None:
        """Contact-entity shape: source_field=first_name is fine, but
        when source_field isn't resolvable the generator should still
        concatenate first_name+last_name rather than collapse to
        'user'."""
        gen = self._make_generator()
        pattern = FieldPattern(
            field_name="email",
            strategy=FieldStrategy.EMAIL_FROM_NAME,
            params={"source_field": "nonexistent", "domains": ["example.test"]},
        )
        context = {"first_name": "Priya", "last_name": "Patel"}
        result = gen.generate_field_value(pattern, context)
        assert result.startswith("priya.patel."), f"expected concat fallback, got: {result}"

    def test_email_from_name_uniquifies_with_random_suffix(self) -> None:
        """Even when every row has the same name (faker pool
        exhaustion at row_count=20 is common), every row must produce
        a distinct email — the rare collision mode that used to crash
        seeds at the 10th or 11th row."""
        gen = self._make_generator()
        pattern = FieldPattern(
            field_name="email",
            strategy=FieldStrategy.EMAIL_FROM_NAME,
            params={"source_field": "name", "domains": ["example.test"]},
        )
        context = {"name": "Same Name"}  # same every time
        emails = {gen.generate_field_value(pattern, context) for _ in range(50)}
        # With 9000-value suffix space, 50 trials essentially never
        # collide. The assertion is soft — >= 45 unique emails out
        # of 50 would still be far better than the old behaviour
        # (1 unique out of 50).
        assert len(emails) >= 45, f"expected near-unique emails, got {len(emails)} unique"

    def test_username_from_name_also_uniquifies(self) -> None:
        """Same fallback + uniquify pattern on USERNAME_FROM_NAME."""
        gen = self._make_generator()
        pattern = FieldPattern(
            field_name="username",
            strategy=FieldStrategy.USERNAME_FROM_NAME,
            params={"source_field": "name"},
        )
        context = {"name": "Fixed Name"}
        usernames = {gen.generate_field_value(pattern, context) for _ in range(50)}
        assert len(usernames) >= 45

    def test_email_from_name_no_source_at_all_still_produces_email(self) -> None:
        """Fully missing context — no name, no first_name, no last_name.
        Must produce a valid-shape email with a random id rather than
        crashing or returning 'user@example.test' repeatedly."""
        gen = self._make_generator()
        pattern = FieldPattern(
            field_name="email",
            strategy=FieldStrategy.EMAIL_FROM_NAME,
            params={"source_field": "name", "domains": ["example.test"]},
        )
        context: dict = {}
        result = gen.generate_field_value(pattern, context)
        assert "@example.test" in result
        assert "user" in result.lower()


class TestPersonNameFieldNameDispatch:
    """``PERSON_NAME`` strategy must dispatch on ``field_name`` so the
    same strategy can fill ``first_name`` / ``last_name`` / ``name``
    columns with the right shape — fake.first_name() / fake.last_name()
    / fake.name() respectively. Without this, blueprints that mark both
    ``first_name`` and ``last_name`` as ``person_name`` (the default
    inference) get full names in BOTH columns. Caught in cycle 108
    trial of contact_manager: rendered "Martin Smith" / "Albert Clark"
    in adjacent cells of the same row, with the email matching only the
    first-cell name. Tom (the fake business-owner persona) read it as
    misaligned data and rejected the app."""

    def _make_generator(self):
        from dazzle.core.ir.demo_blueprint import DemoDataBlueprint
        from dazzle.demo_data.blueprint_generator import BlueprintDataGenerator

        return BlueprintDataGenerator(
            blueprint=DemoDataBlueprint(project_id="t", domain_description="x", entities=[])
        )

    def test_first_name_field_returns_only_first_name(self) -> None:
        """`fake.first_name()` returns a single token like 'William',
        never a full name like 'William Jennings'."""
        gen = self._make_generator()
        pattern = FieldPattern(field_name="first_name", strategy=FieldStrategy.PERSON_NAME)
        # Sample a few — Faker's first_name() returns ~1k options;
        # 30 draws is enough to surface a multi-word leak if the
        # dispatch regressed.
        for _ in range(30):
            value = gen.generate_field_value(pattern, context={})
            assert isinstance(value, str)
            # First-name draws can include a hyphen or apostrophe but
            # NEVER a space (which is the join between given+family).
            assert " " not in value, f"first_name should be single token; got {value!r}"

    def test_last_name_field_returns_only_last_name(self) -> None:
        gen = self._make_generator()
        pattern = FieldPattern(field_name="last_name", strategy=FieldStrategy.PERSON_NAME)
        for _ in range(30):
            value = gen.generate_field_value(pattern, context={})
            assert isinstance(value, str)
            # en_GB last_name() can return double-barrelled like
            # "Wilson-Newman" — that's hyphenated, not space-separated.
            # A space indicates a multi-token leak from fake.name().
            assert " " not in value, f"last_name should be single token; got {value!r}"

    def test_generic_name_field_returns_full_name(self) -> None:
        """`name` / `full_name` / `fullname` should still get the full
        first+last shape (contains a space)."""
        gen = self._make_generator()
        pattern = FieldPattern(field_name="name", strategy=FieldStrategy.PERSON_NAME)
        # Sample several — at least one should contain a space (full names
        # are 'First Last' or 'Title First Last' in en_GB).
        values = [gen.generate_field_value(pattern, context={}) for _ in range(30)]
        assert any(" " in v for v in values), (
            "generic `name` field should include a space-separated full name in some draws"
        )

    def test_aliases_dispatch_correctly(self) -> None:
        """firstname / given_name / surname / family_name aliases route
        to the right faker method."""
        gen = self._make_generator()
        for alias in ("firstname", "given_name"):
            pattern = FieldPattern(field_name=alias, strategy=FieldStrategy.PERSON_NAME)
            for _ in range(10):
                value = gen.generate_field_value(pattern, context={})
                assert " " not in value, f"{alias} alias should be single token; got {value!r}"
        for alias in ("surname", "family_name"):
            pattern = FieldPattern(field_name=alias, strategy=FieldStrategy.PERSON_NAME)
            for _ in range(10):
                value = gen.generate_field_value(pattern, context={})
                assert " " not in value, f"{alias} alias should be single token; got {value!r}"
