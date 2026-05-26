"""Branded types for identifier classes — distinguish UserId from TenantId.

Counter-prior: `magic-string-typing`. The catalogue at
`docs/counter-priors/magic-string-typing.md` explains the antipattern this
shape inoculates against and the convention for declaring branded ID types.

NewType is Python stdlib (typing.NewType) and is runtime-free — the
returned callable is the identity function. The type checker treats
`UserId = NewType("UserId", str)` as distinct from str, catching mix-ups
between identifier classes.

Convention: declare branded types where they belong (typically `app/ids.py`).
This module re-exports NewType for one-stop discovery; you do not need to
import from typing at all.

Example:

    from dazzle.types import NewType

    UserId = NewType("UserId", str)
    TenantId = NewType("TenantId", str)

    def fetch(uid: UserId, tid: TenantId) -> User:
        ...

    # Type checker catches: fetch(tid, uid)  # arguments swapped, would silently break
"""

from __future__ import annotations

from typing import NewType

__all__ = ["NewType"]
