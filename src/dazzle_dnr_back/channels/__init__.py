"""
Channel adapters and provider detection for DAZZLE messaging (v0.9.0).

This module provides:
- Provider auto-detection for email, queue, and stream channels
- Channel adapter base classes
- Runtime channel resolution
- Transactional outbox pattern
- Template rendering

Example:
    from dazzle_dnr_back.channels import ChannelResolver, OutboxRepository

    resolver = ChannelResolver()
    resolution = await resolver.resolve(channel_spec)
    adapter = resolution.adapter_class(resolution.provider)
    await adapter.send(message)
"""

from .adapters import BaseChannelAdapter, FileEmailAdapter, MailpitAdapter, SendResult
from .detection import (
    DetectionResult,
    ProviderDetector,
    ProviderStatus,
)
from .manager import (
    ChannelManager,
    ChannelStatus,
    create_channel_manager,
)
from .outbox import (
    OutboxMessage,
    OutboxRepository,
    OutboxStatus,
    create_outbox_message,
)
from .resolver import (
    ChannelConfigError,
    ChannelResolution,
    ChannelResolver,
)
from .templates import (
    TemplateError,
    TemplateRenderError,
    TemplateSyntaxError,
    extract_variables,
    render_template,
    validate_template,
)

__all__ = [
    # Detection
    "DetectionResult",
    "ProviderDetector",
    "ProviderStatus",
    # Resolver
    "ChannelConfigError",
    "ChannelResolution",
    "ChannelResolver",
    # Manager
    "ChannelManager",
    "ChannelStatus",
    "create_channel_manager",
    # Outbox
    "OutboxMessage",
    "OutboxRepository",
    "OutboxStatus",
    "create_outbox_message",
    # Adapters
    "BaseChannelAdapter",
    "SendResult",
    "MailpitAdapter",
    "FileEmailAdapter",
    # Templates
    "TemplateError",
    "TemplateSyntaxError",
    "TemplateRenderError",
    "render_template",
    "validate_template",
    "extract_variables",
]
