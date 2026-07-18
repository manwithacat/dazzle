"""Installed vs project pin compatibility for agents (#1629 G7).

Single compact structure for status.mcp / doctor / knowledge priors —
do not invent pins from CLI banner folklore alone.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from dazzle._version import get_version
from dazzle.core.manifest import load_manifest

logger = logging.getLogger(__name__)


def _installed_version() -> str:
    try:
        return get_version()
    except Exception:  # noqa: BLE001
        logger.debug("get_version failed", exc_info=True)
        return "unknown"


def _project_pin(project_root: Path | None) -> str | None:
    if project_root is None:
        return None
    toml = project_root / "dazzle.toml"
    if not toml.is_file():
        return None
    try:
        mf = load_manifest(toml)
        pin = getattr(mf, "framework_version", None)
        return str(pin) if pin else None
    except Exception:  # noqa: BLE001
        logger.debug("load framework_version pin failed for %s", project_root, exc_info=True)
        return None


def _pin_compatible(installed: str, pin: str | None) -> bool | None:
    """Whether *installed* satisfies *pin*. None if not evaluable."""
    if not pin or installed in ("unknown", ""):
        return None
    try:
        installed_v = Version(installed.split("+")[0])
        constraint = pin.strip()
        if constraint.startswith("~"):
            base = constraint[1:]
            parts = base.split(".")
            if len(parts) >= 2:
                upper = f"{int(parts[0])}.{int(parts[1]) + 1}"
            else:
                upper = f"{int(parts[0]) + 1}"
            spec = SpecifierSet(f">={base},<{upper}")
        else:
            spec = SpecifierSet(constraint)
        return installed_v in spec
    except Exception:  # noqa: BLE001
        logger.debug(
            "pin compatible check failed installed=%s pin=%s", installed, pin, exc_info=True
        )
        return None


def framework_version_cognition(project_root: Path | None = None) -> dict[str, Any]:
    """Return installed / project_pin / compatible for agent pin decisions."""
    installed = _installed_version()
    pin = _project_pin(project_root)
    compatible = _pin_compatible(installed, pin)
    return {
        "installed": installed,
        "project_pin": pin,
        "compatible": compatible,
        "hint": (
            "Trust this triple over CLI banner alone. Init stamps "
            "~{{major.minor}} from installed package. "
            "knowledge concept=version_cognition; counter-prior version_pin_distrust."
        ),
    }
