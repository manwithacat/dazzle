"""Tests for _set_factory_env in combined_server.py."""

import os
from pathlib import Path
from unittest.mock import patch

from dazzle_ui.runtime.combined_server import _set_factory_env


class TestSetFactoryEnv:
    """Verify _set_factory_env propagates CLI flags to env vars."""

    def test_test_mode_sets_dazzle_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            _set_factory_env(Path("/tmp"), enable_dev_mode=False, enable_test_mode=True)
            assert os.environ["DAZZLE_ENV"] == "test"

    def test_dev_mode_sets_dazzle_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            _set_factory_env(Path("/tmp"), enable_dev_mode=True, enable_test_mode=False)
            assert os.environ["DAZZLE_ENV"] == "development"

    def test_test_mode_overrides_existing_production_env(self) -> None:
        """--test-mode must override DAZZLE_ENV=production (#466)."""
        with patch.dict(os.environ, {"DAZZLE_ENV": "production"}, clear=True):
            _set_factory_env(Path("/tmp"), enable_dev_mode=False, enable_test_mode=True)
            assert os.environ["DAZZLE_ENV"] == "test"

    def test_dev_mode_overrides_existing_env(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_ENV": "production"}, clear=True):
            _set_factory_env(Path("/tmp"), enable_dev_mode=True, enable_test_mode=False)
            assert os.environ["DAZZLE_ENV"] == "development"

    def test_neither_mode_leaves_env_unchanged(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_ENV": "production"}, clear=True):
            _set_factory_env(Path("/tmp"), enable_dev_mode=False, enable_test_mode=False)
            assert os.environ["DAZZLE_ENV"] == "production"

    def test_project_root_set_as_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            _set_factory_env(Path("/my/project"), enable_dev_mode=False, enable_test_mode=False)
            assert os.environ["DAZZLE_PROJECT_ROOT"] == "/my/project"

    def test_project_root_does_not_override_existing(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_PROJECT_ROOT": "/existing"}, clear=True):
            _set_factory_env(Path("/my/project"), enable_dev_mode=False, enable_test_mode=False)
            assert os.environ["DAZZLE_PROJECT_ROOT"] == "/existing"
