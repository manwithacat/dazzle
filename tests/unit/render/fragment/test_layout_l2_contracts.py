"""Layouts L2 — Stack/Row emit the HM Layout Hyperpart contracts.

The legacy modifier-class idiom (`dz-stack--gap-md`, `dz-row--gap-md
dz-row--align-center`) is replaced by the L1 attribute contracts
(`data-dz-gap` on `dz-stack`; the `dz-cluster` Hyperpart for rows).
Split/Grid keep their legacy emission: both have ZERO production call
sites (verified 2026-07-06), so they wait for a consumer to motivate a
contract choice rather than guessing one now.
"""

from __future__ import annotations

from dazzle.render.fragment import FragmentRenderer, Row, Stack, Text


def _render(frag: object) -> str:
    return FragmentRenderer().render(frag)  # type: ignore[arg-type]


class TestStackContract:
    def test_stack_emits_data_dz_gap(self) -> None:
        html = _render(Stack(children=(Text("a"), Text("b")), gap="sm"))
        assert '<div class="dz-stack" data-dz-gap="sm">' in html
        assert "dz-stack--gap" not in html

    def test_stack_default_gap_is_explicit(self) -> None:
        html = _render(Stack(children=(Text("a"),)))
        assert 'data-dz-gap="md"' in html


class TestRowContract:
    def test_row_emits_the_cluster_hyperpart(self) -> None:
        html = _render(Row(children=(Text("a"), Text("b")), gap="md", align="center"))
        # align=center is the cluster's default — no attribute emitted.
        assert '<div class="dz-cluster" data-dz-gap="md">' in html
        assert "dz-row" not in html

    def test_row_start_align_emits_attribute_since_cluster_default_is_center(self) -> None:
        html = _render(Row(children=(Text("a"),), align="start"))
        assert 'data-dz-align="start"' in html
