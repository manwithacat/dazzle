"""Regression test for the channel resolver's resolution log (#1563).

`_log_resolution` passed a 3-placeholder `%s` format string to `logger.info`
with no positional args, so the console emitted the literal `%s` on every boot.
"""

import logging

from dazzle.http.channels.detection import DetectionResult, ProviderStatus
from dazzle.http.channels.resolver import ChannelResolver


def test_resolution_log_interpolates_placeholders(caplog) -> None:
    result = DetectionResult(
        provider_name="mailpit",
        status=ProviderStatus.AVAILABLE,
        connection_url="smtp://localhost:1025",
        detection_method="port",
    )
    with caplog.at_level(logging.INFO, logger="dazzle.http.channels.resolver"):
        ChannelResolver()._log_resolution("email", result, "port")

    msgs = [r.getMessage() for r in caplog.records]
    assert msgs, "expected a resolution log record"
    joined = " ".join(msgs)
    assert "%s" not in joined  # the bug: literal, uninterpolated format string
    assert "email" in joined
    assert "mailpit" in joined
    assert "port" in joined
