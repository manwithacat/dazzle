"""Re-export mailbox-shape from core (HTTP callers stay put)."""

from dazzle.core.mailbox_shape import MAILBOX_SHAPE_MAX, is_mailbox_shape

__all__ = ["MAILBOX_SHAPE_MAX", "is_mailbox_shape"]
