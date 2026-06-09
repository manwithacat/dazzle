"""Small IO helpers for loading optional persisted state.

The recurring smell (code-smells round 2026-05-28, pattern 1) is
``except (json.JSONDecodeError, OSError): return <empty>`` — which conflates a
**missing** file (legitimately optional) with a **corrupt** one (should be
surfaced). ``load_json_or`` splits the two: missing → silent default,
corrupt/unreadable → WARNING + default, so callers degrade gracefully without
masking corruption.

New persistence loaders should route optional-JSON reads through here rather
than re-inventing the swallow.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_json_or(path: Path | str, default: Any) -> Any:
    """Load JSON from ``path``; ``default`` if absent, log+``default`` if corrupt.

    - Missing file (``FileNotFoundError``) is the legitimately-optional case — silent.
    - A file that EXISTS but fails to parse (``json.JSONDecodeError`` /
      ``UnicodeDecodeError`` / other ``OSError``) is surfaced at WARNING with the
      path, then ``default`` is returned.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        logger.warning("corrupt or unreadable JSON at %s: %s", path, exc)
        return default
