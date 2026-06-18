"""#1413 — declared-but-unregistered custom renderers must be catchable before deploy.

Two layers, both DB-free:
  * the static signpost `dazzle validate` now emits when `[renderers] extra` is
    declared (it can't boot, so it points at the runtime gate), and
  * the runtime gate itself — `dazzle inspect renderers --runtime` — which already
    classifies a declared-but-unregistered renderer as a mismatch and exits 1.
This locks both so the gate can't silently regress.
"""

from __future__ import annotations

import pytest

from dazzle.cli.inspect import (
    InspectEntry,
    InspectResult,
    _cross_reference,
    _emit,
)
from dazzle.cli.project import _renderer_registration_advisory


class TestValidateSignpost:
    def test_no_custom_renderers_no_advisory(self) -> None:
        assert _renderer_registration_advisory([]) is None

    def test_declared_renderers_point_at_runtime_gate(self) -> None:
        msg = _renderer_registration_advisory(["word_cloud", "feedback_detail"])
        assert msg is not None
        # Names surfaced, and the author is pointed at the boot-time gate + issue.
        assert "word_cloud" in msg and "feedback_detail" in msg
        assert "dazzle inspect renderers --runtime" in msg
        assert "#1413" in msg


class TestInspectRuntimeGate:
    def _entries(self) -> list[InspectEntry]:
        # One framework default (always registered) + one manifest-declared.
        return [
            InspectEntry(name="fragment", source="framework", declared=True),
            InspectEntry(name="word_cloud", source="manifest", declared=True),
        ]

    def test_declared_unregistered_renderer_is_a_mismatch(self) -> None:
        result = InspectResult(ext_point="renderers", entries=self._entries())
        # word_cloud declared but NOT in the registered set → mismatch.
        _cross_reference(
            result.entries,
            result,
            registered_names={"fragment"},
            declared_names={"fragment", "word_cloud"},
        )
        assert any("word_cloud" in m and "no runtime handler" in m for m in result.mismatches)

    def test_all_registered_is_clean(self) -> None:
        result = InspectResult(ext_point="renderers", entries=self._entries())
        _cross_reference(
            result.entries,
            result,
            registered_names={"fragment", "word_cloud"},
            declared_names={"fragment", "word_cloud"},
        )
        assert result.mismatches == []

    def test_emit_exits_nonzero_on_mismatch(self) -> None:
        result = InspectResult(ext_point="renderers")
        result.mismatches.append("`word_cloud` is declared in dazzle.toml but no runtime handler")
        with pytest.raises(SystemExit) as exc:
            _emit(result, output_json=False)
        assert exc.value.code == 1

    def test_emit_clean_does_not_exit(self) -> None:
        result = InspectResult(ext_point="renderers")
        _emit(result, output_json=False)  # no mismatches → returns normally
