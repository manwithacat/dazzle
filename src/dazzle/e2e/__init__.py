"""Dazzle e2e environment primitives.

Shared runner, mode registry, snapshot/restore, and lifecycle management for
launching example Dazzle apps as live test environments.

v1 exposes Mode A (developer one-shot) + the snapshot primitive. Modes B, C,
and D are sketched in the design spec but not wired in v1. Import from the
submodules (``errors``, ``runner``, ``snapshot``, ...).
"""
