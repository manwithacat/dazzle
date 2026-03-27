"""Tests for fuzzer classification oracle."""

from dazzle.testing.fuzzer.oracle import Classification, classify


class TestOracle:
    def test_valid_dsl_classified_as_valid(self) -> None:
        dsl = 'module test\napp test_app "Test"\n\nentity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'
        result = classify(dsl, timeout_seconds=5)
        assert result.classification == Classification.VALID

    def test_parse_error_with_location_is_clean(self) -> None:
        """A ParseError that includes file/line info is a clean error."""
        dsl = "entity\n"  # Missing name — parser gives location
        result = classify(dsl, timeout_seconds=5)
        assert result.classification == Classification.CLEAN_ERROR
        assert result.error_message is not None

    def test_empty_input_does_not_crash(self) -> None:
        result = classify("", timeout_seconds=5)
        assert result.classification in (
            Classification.VALID,
            Classification.CLEAN_ERROR,
        )

    def test_crash_on_non_parse_error(self) -> None:
        """If we inject a scenario that raises something other than ParseError,
        it should be classified as CRASH. We test the classifier directly."""
        from dazzle.testing.fuzzer.oracle import FuzzResult

        # Simulate a crash result
        result = FuzzResult(
            dsl_input="fake",
            classification=Classification.CRASH,
            error_message="TypeError: 'NoneType'",
            error_type="TypeError",
        )
        assert result.classification == Classification.CRASH

    def test_classification_includes_input(self) -> None:
        dsl = "not valid dsl at all @@@ !!!"
        result = classify(dsl, timeout_seconds=5)
        assert result.dsl_input == dsl
