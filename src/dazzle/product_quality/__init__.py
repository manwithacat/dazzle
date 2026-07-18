"""Felt product / demo quality bars for agents (#1626).

Structural residual (validate/lint/conformance) is necessary but not
sufficient for commercial demo quality. This package scores:

* product maturity (anti-warehouse structure)
* demo fleet bar (nav / seeds / stills floors)
* journey maturity (bound stories)
* **persona homes** (assignment-aware seed residual)
* still empty-hero byte floors

MCP: ``product_quality`` tool. CLI: ``dazzle demo quality``.
"""

from dazzle.product_quality.bar import score_project, score_status_lines

__all__ = ["score_project", "score_status_lines"]
