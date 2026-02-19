"""Tests for dazzle_back.runtime.aws_config."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from dazzle_back.runtime.aws_config import (
    AWSConfig,
    get_aioboto3_session,
    get_aws_config,
    get_boto3_session,
)

# ---------------------------------------------------------------------------
# Env-var names used by the module under test
# ---------------------------------------------------------------------------
_ALL_ENV_VARS = (
    "DAZZLE_AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "DAZZLE_AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL",
)


@pytest.fixture(autouse=True)
def _clear_env_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all AWS env vars and clear the lru_cache before each test."""
    for var in _ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    get_aws_config.cache_clear()


# ===================================================================
# get_aws_config() — region resolution
# ===================================================================


class TestGetAwsConfigRegion:
    """Region precedence: DAZZLE_AWS_REGION > AWS_DEFAULT_REGION > AWS_REGION > us-east-1."""

    def test_defaults_to_us_east_1(self) -> None:
        cfg = get_aws_config()
        assert cfg.region == "us-east-1"

    def test_aws_region_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        cfg = get_aws_config()
        assert cfg.region == "eu-west-1"

    def test_aws_default_region_takes_precedence_over_aws_region(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
        cfg = get_aws_config()
        assert cfg.region == "ap-south-1"

    def test_dazzle_aws_region_takes_precedence_over_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
        monkeypatch.setenv("DAZZLE_AWS_REGION", "us-west-2")
        cfg = get_aws_config()
        assert cfg.region == "us-west-2"

    def test_dazzle_aws_region_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_AWS_REGION", "ca-central-1")
        cfg = get_aws_config()
        assert cfg.region == "ca-central-1"


# ===================================================================
# get_aws_config() — credentials
# ===================================================================


class TestGetAwsConfigCredentials:
    """Access key and secret key reading."""

    def test_no_credentials_returns_none(self) -> None:
        cfg = get_aws_config()
        assert cfg.access_key_id is None
        assert cfg.secret_access_key is None

    def test_reads_access_key_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
        cfg = get_aws_config()
        assert cfg.access_key_id == "AKIAIOSFODNN7EXAMPLE"

    def test_reads_secret_access_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
        cfg = get_aws_config()
        assert cfg.secret_access_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def test_reads_both_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
        cfg = get_aws_config()
        assert cfg.access_key_id == "AKID"
        assert cfg.secret_access_key == "SECRET"


# ===================================================================
# get_aws_config() — endpoint_url
# ===================================================================


class TestGetAwsConfigEndpoint:
    """Endpoint URL for LocalStack/testing."""

    def test_no_endpoint_returns_none(self) -> None:
        cfg = get_aws_config()
        assert cfg.endpoint_url is None

    def test_dazzle_aws_endpoint_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_AWS_ENDPOINT_URL", "http://localhost:4566")
        cfg = get_aws_config()
        assert cfg.endpoint_url == "http://localhost:4566"

    def test_aws_endpoint_url_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4567")
        cfg = get_aws_config()
        assert cfg.endpoint_url == "http://localhost:4567"

    def test_dazzle_endpoint_takes_precedence_over_aws_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4567")
        monkeypatch.setenv("DAZZLE_AWS_ENDPOINT_URL", "http://localhost:4566")
        cfg = get_aws_config()
        assert cfg.endpoint_url == "http://localhost:4566"


# ===================================================================
# get_aws_config() — caching
# ===================================================================


class TestGetAwsConfigCaching:
    """functools.cache memoizes the result."""

    def test_returns_same_object_on_repeated_calls(self) -> None:
        cfg1 = get_aws_config()
        cfg2 = get_aws_config()
        assert cfg1 is cfg2

    def test_cache_clear_returns_fresh_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg1 = get_aws_config()
        assert cfg1.region == "us-east-1"

        monkeypatch.setenv("DAZZLE_AWS_REGION", "eu-north-1")
        get_aws_config.cache_clear()
        cfg2 = get_aws_config()
        assert cfg2.region == "eu-north-1"
        assert cfg1 is not cfg2


# ===================================================================
# AWSConfig.to_boto3_kwargs()
# ===================================================================


class TestToBoto3Kwargs:
    """Test the kwargs dict generation for boto3 clients."""

    def test_region_always_present(self) -> None:
        cfg = AWSConfig(region="us-east-1")
        kwargs = cfg.to_boto3_kwargs()
        assert kwargs == {"region_name": "us-east-1"}

    def test_includes_credentials_when_set(self) -> None:
        cfg = AWSConfig(
            region="eu-west-1",
            access_key_id="AKID",
            secret_access_key="SECRET",
        )
        kwargs = cfg.to_boto3_kwargs()
        assert kwargs == {
            "region_name": "eu-west-1",
            "aws_access_key_id": "AKID",
            "aws_secret_access_key": "SECRET",
        }

    def test_includes_endpoint_url_when_set(self) -> None:
        cfg = AWSConfig(region="us-east-1", endpoint_url="http://localhost:4566")
        kwargs = cfg.to_boto3_kwargs()
        assert kwargs == {
            "region_name": "us-east-1",
            "endpoint_url": "http://localhost:4566",
        }

    def test_excludes_credentials_when_none(self) -> None:
        cfg = AWSConfig(region="us-east-1", access_key_id=None, secret_access_key=None)
        kwargs = cfg.to_boto3_kwargs()
        assert "aws_access_key_id" not in kwargs
        assert "aws_secret_access_key" not in kwargs

    def test_excludes_endpoint_url_when_none(self) -> None:
        cfg = AWSConfig(region="us-east-1", endpoint_url=None)
        kwargs = cfg.to_boto3_kwargs()
        assert "endpoint_url" not in kwargs

    def test_all_fields_set(self) -> None:
        cfg = AWSConfig(
            region="ap-southeast-1",
            access_key_id="AKID",
            secret_access_key="SECRET",
            endpoint_url="http://localstack:4566",
        )
        kwargs = cfg.to_boto3_kwargs()
        assert kwargs == {
            "region_name": "ap-southeast-1",
            "aws_access_key_id": "AKID",
            "aws_secret_access_key": "SECRET",
            "endpoint_url": "http://localstack:4566",
        }

    def test_empty_string_credentials_excluded(self) -> None:
        """Empty strings are falsy, so they should not appear in kwargs."""
        cfg = AWSConfig(region="us-east-1", access_key_id="", secret_access_key="")
        kwargs = cfg.to_boto3_kwargs()
        assert "aws_access_key_id" not in kwargs
        assert "aws_secret_access_key" not in kwargs

    def test_empty_string_endpoint_excluded(self) -> None:
        """Empty endpoint_url string is falsy and should be omitted."""
        cfg = AWSConfig(region="us-east-1", endpoint_url="")
        kwargs = cfg.to_boto3_kwargs()
        assert "endpoint_url" not in kwargs


# ===================================================================
# AWSConfig frozen dataclass
# ===================================================================


class TestAWSConfigDataclass:
    """AWSConfig is a frozen dataclass."""

    def test_is_frozen(self) -> None:
        cfg = AWSConfig(region="us-east-1")
        with pytest.raises(AttributeError):
            cfg.region = "eu-west-1"  # type: ignore[misc]

    def test_equality(self) -> None:
        cfg1 = AWSConfig(region="us-east-1", access_key_id="AKID")
        cfg2 = AWSConfig(region="us-east-1", access_key_id="AKID")
        assert cfg1 == cfg2

    def test_inequality(self) -> None:
        cfg1 = AWSConfig(region="us-east-1")
        cfg2 = AWSConfig(region="eu-west-1")
        assert cfg1 != cfg2


# ===================================================================
# get_boto3_session()
# ===================================================================


class TestGetBoto3Session:
    """Test boto3 session creation with mocked boto3 import."""

    def test_creates_session_with_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_boto3 = MagicMock()
        mock_session = MagicMock()
        mock_boto3.Session.return_value = mock_session
        monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

        config = AWSConfig(
            region="eu-west-1",
            access_key_id="AKID",
            secret_access_key="SECRET",
        )
        result = get_boto3_session(config)

        mock_boto3.Session.assert_called_once_with(
            region_name="eu-west-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET",
        )
        assert result is mock_session

    def test_creates_session_without_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_boto3 = MagicMock()
        monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

        config = AWSConfig(region="us-east-1")
        get_boto3_session(config)

        mock_boto3.Session.assert_called_once_with(region_name="us-east-1")

    def test_uses_get_aws_config_when_config_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_boto3 = MagicMock()
        monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
        monkeypatch.setenv("DAZZLE_AWS_REGION", "sa-east-1")
        get_aws_config.cache_clear()

        get_boto3_session(None)

        mock_boto3.Session.assert_called_once_with(region_name="sa-east-1")

    def test_import_error_with_helpful_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Ensure boto3 cannot be imported by removing it from sys.modules
        # and making the import fail.
        monkeypatch.delitem(sys.modules, "boto3", raising=False)

        # Create a fake module that raises ImportError on import
        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def fake_import(name: str, *args: object, **kwargs: object) -> ModuleType:
            if name == "boto3":
                raise ImportError("No module named 'boto3'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        with pytest.raises(ImportError, match="boto3 is required for AWS services"):
            get_boto3_session(AWSConfig(region="us-east-1"))


# ===================================================================
# get_aioboto3_session()
# ===================================================================


class TestGetAioboto3Session:
    """Test aioboto3 session creation with mocked aioboto3 import."""

    def test_creates_session_with_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_aioboto3 = MagicMock()
        mock_session = MagicMock()
        mock_aioboto3.Session.return_value = mock_session
        monkeypatch.setitem(sys.modules, "aioboto3", mock_aioboto3)

        config = AWSConfig(
            region="ap-northeast-1",
            access_key_id="AKID",
            secret_access_key="SECRET",
        )
        result = get_aioboto3_session(config)

        mock_aioboto3.Session.assert_called_once_with(
            region_name="ap-northeast-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET",
        )
        assert result is mock_session

    def test_creates_session_without_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_aioboto3 = MagicMock()
        monkeypatch.setitem(sys.modules, "aioboto3", mock_aioboto3)

        config = AWSConfig(region="us-west-2")
        get_aioboto3_session(config)

        mock_aioboto3.Session.assert_called_once_with(region_name="us-west-2")

    def test_uses_get_aws_config_when_config_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_aioboto3 = MagicMock()
        monkeypatch.setitem(sys.modules, "aioboto3", mock_aioboto3)
        monkeypatch.setenv("AWS_DEFAULT_REGION", "me-south-1")
        get_aws_config.cache_clear()

        get_aioboto3_session(None)

        mock_aioboto3.Session.assert_called_once_with(region_name="me-south-1")

    def test_import_error_with_helpful_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delitem(sys.modules, "aioboto3", raising=False)

        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def fake_import(name: str, *args: object, **kwargs: object) -> ModuleType:
            if name == "aioboto3":
                raise ImportError("No module named 'aioboto3'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        with pytest.raises(ImportError, match="aioboto3 is required for async AWS services"):
            get_aioboto3_session(AWSConfig(region="us-east-1"))


# ===================================================================
# Integration-style: get_aws_config → session factories
# ===================================================================


class TestEndToEndFlow:
    """Verify that env vars flow through get_aws_config into session factories."""

    def test_full_config_flows_to_boto3_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_AWS_REGION", "eu-central-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID_FULL")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET_FULL")
        monkeypatch.setenv("DAZZLE_AWS_ENDPOINT_URL", "http://localstack:4566")

        cfg = get_aws_config()
        assert cfg.region == "eu-central-1"
        assert cfg.access_key_id == "AKID_FULL"
        assert cfg.secret_access_key == "SECRET_FULL"
        assert cfg.endpoint_url == "http://localstack:4566"

        kwargs = cfg.to_boto3_kwargs()
        assert kwargs == {
            "region_name": "eu-central-1",
            "aws_access_key_id": "AKID_FULL",
            "aws_secret_access_key": "SECRET_FULL",
            "endpoint_url": "http://localstack:4566",
        }

    def test_minimal_config_flows_correctly(self) -> None:
        """No env vars set at all -- pure defaults."""
        cfg = get_aws_config()
        assert cfg.region == "us-east-1"
        assert cfg.access_key_id is None
        assert cfg.secret_access_key is None
        assert cfg.endpoint_url is None

        kwargs = cfg.to_boto3_kwargs()
        assert kwargs == {"region_name": "us-east-1"}
