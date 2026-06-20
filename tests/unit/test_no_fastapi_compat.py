"""Guard: the FastAPI optional-import shim must stay deleted.

FastAPI is a required core dependency (pyproject ``dependencies``), so the
``_fastapi_compat`` shim + ``FASTAPI_AVAILABLE`` pattern are dead ceremony.
Banning them keeps the clean break from regressing (ADR-0003).
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "dazzle"
TESTS = ROOT / "tests"
SELF = pathlib.Path(__file__).resolve()


def _py_files() -> list[pathlib.Path]:
    # Scan both src/ and tests/ — the dead flag must not survive anywhere.
    # Exclude this guard file itself (it names the banned tokens on purpose).
    return [
        p
        for root in (SRC, TESTS)
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and p.resolve() != SELF
    ]


def test_no_fastapi_compat_module() -> None:
    shim = SRC / "http" / "runtime" / "_fastapi_compat.py"
    assert not shim.exists(), "delete _fastapi_compat.py — FastAPI is a required core dep"


def test_no_fastapi_compat_imports() -> None:
    offenders = [str(p) for p in _py_files() if "_fastapi_compat" in p.read_text()]
    assert not offenders, f"import fastapi directly, not via the shim: {offenders}"


def test_no_fastapi_available_flag() -> None:
    offenders = [str(p) for p in _py_files() if "FASTAPI_AVAILABLE" in p.read_text()]
    assert not offenders, f"remove dead FASTAPI_AVAILABLE guards: {offenders}"
