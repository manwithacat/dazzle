#!/usr/bin/env python3
"""Test backend plugin system."""

from pathlib import Path

from dazzle.core import ir
from dazzle.stacks import (
    Backend,
    BackendCapabilities,
    BackendError,
    BackendRegistry,
)


class MockBackend(Backend):
    """Mock backend for testing."""

    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options) -> None:
        """Mock generate - just creates a marker file."""
        (output_dir / "generated.txt").write_text(f"Generated from {appspec.name}")

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="mock",
            description="Mock backend for testing",
            output_formats=["txt"],
        )


class MockBackendWithConfig(Backend):
    """Mock backend that requires config."""

    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options) -> None:
        api_key = options.get("api_key")
        if not api_key:
            raise BackendError("Missing required option: api_key")
        (output_dir / "config.txt").write_text(f"API Key: {api_key}")

    def validate_config(self, **options) -> None:
        if "api_key" not in options:
            raise BackendError("Missing required option: api_key")

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="mock_config",
            description="Mock backend with config",
            output_formats=["txt"],
            requires_config=True,
        )


def test_backend_registration():
    """Test manual backend registration."""
    print("Testing backend registration...")

    registry = BackendRegistry()

    # Register mock backend
    registry.register("mock", MockBackend)

    # Verify it's registered
    backends = registry.list_backends()
    assert "mock" in backends
    print("  ✓ Backend registered successfully")

    # Get backend instance
    backend = registry.get("mock")
    assert isinstance(backend, MockBackend)
    print("  ✓ Backend instance retrieved")


def test_duplicate_registration():
    """Test that duplicate registration raises error."""
    print("Testing duplicate registration detection...")

    registry = BackendRegistry()
    registry.register("mock", MockBackend)

    try:
        registry.register("mock", MockBackend)
        raise AssertionError("Should have raised BackendError for duplicate")
    except BackendError as e:
        assert "already registered" in str(e)
        print("  ✓ Duplicate registration detected")


def test_missing_backend():
    """Test error handling for missing backend."""
    print("Testing missing backend error...")

    registry = BackendRegistry()

    try:
        registry.get("nonexistent")
        raise AssertionError("Should have raised BackendError for missing backend")
    except BackendError as e:
        assert "not found" in str(e)
        assert "Available backends" in str(e)
        print("  ✓ Missing backend error raised with helpful message")


def test_backend_generate():
    """Test backend generate method."""
    print("Testing backend generate...")

    import tempfile

    registry = BackendRegistry()
    registry.register("mock", MockBackend)

    backend = registry.get("mock")

    # Create test AppSpec
    appspec = ir.AppSpec(
        name="test_app",
        title="Test App",
        domain=ir.DomainSpec(entities=[]),
    )

    # Generate to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        backend.generate(appspec, output_dir)

        # Verify output
        output_file = output_dir / "generated.txt"
        assert output_file.exists()
        assert output_file.read_text() == "Generated from test_app"
        print("  ✓ Backend generated output successfully")


def test_backend_capabilities():
    """Test backend capabilities introspection."""
    print("Testing backend capabilities...")

    backend = MockBackend()
    capabilities = backend.get_capabilities()

    assert capabilities.name == "mock"
    assert capabilities.description == "Mock backend for testing"
    assert "txt" in capabilities.output_formats
    assert capabilities.supports_incremental is False
    assert capabilities.requires_config is False
    print("  ✓ Backend capabilities retrieved")


def test_backend_config_validation():
    """Test backend config validation."""
    print("Testing backend config validation...")

    backend = MockBackendWithConfig()

    # Test missing config
    try:
        backend.validate_config()
        raise AssertionError("Should have raised BackendError for missing config")
    except BackendError as e:
        assert "api_key" in str(e)
        print("  ✓ Missing config detected")

    # Test valid config
    backend.validate_config(api_key="test-key")
    print("  ✓ Valid config accepted")


def test_backend_with_config():
    """Test backend that requires config."""
    print("Testing backend with config...")

    import tempfile

    backend = MockBackendWithConfig()

    appspec = ir.AppSpec(
        name="test_app",
        title="Test App",
        domain=ir.DomainSpec(entities=[]),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Test with valid config
        backend.generate(appspec, output_dir, api_key="test-key-123")

        output_file = output_dir / "config.txt"
        assert output_file.exists()
        assert "test-key-123" in output_file.read_text()
        print("  ✓ Backend used config options")


def test_invalid_backend_class():
    """Test that non-Backend classes are rejected."""
    print("Testing invalid backend class rejection...")

    registry = BackendRegistry()

    class NotABackend:
        pass

    try:
        registry.register("invalid", NotABackend)
        raise AssertionError("Should have raised BackendError for invalid class")
    except BackendError as e:
        assert "must extend Backend" in str(e)
        print("  ✓ Invalid backend class rejected")


def test_backend_discovery():
    """Test auto-discovery of backends."""
    print("Testing backend auto-discovery...")

    registry = BackendRegistry()

    # Manually register a backend first
    registry.register("mock", MockBackend)

    # Run discovery
    registry.discover()

    # Verify mock backend still registered
    assert "mock" in registry.list_backends()
    print("  ✓ Discovery doesn't break existing registrations")

    # Note: We don't have any real backend files yet,
    # so discovery won't find anything new.
    # This test mainly verifies discovery doesn't crash.


def test_list_backends():
    """Test listing all backends."""
    print("Testing backend listing...")

    registry = BackendRegistry()
    registry.register("mock1", MockBackend)
    registry.register("mock2", MockBackendWithConfig)

    backends = registry.list_backends()
    assert "mock1" in backends
    assert "mock2" in backends
    assert len(backends) == 2
    print("  ✓ Backend list correct")


def main():
    """Run all backend tests."""
    print("=" * 60)
    print("Stage 5: Backend Plugin System Tests")
    print("=" * 60)
    print()

    try:
        test_backend_registration()
        test_duplicate_registration()
        test_missing_backend()
        test_backend_generate()
        test_backend_capabilities()
        test_backend_config_validation()
        test_backend_with_config()
        test_invalid_backend_class()
        test_backend_discovery()
        test_list_backends()

        print()
        print("=" * 60)
        print("✅ All Stage 5 backend tests passed!")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Test failed!")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
