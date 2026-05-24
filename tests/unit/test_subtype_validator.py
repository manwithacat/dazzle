"""#1217 Phase 3e.vi — validator additions for subtype_of: escape-hatch framing.

Pins:
1. The existing polymorphic-key warning now leads with `W_LOOKS_POLYMORPHIC:`
   and surfaces alternatives in priority order (separate refs first,
   subtype_of: second — see ADR-0026).
2. A new `W_SUBTYPE_OF_OVERREACH` warning fires when a child entity
   declares `subtype_of:` but adds <=1 specific field. That shape is
   almost always cheaper as a flat-entity-with-discriminator.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _validate(dsl: str) -> list[str]:
    """Parse, link, run extended lint. Returns warning strings."""
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules
    from dazzle.core.validator import extended_lint

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(dsl)
        tmp_path = Path(f.name)
    modules = parse_modules([tmp_path])
    appspec = build_appspec(modules, root_module_name="test")
    return extended_lint(appspec)


class TestLooksPolymorphicMessageUpdated:
    def test_warning_uses_code_prefix(self) -> None:
        dsl = """\
module test
app a "A"

entity Comment "Comment":
  id: uuid pk
  body: str(2000) required
  subject_type: enum[post,photo] required
  subject_id: uuid required
"""
        warnings = _validate(dsl)
        msg = next((w for w in warnings if "subject_type" in w), None)
        assert msg is not None, f"no polymorphic warning emitted; got: {warnings}"
        assert "W_LOOKS_POLYMORPHIC" in msg

    def test_warning_suggests_alternatives_in_order(self) -> None:
        dsl = """\
module test
app a "A"

entity Comment "Comment":
  id: uuid pk
  body: str(2000) required
  subject_type: enum[post,photo] required
  subject_id: uuid required
"""
        warnings = _validate(dsl)
        msg = next((w for w in warnings if "subject_type" in w), None)
        assert msg is not None
        # Lead alternative comes BEFORE subtype_of in the message.
        assert msg.index("Separate nullable refs") < msg.index("subtype_of:")


class TestSubtypeOfOverreachWarns:
    def test_one_subtype_specific_field_warns(self) -> None:
        dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
"""
        warnings = _validate(dsl)
        assert any("W_SUBTYPE_OF_OVERREACH" in w for w in warnings), (
            f"expected overreach warning; got: {warnings}"
        )
        msg = next(w for w in warnings if "W_SUBTYPE_OF_OVERREACH" in w)
        assert "Vehicle" in msg

    def test_three_subtype_specific_fields_no_warning(self) -> None:
        dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
  vin: str(17) required
  fuel_type: enum[petrol,diesel] required
"""
        warnings = _validate(dsl)
        assert not any("W_SUBTYPE_OF_OVERREACH" in w for w in warnings), (
            f"unexpected overreach warning for 3-field child; got: "
            f"{[w for w in warnings if 'W_SUBTYPE_OF_OVERREACH' in w]}"
        )

    def test_non_subtype_entity_does_not_warn(self) -> None:
        """Sanity guard — overreach check must only fire on subtype children."""
        dsl = """\
module test
app a "A"

entity Asset "Asset":
  id: uuid pk
  wheels: int required
"""
        warnings = _validate(dsl)
        assert not any("W_SUBTYPE_OF_OVERREACH" in w for w in warnings)
