#!/bin/bash
#
# Test Homebrew installation locally before releasing
#
# Usage: ./scripts/test-homebrew-install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FORMULA_PATH="$PROJECT_ROOT/homebrew/dazzle.rb"

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

# Uninstall if already installed
if brew list dazzle &> /dev/null; then
    echo "🗑️  Uninstalling existing DAZZLE..."
    brew uninstall dazzle
    echo
fi

# Install from local formula
echo "📦 Installing DAZZLE from local formula..."
echo "   This will build from source..."
echo

if brew install --build-from-source "$FORMULA_PATH"; then
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

# Test version
echo "📋 Testing --version..."
VERSION_OUTPUT=$(dazzle --version 2>&1)
echo "   Output: $VERSION_OUTPUT"
echo "✅ Version check passed"
echo

# Test --help
echo "📋 Testing --help..."
if dazzle --help &> /dev/null; then
    echo "✅ Help command passed"
else
    echo "❌ Help command failed"
    exit 1
fi
echo

# Test basic workflow
echo "🏗️  Testing basic workflow..."
TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"

echo "   Creating test project..."
if dazzle init test-app --backend django_micro_modular &> /dev/null; then
    echo "✅ Init passed"
else
    echo "❌ Init failed"
    exit 1
fi

cd test-app

# Create simple DSL file
cat > dsl/app.dsl << 'EOF'
module test
app test "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  done: bool = false
EOF

echo "   Validating DSL..."
if dazzle validate; then
    echo "✅ Validate passed"
else
    echo "❌ Validate failed"
    exit 1
fi

echo

# Check Python location
echo "🐍 Checking Python environment..."
PYTHON_PATH=$(brew --prefix dazzle)/libexec/bin/python
if [ -f "$PYTHON_PATH" ]; then
    echo "✅ Python found: $PYTHON_PATH"
    PYTHON_VERSION=$($PYTHON_PATH --version)
    echo "   Version: $PYTHON_VERSION"
else
    echo "⚠️  Python not found at expected location"
fi

echo

# Check that dazzle module is importable
echo "📦 Checking Python package..."
if $PYTHON_PATH -c "import dazzle; print(f'✅ dazzle module version: {dazzle.__version__}')" 2>/dev/null; then
    :
else
    echo "❌ Failed to import dazzle module"
    exit 1
fi

echo

# List installed files
echo "📁 Installation structure:"
brew --prefix dazzle | xargs ls -la
echo

# Cleanup
cd /
rm -rf "$TEST_DIR"

echo "=================================="
echo "✅ All tests passed!"
echo
echo "Installation details:"
echo "  Location: $(brew --prefix dazzle)"
echo "  Binary: $(which dazzle)"
echo "  Python: $(brew --prefix dazzle)/libexec/bin/python"
echo
echo "To uninstall:"
echo "  brew uninstall dazzle"
echo
