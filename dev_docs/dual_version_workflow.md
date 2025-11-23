# Dual-Version Development Workflow

This guide explains how to manage both the **editable development version** and **homebrew installation** of Dazzle without conflicts.

## Current Setup

### Development Environment (pyenv virtualenv)
- **Virtualenv**: `dazzle-dev` (Python 3.12.11)
- **Location**: `/Volumes/SSD/Dazzle`
- **Installation**: Editable (`pip install -e`)
- **Auto-activation**: `.python-version` file triggers automatic activation when you `cd` into the project directory

### Path Precedence
```
1. ~/.pyenv/shims/dazzle          ← Development version (highest priority)
2. /opt/homebrew/bin/dazzle       ← Homebrew version
3. Other system paths
```

**Key insight**: pyenv always takes precedence, so the development version will be used by default when the virtualenv is active.

## Daily Development Workflow

### Working on Dazzle Code

```bash
# Navigate to project - auto-activates dazzle-dev virtualenv
cd /Volumes/SSD/Dazzle

# Verify you're using dev version
pyenv version
# Should show: dazzle-dev (set by /Volumes/SSD/Dazzle/.python-version)

# Make changes to code...
vim src/dazzle/cli.py

# Test immediately (no reinstall needed - editable install!)
dazzle --version
dazzle validate
dazzle build --stack openapi

# Commit changes
git add .
git commit -m "feat: add new feature"
```

### Testing Outside Project Directory

```bash
# Outside the project, pyenv uses system Python
cd ~

# Check current Python
pyenv version
# Should show: 3.12.11 (set by /Users/james/.pyenv/version) or similar

# If you have homebrew dazzle installed, it will be used here
# If not, dazzle won't be available (which is expected)
```

## Homebrew Testing Workflow

### Testing the Homebrew Formula

When you need to test the homebrew installation (e.g., before pushing to the tap):

```bash
# 1. Navigate away from the project directory (deactivate virtualenv)
cd ~

# 2. Install from your local formula
brew uninstall dazzle 2>/dev/null  # Remove any existing homebrew install
brew install --build-from-source ~/path/to/Dazzle/homebrew/dazzle.rb

# Or if you have a tap:
brew install your-tap/dazzle

# 3. Test the homebrew installation
/opt/homebrew/bin/dazzle --version
/opt/homebrew/bin/dazzle validate

# 4. When done testing, remove it to avoid confusion
brew uninstall dazzle

# 5. Return to development
cd /Volumes/SSD/Dazzle  # Auto-activates dazzle-dev again
```

### Alternative: Force Test Homebrew Version While In Project

If you need to quickly test the homebrew version without leaving the project:

```bash
# Temporarily disable pyenv for one command
PATH="/opt/homebrew/bin:$PATH" /opt/homebrew/bin/dazzle --version

# Or create an alias in ~/.zshrc:
alias dazzle-brew='/opt/homebrew/bin/dazzle'
alias dazzle-dev='~/.pyenv/shims/dazzle'

# Then use:
dazzle-brew --version   # Tests homebrew version
dazzle-dev --version    # Tests dev version
```

## Updating the Homebrew Formula

When you make changes and want to update the homebrew formula:

```bash
# 1. Update version in pyproject.toml
vim pyproject.toml

# 2. Tag the release
git tag v0.1.1
git push origin v0.1.1

# 3. Update homebrew formula
cd homebrew/
# Update version and sha256 in dazzle.rb

# 4. Test the formula locally
cd ~
brew uninstall dazzle 2>/dev/null
brew install --build-from-source /Volumes/SSD/Dazzle/homebrew/dazzle.rb
/opt/homebrew/bin/dazzle --version

# 5. If tests pass, push to tap
cd /path/to/homebrew-tap
cp /Volumes/SSD/Dazzle/homebrew/dazzle.rb Formula/
git add Formula/dazzle.rb
git commit -m "dazzle: update to 0.1.1"
git push
```

## Quick Diagnostics

If you're confused about which version is active:

```bash
# Full diagnostic
echo "=== Python Version ==="
pyenv version

echo -e "\n=== Which Dazzle ==="
which dazzle

echo -e "\n=== Dazzle Version ==="
dazzle --version

echo -e "\n=== All Dazzle Executables ==="
which -a dazzle

echo -e "\n=== Pip Show ==="
pip show dazzle
```

Save this as an alias in `~/.zshrc`:

```bash
alias dazzle-check='echo "=== Python Version ===" && pyenv version && echo -e "\n=== Which Dazzle ===" && which dazzle && echo -e "\n=== Dazzle Version ===" && dazzle --version'
```

## Troubleshooting

### "Command not found: dazzle" outside project

**Expected behavior**. The `dazzle-dev` virtualenv is only active inside `/Volumes/SSD/Dazzle`.

**Solution**: If you want dazzle available globally, install via homebrew or install it in your global Python environment.

### Changes not taking effect

If you modify code but don't see changes:

```bash
# Check you're in the virtualenv
pyenv version

# Verify editable install
pip show dazzle | grep "Editable project location"
# Should show: Editable project location: /Volumes/SSD/Dazzle

# If not editable, reinstall:
pip install -e '/Volumes/SSD/Dazzle[llm]'
```

### Homebrew version being used in project

If `which dazzle` shows `/opt/homebrew/bin/dazzle` even in the project directory:

```bash
# Check if virtualenv is active
pyenv version

# Check if .python-version exists
cat .python-version
# Should show: dazzle-dev

# Manually activate if needed
pyenv activate dazzle-dev
```

### Want to temporarily disable dev version

```bash
# Option 1: Deactivate virtualenv
pyenv deactivate

# Option 2: Use system Python temporarily
PYENV_VERSION=system dazzle --version

# Option 3: Use homebrew directly
/opt/homebrew/bin/dazzle --version
```

## Virtualenv Management

### Recreate virtualenv from scratch

```bash
# Delete existing virtualenv
pyenv uninstall dazzle-dev

# Recreate
pyenv virtualenv 3.12.11 dazzle-dev
PYENV_VERSION=dazzle-dev pip install -e '/Volumes/SSD/Dazzle[llm]'
PYENV_VERSION=dazzle-dev pip install pygls  # For LSP support

# .python-version file will auto-activate it in the project directory
```

### Install additional dependencies

```bash
# Must activate virtualenv first
cd /Volumes/SSD/Dazzle  # Auto-activates

# Or manually:
PYENV_VERSION=dazzle-dev pip install some-package

# Or if already in project directory:
pip install some-package
```

### List all virtualenvs

```bash
pyenv virtualenvs
```

## Summary

- **In project directory** (`/Volumes/SSD/Dazzle`): Always uses `dazzle-dev` virtualenv (editable install)
- **Outside project**: Uses system Python (no dazzle unless installed globally via homebrew)
- **Testing homebrew**: Temporarily leave project directory or use `/opt/homebrew/bin/dazzle` directly
- **Changes take effect immediately**: Editable install means no reinstall needed
- **No containers needed**: pyenv virtualenvs provide clean isolation

## Quick Reference Commands

```bash
# Check which version you're using
pyenv version && which dazzle

# Switch to dev version (if not already)
cd /Volumes/SSD/Dazzle

# Test homebrew version
cd ~ && /opt/homebrew/bin/dazzle --version

# Reinstall dev version with all extras
PYENV_VERSION=dazzle-dev pip install -e '/Volumes/SSD/Dazzle[llm]' && PYENV_VERSION=dazzle-dev pip install pygls
```
