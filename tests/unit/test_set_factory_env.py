"""Tests for _set_factory_env in combined_server.py."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from dazzle.back.runtime.combined_server import _set_factory_env


class TestSetFactoryEnv:
    """Verify _set_factory_env propagates CLI flags to env vars."""

    @pytest.mark.parametrize(
        ("starting_env", "dev_mode", "test_mode", "expected_env"),
        [
            # Empty env + flags → flag wins
            ({}, False, True, "test"),
            ({}, True, False, "development"),
            # CLI flags MUST override existing env (#466)
            ({"DAZZLE_ENV": "production"}, False, True, "test"),
            ({"DAZZLE_ENV": "production"}, True, False, "development"),
            # Neither flag set → existing env preserved
            ({"DAZZLE_ENV": "production"}, False, False, "production"),
        ],
        ids=[
            "test_mode_sets_env",
            "dev_mode_sets_env",
            "test_mode_overrides_production",
            "dev_mode_overrides_production",
            "neither_mode_leaves_unchanged",
        ],
    )
    def test_dazzle_env(self, starting_env, dev_mode, test_mode, expected_env) -> None:
        with patch.dict(os.environ, starting_env, clear=True):
            _set_factory_env(Path("/tmp"), enable_dev_mode=dev_mode, enable_test_mode=test_mode)
            assert os.environ["DAZZLE_ENV"] == expected_env

    @pytest.mark.parametrize(
        ("starting_env", "expected_root"),
        [
            ({}, "/my/project"),  # set when unset
            ({"DAZZLE_PROJECT_ROOT": "/existing"}, "/existing"),  # don't clobber
        ],
        ids=["set_when_unset", "preserve_when_set"],
    )
    def test_project_root(self, starting_env, expected_root) -> None:
        with patch.dict(os.environ, starting_env, clear=True):
            _set_factory_env(Path("/my/project"), enable_dev_mode=False, enable_test_mode=False)
            assert os.environ["DAZZLE_PROJECT_ROOT"] == expected_root
