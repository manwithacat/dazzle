"""Drift gate for examples/acme_billing committed reference outputs (#1174).

Regenerates the RBAC matrix and compliance audit spec and diffs them against
the committed copies in examples/acme_billing/expected/.  A framework change
that alters either output fails here — regenerate the committed reference and
note the change in CHANGELOG.

Regeneration commands (run from examples/acme_billing/):
  python -m dazzle rbac matrix --format json > expected/rbac-matrix.json
  python -m dazzle compliance compile && \\
    python3 -c "
import json; from pathlib import Path
d = json.loads(Path('.dazzle/compliance/output/iso27001/auditspec.json').read_text())
d.pop('generated_at', None)
d.pop('dsl_source', None)
Path('expected/compliance-auditspec.json').write_text(json.dumps(d, indent=2))
"

Volatile content normalisation
  - compliance-auditspec.json: ``generated_at`` (a UTC timestamp) and
    ``dsl_source`` (a machine-absolute project path — differs between dev
    boxes and CI runners) are stripped before comparison. The committed copy
    is stored without either field. The compile command writes to
    .dazzle/compliance/output/iso27001/auditspec.json; the test reads from
    that path after running the command.
  - rbac-matrix.json: fully deterministic, no normalisation required.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gate

# Anchor paths to the repo root, not pytest's launch directory (#1174).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP = _REPO_ROOT / "examples" / "acme_billing"
_AUDITSPEC_PATH = _APP / ".dazzle" / "compliance" / "output" / "iso27001" / "auditspec.json"

# Fields stripped before comparison — volatile or machine-specific.
_VOLATILE_AUDITSPEC_FIELDS = ("generated_at", "dsl_source")


def _normalise_auditspec(d: dict[str, Any]) -> dict[str, Any]:
    """Drop volatile/machine-specific top-level fields from a parsed auditspec.

    ``generated_at`` is a per-run UTC timestamp; ``dsl_source`` is the
    machine-absolute project path. Both would cause spurious drift failures.
    """
    for field in _VOLATILE_AUDITSPEC_FIELDS:
        d.pop(field, None)
    return d


def test_rbac_matrix_matches_committed_reference() -> None:
    """RBAC matrix must exactly match the committed expected/rbac-matrix.json."""
    committed = json.loads((_APP / "expected" / "rbac-matrix.json").read_text())
    result = subprocess.run(
        ["python", "-m", "dazzle", "rbac", "matrix", "--format", "json"],
        cwd=_APP,
        capture_output=True,
        text=True,
        check=True,
    )
    live = json.loads(result.stdout)
    assert live == committed, (
        "acme_billing RBAC matrix drifted from expected/rbac-matrix.json.\n\n"
        "To accept the drift:\n"
        "  1. cd examples/acme_billing\n"
        "  2. python -m dazzle rbac matrix --format json > expected/rbac-matrix.json\n"
        "  3. Review the diff\n"
        "  4. Add a CHANGELOG entry under Changed\n"
        "  5. Commit the regenerated expected/rbac-matrix.json"
    )


def test_compliance_auditspec_matches_committed_reference() -> None:
    """Compliance auditspec must match committed expected/compliance-auditspec.json.

    ``generated_at`` (timestamp) and ``dsl_source`` (machine-absolute path) are
    stripped from both sides before comparison — see ``_normalise_auditspec``.

    The ``compile`` command writes to .dazzle/compliance/output/iso27001/auditspec.json;
    the test reads from that canonical output path rather than stdout (which mixes
    in Rich console output and cannot be parsed as pure JSON).
    """
    committed = _normalise_auditspec(
        json.loads((_APP / "expected" / "compliance-auditspec.json").read_text())
    )
    subprocess.run(
        ["python", "-m", "dazzle", "compliance", "compile"],
        cwd=_APP,
        capture_output=True,
        text=True,
        check=True,
    )
    live = _normalise_auditspec(json.loads(_AUDITSPEC_PATH.read_text()))
    assert live == committed, (
        "acme_billing compliance auditspec drifted from "
        "expected/compliance-auditspec.json.\n\n"
        "To accept the drift:\n"
        "  1. cd examples/acme_billing\n"
        "  2. python -m dazzle compliance compile\n"
        '  3. python3 -c "import json; from pathlib import Path; '
        "d=json.loads(Path('.dazzle/compliance/output/iso27001/auditspec.json').read_text()); "
        "d.pop('generated_at', None); d.pop('dsl_source', None); "
        "Path('expected/compliance-auditspec.json').write_text(json.dumps(d, indent=2))\"\n"
        "  4. Review the diff\n"
        "  5. Add a CHANGELOG entry under Changed\n"
        "  6. Commit the regenerated expected/compliance-auditspec.json"
    )
