#!/bin/bash
# Setup development environment for DAZZLE
# Run this after cloning the repository

set -e

echo "Setting up DAZZLE development environment..."
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.11"

if [[ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]]; then
    echo "Error: Python $required_version or higher is required (found $python_version)"
    exit 1
fi

echo "Python version: $python_version"

# Install package in development mode with all dependencies
echo ""
echo "Installing DAZZLE in development mode..."
pip install -e ".[dev,llm]"

# Install optional LSP dependencies
echo ""
echo "Installing optional dependencies..."
pip install pygls || true

# Install pre-commit hooks
echo ""
echo "Installing pre-commit hooks..."
pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push

echo ""
echo "============================================"
echo "Development environment setup complete!"
echo "============================================"
echo ""
echo "Pre-commit hooks installed:"
echo "  - pre-commit: lint, format, type-check, security, spell-check"
echo "  - pre-push: fast tests, build check"
echo ""
echo "Quick commands (or use Makefile):"
echo "  make help              # Show all available commands"
echo "  make ci                # Run all CI checks locally"
echo "  make test-fast         # Run fast tests"
echo "  make lint              # Run linter"
echo "  make format            # Format code"
echo "  make build             # Build Python package"
echo ""
echo "Manual commands:"
echo "  pre-commit run --all-files    # Run all pre-commit hooks"
echo "  pytest tests/ -x              # Run tests"
echo "  ruff check src/ tests/        # Run linter"
echo "  mypy src/dazzle               # Run type checker"
