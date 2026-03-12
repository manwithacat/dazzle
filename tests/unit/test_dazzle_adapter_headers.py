"""Tests for DazzleAdapter test secret header propagation (#467)."""

from __future__ import annotations

import os
from unittest.mock import patch

from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter


class TestDazzleAdapterTestSecret:
    """Verify X-Test-Secret header is included when DAZZLE_TEST_SECRET is set."""

    def test_no_secret_no_header(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            adapter = DazzleAdapter()
            assert adapter._test_headers == {}

    def test_secret_sets_header(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_TEST_SECRET": "s3cret"}, clear=True):
            adapter = DazzleAdapter()
            assert adapter._test_headers == {"X-Test-Secret": "s3cret"}

    def test_reset_sync_sends_header(self) -> None:
        """reset_sync should include X-Test-Secret in request headers."""
        from unittest.mock import MagicMock

        with patch.dict(os.environ, {"DAZZLE_TEST_SECRET": "abc123"}, clear=True):
            adapter = DazzleAdapter(api_url="http://test:8000")

        # Verify the header dict is populated
        assert adapter._test_headers["X-Test-Secret"] == "abc123"

        # Verify httpx.Client would receive headers
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            adapter.reset_sync()

            mock_client_cls.assert_called_once_with(
                timeout=30.0, headers={"X-Test-Secret": "abc123"}
            )
