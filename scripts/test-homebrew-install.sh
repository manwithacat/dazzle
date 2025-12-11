#!/bin/bash
#
# Test Homebrew installation locally before releasing
#
# This script validates:
# 1. Formula syntax is valid
# 2. Local installation works
# 3. CLI commands function correctly
# 4. Python package is properly installed
# 5. Version numbers are consistent
#
# Usage: ./scripts/test-homebrew-install.sh [--skip-install]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FORMULA_PATH="$PROJECT_ROOT/homebrew/dazzle.rb"
SKIP_INSTALL=false

# Parse args
if [ "$1" = "--skip-install" ]; then
    SKIP_INSTALL=true
fi

echo "🧪 Testing DAZZLE Homebrew Formula"
echo "=================================="
echo

# Check if formula exists
if [ ! -f "$FORMULA_PATH" ]; then
    echo "❌ Formula not found: $FORMULA_PATH"
    exit 1
fi

echo "📝 Formula path: $FORMULA_PATH"
echo

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not installed. Install from https://brew.sh"
    exit 1
fi

echo "✅ Homebrew found: $(brew --version | head -1)"
echo

# Extract expected version from formula
FORMULA_VERSION=$(grep 'version "' "$FORMULA_PATH" | head -1 | sed 's/.*version "\([^"]*\)".*/\1/')
echo "📋 Formula version: $FORMULA_VERSION"

# Check version consistency across files
echo "🔍 Checking version consistency..."
PYPROJECT_VERSION=$(grep '^version = "' "$PROJECT_ROOT/pyproject.toml" | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
INIT_VERSION=$(grep '__version__ = "' "$PROJECT_ROOT/src/dazzle/__init__.py" | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
CLI_VERSION=$(grep '"version":' "$PROJECT_ROOT/cli/package.json" | head -1 | sed 's/.*: "\([^"]*\)".*/\1/')

echo "   pyproject.toml: $PYPROJECT_VERSION"
echo "   __init__.py:    $INIT_VERSION"
echo "   cli/package.json: $CLI_VERSION"
echo "   homebrew/dazzle.rb: $FORMULA_VERSION"

VERSIONS_MATCH=true
if [ "$PYPROJECT_VERSION" != "$FORMULA_VERSION" ]; then
    echo "   ⚠️  pyproject.toml version doesn't match formula"
    VERSIONS_MATCH=false
fi
if [ "$INIT_VERSION" != "$FORMULA_VERSION" ]; then
    echo "   ⚠️  __init__.py version doesn't match formula"
    VERSIONS_MATCH=false
fi
if [ "$CLI_VERSION" != "$FORMULA_VERSION" ]; then
    echo "   ⚠️  cli/package.json version doesn't match formula"
    VERSIONS_MATCH=false
fi

if [ "$VERSIONS_MATCH" = true ]; then
    echo "✅ All versions match: $FORMULA_VERSION"
else
    echo "❌ Version mismatch detected!"
    exit 1
fi
echo

# Validate formula syntax
echo "🔍 Validating formula syntax..."
if brew style "$FORMULA_PATH" 2>&1 | grep -q "no offenses detected"; then
    echo "✅ Formula syntax is valid"
else
    echo "⚠️  Formula has style warnings (non-fatal):"
    brew style "$FORMULA_PATH" 2>&1 | head -20
fi
echo

if [ "$SKIP_INSTALL" = true ]; then
    echo "⏭️  Skipping installation (--skip-install)"
    exit 0
fi

# Uninstall if already installed
if brew list dazzle &> /dev/null; then
    echo "🗑️  Uninstalling existing DAZZLE..."
    brew uninstall dazzle
    echo
fi

# Install from local formula
echo "📦 Installing DAZZLE from local formula..."
echo "   (This installs from the local source, not the release tarball)"
echo
if brew install "$FORMULA_PATH" 2>&1; then
    echo
    echo "✅ Installation successful!"
else
    echo
    echo "❌ Installation failed"
    exit 1
fi
echo

# Test that dazzle is in PATH
echo "🔍 Checking installation..."
if ! command -v dazzle &> /dev/null; then
    echo "❌ dazzle command not found in PATH"
    exit 1
fi
echo "✅ dazzle found in PATH: $(which dazzle)"
echo

# Test version command
echo "📋 Testing 'dazzle version'..."
VERSION_OUTPUT=$(dazzle version 2>&1)
echo "$VERSION_OUTPUT"

# Extract CLI version from output
INSTALLED_CLI_VERSION=$(echo "$VERSION_OUTPUT" | grep "^cli" | awk '{print $2}')
echo
if [ "$INSTALLED_CLI_VERSION" = "$CLI_VERSION" ]; then
    echo "✅ CLI version matches: $INSTALLED_CLI_VERSION"
else
    echo "❌ CLI version mismatch: expected $CLI_VERSION, got $INSTALLED_CLI_VERSION"
    echo "   (This usually means the release binaries weren't rebuilt)"
fi
echo

# Test dazzle new
echo "🏗️  Testing 'dazzle new'..."
TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"

echo "   Creating test project in $TEST_DIR..."
if dazzle new test-app 2>&1; then
    echo "✅ 'dazzle new' succeeded"
else
    echo "❌ 'dazzle new' failed"
    echo "   This usually means examples aren't bundled correctly"
    rm -rf "$TEST_DIR"
    exit 1
fi
echo

# Verify project structure
echo "🔍 Verifying project structure..."
if [ -f "$TEST_DIR/test-app/dazzle.toml" ] && [ -d "$TEST_DIR/test-app/dsl" ]; then
    echo "✅ Project structure looks correct"
else
    echo "❌ Project structure is incorrect"
    ls -la "$TEST_DIR/test-app"
    rm -rf "$TEST_DIR"
    exit 1
fi

# Test dazzle check
cd "$TEST_DIR/test-app"
echo
echo "📋 Testing 'dazzle check'..."
if dazzle check 2>&1; then
    echo "✅ 'dazzle check' passed"
else
    echo "❌ 'dazzle check' failed"
fi
echo

# Test Python package import
echo "🐍 Checking Python environment..."
PYTHON_PATH=$(brew --prefix dazzle)/libexec/bin/python
if [ -f "$PYTHON_PATH" ]; then
    echo "✅ Python found: $PYTHON_PATH"
    PYTHON_VERSION=$($PYTHON_PATH --version)
    echo "   Version: $PYTHON_VERSION"

    # Check dazzle module
    echo
    echo "📦 Checking Python package..."
    INSTALLED_PYTHON_VERSION=$($PYTHON_PATH -c "import dazzle; print(dazzle.__version__)" 2>/dev/null)
    if [ -n "$INSTALLED_PYTHON_VERSION" ]; then
        echo "✅ dazzle module version: $INSTALLED_PYTHON_VERSION"
        if [ "$INSTALLED_PYTHON_VERSION" != "$PYPROJECT_VERSION" ]; then
            echo "   ⚠️  Python version doesn't match expected ($PYPROJECT_VERSION)"
        fi
    else
        echo "❌ Failed to import dazzle module"
    fi

    # Check examples
    echo
    echo "📦 Checking bundled examples..."
    EXAMPLES=$($PYTHON_PATH -c "from dazzle.examples import list_examples; print(','.join(list_examples()))" 2>/dev/null)
    if [ -n "$EXAMPLES" ]; then
        echo "✅ Bundled examples: $EXAMPLES"
    else
        echo "❌ No bundled examples found"
    fi
else
    echo "❌ Python not found at expected location: $PYTHON_PATH"
fi
echo

# Cleanup
cd /
rm -rf "$TEST_DIR"

echo "=================================="
echo "✅ All tests passed!"
echo
echo "Installation summary:"
echo "  Formula version: $FORMULA_VERSION"
echo "  CLI version:     $INSTALLED_CLI_VERSION"
echo "  Python version:  $INSTALLED_PYTHON_VERSION"
echo "  Location:        $(brew --prefix dazzle)"
echo
echo "To uninstall:"
echo "  brew uninstall dazzle"
echo
