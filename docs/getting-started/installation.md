# Installation Guide

This guide covers multiple ways to install DAZZLE on your system.

## Prerequisites

- **Python 3.12 or higher** (Python 3.12 recommended)
- **pip** (usually comes with Python)
- **git** (for installation from source)

## Installation Methods

### Method 1: Install from PyPI (Recommended)

```bash
pip install dazzle-dsl
```

To install with LLM support (for DSL generation features):

```bash
pip install dazzle-dsl[llm]
```

To install for development:

```bash
pip install dazzle-dsl[dev]
```

### Method 2: Install from Source

For the latest development version or to contribute:

```bash
# Clone the repository
git clone https://github.com/manwithacat/dazzle.git
cd dazzle

# Install in editable mode
pip install -e .

# Or with all extras
pip install -e ".[dev,llm]"
```

### Method 3: Homebrew (macOS/Linux)

Install via our Homebrew tap:

```bash
brew install manwithacat/tap/dazzle
```

This installs DAZZLE with Python 3.12 in an isolated virtualenv and registers the MCP server with Claude Code automatically.

### Method 4: Using pipx (Isolated Environment)

To install DAZZLE in an isolated environment:

```bash
# Install pipx if you don't have it
python -m pip install --user pipx
python -m pipx ensurepath

# Install DAZZLE
pipx install dazzle-dsl

# Or from source
pipx install git+https://github.com/manwithacat/dazzle.git
```

### Method 5: Docker (Coming Soon)

Docker images will be available in a future release:

```bash
# Future command (not yet available)
docker pull ghcr.io/manwithacat/dazzle:latest
docker run -v $(pwd):/workspace ghcr.io/manwithacat/dazzle:latest validate
```

## Verification

After installation, verify DAZZLE is working:

```bash
# Check version
dazzle --version

# Check environment health
dazzle doctor

# Get help
dazzle --help

# Run a quick validation (if you have a DSL file)
dazzle validate
```

## Updating

### Update PyPI Installation

```bash
pip install --upgrade dazzle-dsl
```

### Update Source Installation

```bash
cd dazzle
git pull
pip install -e .
```

### Update Homebrew Installation

```bash
brew update
brew upgrade manwithacat/tap/dazzle
```

## Uninstallation

### Remove PyPI Installation

```bash
pip uninstall dazzle-dsl
```

### Remove Homebrew Installation

```bash
brew uninstall manwithacat/tap/dazzle
```

## Troubleshooting

### Python Version Issues

If you have multiple Python versions:

```bash
# Use specific Python version
python3.12 -m pip install dazzle-dsl

# Or create a virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install dazzle-dsl
```

### Permission Errors

If you get permission errors:

```bash
# Install to user directory
pip install --user dazzle-dsl

# Or use a virtual environment (recommended)
python -m venv venv
source venv/bin/activate
pip install dazzle-dsl
```

### Command Not Found

If `dazzle` command is not found after installation:

```bash
# Check if pip bin directory is in PATH
python -m dazzle.cli --version

# Add pip bin directory to PATH
export PATH="$HOME/.local/bin:$PATH"  # On Linux/macOS
```

### Import Errors

If you get import errors:

```bash
# Reinstall with all dependencies
pip install --force-reinstall dazzle-dsl

# Or install with verbose output to see what's missing
pip install -v dazzle-dsl
```

## Development Installation

For contributing to DAZZLE, see [Contributing Guide](../contributing/dev-setup.md) for detailed setup instructions including:

- Setting up pre-commit hooks
- Installing development dependencies
- Running tests
- Code quality tools

## Platform-Specific Notes

### macOS

```bash
# Install Python 3.12 via Homebrew
brew install python@3.12

# Install DAZZLE
pip3 install dazzle-dsl
```

### Linux (Ubuntu/Debian)

```bash
# Install Python 3.12+
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip

# Install DAZZLE
pip3 install dazzle-dsl
```

### Windows

```powershell
# Install Python 3.12+ from python.org
# Then install DAZZLE
pip install dazzle-dsl
```

## Next Steps

After installation:

1. **Read the Quick Start** in [Documentation](../index.md)
2. **Try the Examples** in `examples/`
3. **Set Up IDE Integration** (LSP server: `dazzle lsp run`)
4. **Join the Community** on GitHub Discussions

## Getting Help

- **Installation Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
- **Questions**: [GitHub Discussions](https://github.com/manwithacat/dazzle/discussions)
- **Documentation**: [Developer Docs](../index.md)
