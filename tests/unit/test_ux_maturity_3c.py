"""#1558: criterion 3c (state-gated affordance) declared at L4 with a real probe."""

from dazzle.qa import ux_maturity as m


def _crit(cid):  # type: ignore[no-untyped-def]
    return next(c for c in m.CRITERIA if c.id == cid)


def test_3c_declared_l4():
    assert _crit("3c").declared == 4


def test_3c_probe_passes():
    c = _crit("3c")
    result = c.probe()
    assert result.ok, result.note
