"""The shared spec-loader validation accumulator (#1747).

Three loaders each defined their own `*ValidationResult` with byte-identical
`__init__` / `add_error` / `add_warning` / `is_valid`. Only one of the three
documented the one semantic question a reader would have — *does a warning
invalidate the result?* — and only two had a `__repr__`. Consolidating them is
what makes that answer single-sourced; these tests are what keeps it answered.
"""

from __future__ import annotations

from typing import ClassVar

from dazzle.core.sitespec_loader import SiteSpecValidationResult
from dazzle.core.themespec_loader import ThemeSpecValidationResult
from dazzle.core.validation_result import ValidationResult
from dazzle.pitch.loader import PitchSpecValidationResult

LOADERS = (SiteSpecValidationResult, ThemeSpecValidationResult, PitchSpecValidationResult)


class TestAccumulator:
    def test_a_fresh_result_is_valid_and_empty(self) -> None:
        result = ValidationResult()
        assert result.errors == []
        assert result.warnings == []
        assert result.is_valid is True

    def test_one_error_invalidates(self) -> None:
        result = ValidationResult()
        result.add_error("bad field")
        assert result.is_valid is False
        assert result.errors == ["bad field"]

    def test_warnings_alone_never_invalidate(self) -> None:
        """The question only `sitespec_loader` used to answer.

        A loader that cannot resolve an *optional* field should warn and carry
        on. If this ever flips, it is a behaviour change across all three
        loaders at once — which is the reason to have one answer, and the reason
        to have a test on it.
        """
        result = ValidationResult()
        result.add_warning("optional field unresolved")
        result.add_warning("and another")
        assert result.is_valid is True
        assert result.warnings == ["optional field unresolved", "and another"]

    def test_order_is_preserved_within_each_channel(self) -> None:
        result = ValidationResult()
        for i in range(3):
            result.add_error(f"e{i}")
            result.add_warning(f"w{i}")
        assert result.errors == ["e0", "e1", "e2"]
        assert result.warnings == ["w0", "w1", "w2"]


class TestRepr:
    def test_repr_names_the_subclass_not_the_base(self) -> None:
        """A base `__repr__` hardcoding one loader's name is the bug this prevents.

        The two `core/` loaders each carried their own `__repr__`; the shared one
        derives the name, so a fourth loader is correct for free.
        """

        class FourthLoaderResult(ValidationResult):
            pass

        assert repr(FourthLoaderResult()).startswith("FourthLoaderResult(")

    def test_repr_counts_channels(self) -> None:
        result = ValidationResult()
        result.add_error("e")
        result.add_warning("w")
        result.add_warning("w2")
        assert repr(result) == "ValidationResult(errors=1, warnings=2)"


class TestLoaderParity:
    """The three loaders must not drift back into independent accumulators."""

    def test_every_loader_derives_from_the_shared_base(self) -> None:
        for cls in LOADERS:
            assert issubclass(cls, ValidationResult), f"{cls.__name__} bypasses ValidationResult"

    def test_every_loader_overrides_nothing_it_should_inherit(self) -> None:
        """No loader should re-implement what the base now owns."""
        owned_by_base: ClassVar[frozenset[str]] = frozenset(
            {"__init__", "add_error", "add_warning", "is_valid", "__repr__"}
        )
        for cls in LOADERS:
            redefined = owned_by_base & set(vars(cls))
            assert not redefined, f"{cls.__name__} re-defines {sorted(redefined)}"

    def test_every_loader_keeps_its_own_identity(self) -> None:
        for cls in LOADERS:
            result = cls()
            assert type(result) is cls
            assert repr(result).startswith(f"{cls.__name__}(")
