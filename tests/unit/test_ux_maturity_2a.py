"""#1558: criterion 2a (answer-first landing) declared at L4 with a live probe."""

from dazzle.qa import ux_maturity as m


def _crit(cid):  # type: ignore[no-untyped-def]
    return next(c for c in m.CRITERIA if c.id == cid)


def test_2a_declared_l4_with_probe():
    c = _crit("2a")
    assert c.declared == 4
    assert c.probe is not None


def test_2a_probe_passes():
    c = _crit("2a")
    result = c.probe()
    assert result.ok, result.note
