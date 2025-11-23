#!/bin/bash
# Verification script for dual-version development setup

set -e

echo "=================================================="
echo "Dazzle Development Setup Verification"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check 1: pyenv is installed
echo "✓ Checking pyenv installation..."
if command -v pyenv &> /dev/null; then
    echo -e "${GREEN}  ✓ pyenv found: $(pyenv --version)${NC}"
else
    echo -e "${RED}  ✗ pyenv not found${NC}"
    exit 1
fi
echo ""

# Check 2: dazzle-dev virtualenv exists
echo "✓ Checking dazzle-dev virtualenv..."
if pyenv virtualenvs | grep -q "dazzle-dev"; then
    echo -e "${GREEN}  ✓ dazzle-dev virtualenv exists${NC}"
else
    echo -e "${RED}  ✗ dazzle-dev virtualenv not found${NC}"
    echo "  Run: pyenv virtualenv 3.12.11 dazzle-dev"
    exit 1
fi
echo ""

# Check 3: .python-version file exists
echo "✓ Checking .python-version file..."
if [ -f ".python-version" ]; then
    version_content=$(cat .python-version)
    if [ "$version_content" = "dazzle-dev" ]; then
        echo -e "${GREEN}  ✓ .python-version correctly set to dazzle-dev${NC}"
    else
        echo -e "${YELLOW}  ⚠ .python-version exists but set to: $version_content${NC}"
    fi
else
    echo -e "${RED}  ✗ .python-version file not found${NC}"
    echo "  Run: echo 'dazzle-dev' > .python-version"
    exit 1
fi
echo ""

# Check 4: Current Python version
echo "✓ Checking active Python version..."
current_version=$(pyenv version)
if [[ "$current_version" == *"dazzle-dev"* ]]; then
    echo -e "${GREEN}  ✓ $current_version${NC}"
else
    echo -e "${YELLOW}  ⚠ Not using dazzle-dev: $current_version${NC}"
    echo "  This is expected if running from outside project directory"
fi
echo ""

# Check 5: dazzle command exists
echo "✓ Checking dazzle command..."
if command -v dazzle &> /dev/null; then
    dazzle_path=$(which dazzle)
    echo -e "${GREEN}  ✓ dazzle found at: $dazzle_path${NC}"

    # Check if it's from pyenv shims
    if [[ "$dazzle_path" == *".pyenv/shims"* ]]; then
        echo -e "${GREEN}  ✓ Using pyenv shims (correct)${NC}"
    else
        echo -e "${YELLOW}  ⚠ Not using pyenv shims${NC}"
    fi
else
    echo -e "${RED}  ✗ dazzle command not found${NC}"
    exit 1
fi
echo ""

# Check 6: dazzle is editable install
echo "✓ Checking dazzle installation type..."
install_info=$(pip show dazzle 2>/dev/null)
if echo "$install_info" | grep -q "Editable project location"; then
    editable_path=$(echo "$install_info" | grep "Editable project location" | cut -d: -f2- | xargs)
    echo -e "${GREEN}  ✓ Editable install from: $editable_path${NC}"
else
    echo -e "${YELLOW}  ⚠ Not an editable install${NC}"
    echo "  Run: pip install -e '/Volumes/SSD/Dazzle[llm]'"
fi
echo ""

# Check 7: dazzle version and features
echo "✓ Checking dazzle features..."
version_output=$(dazzle --version 2>&1)

if echo "$version_output" | grep -q "LSP Server.*✓"; then
    echo -e "${GREEN}  ✓ LSP Server available${NC}"
else
    echo -e "${YELLOW}  ⚠ LSP Server not available${NC}"
    echo "  Run: pip install pygls"
fi

if echo "$version_output" | grep -q "LLM Support.*✓"; then
    echo -e "${GREEN}  ✓ LLM Support available${NC}"
else
    echo -e "${YELLOW}  ⚠ LLM Support not available${NC}"
    echo "  Run: pip install -e '/Volumes/SSD/Dazzle[llm]'"
fi
echo ""

# Check 8: Homebrew dazzle (informational)
echo "✓ Checking homebrew installation..."
if [ -f "/opt/homebrew/bin/dazzle" ]; then
    echo -e "${YELLOW}  ⚠ Homebrew dazzle is installed at /opt/homebrew/bin/dazzle${NC}"
    echo "    (Development version takes precedence via pyenv)"
else
    echo -e "${GREEN}  ✓ No homebrew dazzle installed (good for development)${NC}"
fi
echo ""

# Summary
echo "=================================================="
echo "Summary"
echo "=================================================="
echo ""
echo "Development setup is ready! ✨"
echo ""
echo "Quick tips:"
echo "  • Changes to code take effect immediately (editable install)"
echo "  • Auto-activates when you cd to /Volumes/SSD/Dazzle"
echo "  • Outside project: dazzle won't be available (expected)"
echo ""
echo "To test homebrew version:"
echo "  cd ~ && brew install --build-from-source /Volumes/SSD/Dazzle/homebrew/dazzle.rb"
echo "  /opt/homebrew/bin/dazzle --version"
echo ""
echo "Documentation: dev_docs/dual_version_workflow.md"
echo ""
