# Installation Guide

This guide covers multiple ways to install DAZZLE on your system.

## Prerequisites

- **Python 3.11 or higher** (Python 3.12 recommended)
- **pip** (usually comes with Python)
- **git** (for installation from source)

## Installation Methods

### Method 1: Install from PyPI (Recommended)

Once DAZZLE is published to PyPI, you can install it with:

```bash
pip install dazzle
```

To install with LLM support (for DSL generation features):

```bash
pip install dazzle[llm]
```

To install for development:

```bash
pip install dazzle[dev]
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

### Method 3: Homebrew (Coming Soon)

Homebrew installation will be available in a future release:

```bash
# Future command (not yet available)
brew install dazzle
```

#### Creating a Homebrew Formula (For Maintainers)

To publish DAZZLE to Homebrew in the future:

1. **Create a GitHub Release**:
   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin v0.1.0
   ```

2. **Build Source Distribution**:
   ```bash
   python -m build --sdist
   ```

3. **Calculate SHA256**:
   ```bash
   shasum -a 256 dist/dazzle-0.1.0.tar.gz
   ```

4. **Create Homebrew Formula** (`Formula/dazzle.rb`):
   ```ruby
   class Dazzle < Formula
     desc "Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps"
     homepage "https://github.com/manwithacat/dazzle"
     url "https://github.com/manwithacat/dazzle/archive/v0.1.0.tar.gz"
     sha256 "YOUR_SHA256_HERE"
     license "MIT"

     depends_on "python@3.11"

     def install
       virtualenv_install_with_resources
     end

     test do
       system "#{bin}/dazzle", "--version"
     end
   end
   ```

5. **Publish to Homebrew Tap**:
   ```bash
   # Create tap repository
   gh repo create manwithacat/homebrew-dazzle --public

   # Add formula
   cp Formula/dazzle.rb ../homebrew-dazzle/Formula/
   cd ../homebrew-dazzle
   git add Formula/dazzle.rb
   git commit -m "Add dazzle formula"
   git push
   ```

6. **Install from Tap**:
   ```bash
   brew tap manwithacat/dazzle
   brew install dazzle
   ```

### Method 4: Using pipx (Isolated Environment)

To install DAZZLE in an isolated environment:

```bash
# Install pipx if you don't have it
python -m pip install --user pipx
python -m pipx ensurepath

# Install DAZZLE
pipx install dazzle

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

# Get help
dazzle --help

# Run a quick validation (if you have a DSL file)
dazzle validate
```

## Updating

### Update PyPI Installation

```bash
pip install --upgrade dazzle
```

### Update Source Installation

```bash
cd dazzle
git pull
pip install -e .
```

### Update Homebrew Installation (Future)

```bash
brew update
brew upgrade dazzle
```

## Uninstallation

### Remove PyPI Installation

```bash
pip uninstall dazzle
```

### Remove Homebrew Installation (Future)

```bash
brew uninstall dazzle
```

## Troubleshooting

### Python Version Issues

If you have multiple Python versions:

```bash
# Use specific Python version
python3.11 -m pip install dazzle

# Or create a virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install dazzle
```

### Permission Errors

If you get permission errors:

```bash
# Install to user directory
pip install --user dazzle

# Or use a virtual environment (recommended)
python -m venv venv
source venv/bin/activate
pip install dazzle
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
pip install --force-reinstall dazzle

# Or install with verbose output to see what's missing
pip install -v dazzle
```

## Development Installation

For contributing to DAZZLE, see [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed setup instructions including:

- Setting up pre-commit hooks
- Installing development dependencies
- Running tests
- Code quality tools

## Platform-Specific Notes

### macOS

```bash
# Install Python 3.11+ via Homebrew
brew install python@3.11

# Install DAZZLE
pip3.11 install dazzle
```

### Linux (Ubuntu/Debian)

```bash
# Install Python 3.11+
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# Install DAZZLE
pip3 install dazzle
```

### Windows

```powershell
# Install Python 3.11+ from python.org
# Then install DAZZLE
pip install dazzle
```

## Next Steps

After installation:

1. **Read the Quick Start** in [README.md](../README.md)
2. **Try the Examples** in `examples/`
3. **Set Up IDE Integration** (VSCode extension)
4. **Join the Community** on GitHub Discussions

## Getting Help

- **Installation Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
- **Questions**: [GitHub Discussions](https://github.com/manwithacat/dazzle/discussions)
- **Documentation**: [docs/](./README.md)
