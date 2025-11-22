# DAZZLE Homebrew Installation - Quick Start

## Overview

DAZZLE is distributed via Homebrew for easy, isolated installation on macOS and Linux.

---

## For Users

### Installation

```bash
# Install from Homebrew tap (when published)
brew tap manwithacat/tap
brew install dazzle

# Or install directly from formula
brew install manwithacat/tap/dazzle
```

### Verification

```bash
# Check installation
which dazzle
# → /opt/homebrew/bin/dazzle

# Check version
dazzle --version
# → DAZZLE 0.1.0

# Get help
dazzle --help
```

### Quick Start

```bash
# Create new project
dazzle init my-app
cd my-app

# Build application
dazzle build

# Run Django server
cd build/my-app
python manage.py runserver
```

### VS Code Integration

The VS Code extension automatically detects Homebrew installations:

```bash
# Install extension
code --install-extension dazzle.dazzle-dsl

# Extension automatically finds:
# /opt/homebrew/opt/dazzle/libexec/bin/python
```

### Adding LLM Support

```bash
# Install LLM dependencies (Anthropic, OpenAI)
$(brew --prefix dazzle)/libexec/bin/pip install anthropic openai

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Use LLM features
dazzle analyze-spec SPEC.md
```

### Updating

```bash
# Update to latest version
brew update
brew upgrade dazzle
```

### Uninstalling

```bash
# Remove DAZZLE
brew uninstall dazzle
```

---

## For Developers

### Local Testing

Test the formula before publishing:

```bash
# Test local formula
./scripts/test-homebrew-install.sh

# Or manually:
brew install --build-from-source ./homebrew/dazzle.rb

# Verify
dazzle --version
```

### Preparing a Release

```bash
# Prepare release (updates versions, creates tarball, calculates SHA256)
./scripts/prepare-release.sh 0.1.0

# Follow the prompts to:
# 1. Review CHANGELOG
# 2. Push to GitHub
# 3. Create GitHub release
# 4. Update Homebrew tap
```

### Release Checklist

- [ ] Update version in `pyproject.toml`
- [ ] Update version in `src/dazzle/__init__.py`
- [ ] Update CHANGELOG.md
- [ ] Run tests: `pytest`
- [ ] Build package: `python -m build`
- [ ] Create git tag: `git tag v0.1.0`
- [ ] Push tag: `git push origin v0.1.0`
- [ ] Create GitHub release
- [ ] Upload tarball to GitHub release
- [ ] Calculate SHA256: `shasum -a 256 dazzle-0.1.0.tar.gz`
- [ ] Update `homebrew/dazzle.rb` with URL and SHA256
- [ ] Test formula: `./scripts/test-homebrew-install.sh`
- [ ] Push to homebrew-tap repo (if separate)
- [ ] Announce release

### Formula Structure

```
homebrew/dazzle.rb
├── Metadata (name, desc, homepage, url, sha256)
├── Dependencies (python@3.12)
├── Resources (Python packages)
├── Install method (virtualenv_install_with_resources)
├── Caveats (setup instructions)
└── Tests (basic functionality)
```

### Installation Structure

```
/opt/homebrew/Cellar/dazzle/0.1.0/
├── libexec/
│   ├── bin/
│   │   ├── python3          # Isolated Python
│   │   ├── dazzle           # CLI entry point
│   │   └── pip              # pip for this virtualenv
│   └── lib/python3.12/
│       └── site-packages/
│           ├── dazzle/       # DAZZLE package
│           ├── typer/        # Dependencies
│           ├── pydantic/
│           └── ...
└── bin/dazzle -> ../libexec/bin/dazzle

/opt/homebrew/bin/dazzle -> ../Cellar/dazzle/0.1.0/bin/dazzle
```

---

## Troubleshooting

### Formula Not Found

```bash
# Update Homebrew
brew update

# Check tap
brew tap

# Add tap if missing
brew tap manwithacat/tap
```

### Installation Failed

```bash
# Clean and retry
brew cleanup
brew uninstall dazzle
brew install --build-from-source dazzle

# Check logs
brew gist-logs dazzle
```

### Python Module Not Found

```bash
# Check Python location
brew --prefix dazzle
ls -la $(brew --prefix dazzle)/libexec/bin/python

# Verify dazzle module
$(brew --prefix dazzle)/libexec/bin/python -c "import dazzle; print(dazzle.__version__)"
```

### VS Code Extension Can't Find DAZZLE

Set Python path manually in VS Code settings:

```json
{
  "dazzle.pythonPath": "/opt/homebrew/opt/dazzle/libexec/bin/python"
}
```

---

## FAQ

**Q: Why Homebrew?**
A: Isolated installation, no system Python pollution, easy updates, standard macOS UX.

**Q: Can I use pip instead?**
A: Yes! `pip install dazzle` works, but Homebrew is recommended for cleaner isolation.

**Q: Where are files installed?**
A: `/opt/homebrew/Cellar/dazzle/VERSION/` (Apple Silicon) or `/usr/local/Cellar/dazzle/VERSION/` (Intel).

**Q: How do I install LLM dependencies?**
A: `$(brew --prefix dazzle)/libexec/bin/pip install anthropic openai`

**Q: Can I install from source?**
A: Yes! `brew install --build-from-source dazzle`

**Q: How do I report issues?**
A: https://github.com/manwithacat/dazzle/issues

---

## Links

- **GitHub**: https://github.com/manwithacat/dazzle
- **Homebrew Tap**: https://github.com/manwithacat/homebrew-tap
- **Documentation**: https://github.com/manwithacat/dazzle/blob/main/README.md
- **Issues**: https://github.com/manwithacat/dazzle/issues

---

**Last Updated**: November 22, 2025
