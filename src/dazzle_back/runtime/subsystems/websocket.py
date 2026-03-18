"""WebSocket / real-time subsystem (placeholder).

Reserved for mounting WebSocket and Server-Sent Events routes for real-time
entity presence, notifications, and live updates.  Not enabled by default —
callers may subclass or replace this subsystem.
"""

from __future__ import annotations

import logging

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class WebSocketSubsystem:
    name = "websocket"

    def startup(self, ctx: SubsystemContext) -> None:
        pass

    def shutdown(self) -> None:
        pass
