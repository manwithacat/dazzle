"""Linear mailbox-shape check (CodeQL py/polynomial-redos #227).

Leftover-honest auth/SCIM/list-filter used
``^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$``. The two ``[^@\\s]+`` groups around
the last-dot split overlap, so CodeQL flags quadratic time on
``!@!.`` + ``!.`` * n. Partition + a single label scan is O(n).
RFC 5321 path max 254 — bound first so a sloppy caller stays cheap.
"""

from __future__ import annotations

# RFC 5321 forward-path maximum. Bound before any scan.
MAILBOX_SHAPE_MAX: int = 254


def is_mailbox_shape(text: str) -> bool:
    """True when *text* is ``local@label(.label)+`` with no spaces.

    Labels cannot be empty (no leading / trailing / doubled dots).
    Does not parse RFC 5322 — leftover-honest mailbox *shape* only.
    """
    if not text or len(text) > MAILBOX_SHAPE_MAX:
        return False
    at = text.find("@")
    if at <= 0 or at != text.rfind("@"):
        return False
    local = text[:at]
    domain = text[at + 1 :]
    if not domain:
        return False
    for ch in local:
        if ch.isspace():
            return False
    saw_dot = False
    label_len = 0
    for ch in domain:
        if ch.isspace() or ch == "@":
            return False
        if ch == ".":
            if label_len == 0:
                return False
            saw_dot = True
            label_len = 0
            continue
        label_len += 1
    return saw_dot and label_len > 0
