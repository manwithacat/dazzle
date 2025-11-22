# DAZZLE Homebrew - Manual Testing Guide

Complete manual testing procedures for validating the Homebrew formula before release.

---

## Prerequisites

- macOS (Intel or Apple Silicon)
- Homebrew installed (`brew --version`)
- Git installed
- Internet connection (for downloading dependencies)

---

## Phase 1: Formula Validation

### Step 1.1: Syntax Check

```bash
cd /Volumes/SSD/Dazzle

# Validate Ruby syntax
brew ruby -e "load './homebrew/dazzle.rb'"
# Should complete without errors

brew ruby -e "load './homebrew/dazzle-simple.rb'"
# Should complete without errors
```

**Expected**: No syntax errors

### Step 1.2: Formula Audit

```bash
# Audit production formula
brew audit --strict homebrew/dazzle.rb

# Expected warnings (acceptable):
# - "No test for v0.1.0" (we'll add after release)
# - "URL not reachable" (tag doesn't exist yet)
```

### Step 1.3: Resource URL Verification

Verify all resource URLs are accessible:

```bash
# Test one resource URL
curl -I "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.9.2.tar.gz"
# Should return: HTTP/2 200
```

**Check all 11 resource URLs** from `homebrew/dazzle.rb`:
- [ ] pydantic
- [ ] pydantic-core
- [ ] typing-extensions
- [ ] annotated-types
- [ ] typer
- [ ] click
- [ ] shellingham
- [ ] rich
- [ ] markdown-it-py
- [ ] mdurl
- [ ] pygments

---

## Phase 2: Local Installation Test

### Step 2.1: Install from Simplified Formula

```bash
cd /Volumes/SSD/Dazzle

# Install simplified formula (from local git)
brew install --verbose ./homebrew/dazzle-simple.rb

# This will:
# - Create virtualenv with Python 3.12
# - Install dazzle from local source
# - Install all dependencies from pyproject.toml
# - Create symlinks in /opt/homebrew/bin/

# Watch for errors during installation
```

**Expected output**:
```
==> Installing dazzle-simple from /Volumes/SSD/Dazzle/homebrew/dazzle-simple.rb
==> Downloading https://github.com/manwithacat/dazzle.git
...
==> Installing dependencies for dazzle-simple: python@3.12
...
==> Installing dazzle-simple
...
🍺  /opt/homebrew/Cellar/dazzle-simple/HEAD-xxxxxxx: XXX files, XXX MB
```

### Step 2.2: Verify Installation

```bash
# Check dazzle is in PATH
which dazzle
# Expected: /opt/homebrew/bin/dazzle

# Check it's a symlink to Cellar
ls -la $(which dazzle)
# Expected: ... -> ../Cellar/dazzle-simple/...

# Check version
dazzle --version
# Expected: DAZZLE 0.1.0 (or current version)

# Check help
dazzle --help
# Expected: Usage information, commands listed
```

### Step 2.3: Verify Python Environment

```bash
# Find installation location
INSTALL_PATH=$(brew --prefix dazzle-simple)
echo $INSTALL_PATH
# Expected: /opt/homebrew/opt/dazzle-simple

# Check Python location
ls -la $INSTALL_PATH/libexec/bin/python
# Expected: Python 3.12.x symlink

# Verify dazzle package is installed
$INSTALL_PATH/libexec/bin/python -c "import dazzle; print(dazzle.__version__)"
# Expected: 0.1.0 (or current version)

# Check all dependencies
$INSTALL_PATH/libexec/bin/python -c "
import pydantic
import typer
import click
import rich
print('✅ All dependencies installed')
"
# Expected: ✅ All dependencies installed
```

---

## Phase 3: Functional Testing

### Step 3.1: Test Basic Workflow

```bash
# Create test directory
cd /tmp
rm -rf dazzle-test
mkdir dazzle-test
cd dazzle-test

# Initialize project
dazzle init my-test-app

# Expected output:
# ✅ Created project directory: my-test-app
# ✅ Created dazzle.toml
# ✅ Created dsl/ directory
# etc.

cd my-test-app
ls -la
# Expected files:
# - dazzle.toml
# - dsl/
# - build/ (maybe)
```

### Step 3.2: Test Validation

```bash
# Create test DSL file
cat > dsl/app.dsl << 'EOF'
module test
app test "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  done: bool = false
  created_at: datetime auto_add
EOF

# Validate
dazzle validate

# Expected output:
# ✅ Validation successful
# (or similar success message)
```

### Step 3.3: Test Build

```bash
# Build project
dazzle build

# Expected:
# - build/ directory created
# - Django project generated
# - No errors

# Verify build output
ls -la build/
# Expected: Django project structure

cd build/my-test-app

# Check Django works
python manage.py check
# Expected: System check identified no issues

# Run migrations
python manage.py migrate
# Expected: Migrations applied successfully
```

### Step 3.4: Test Server

```bash
# Start development server (in background)
python manage.py runserver &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Test HTTP request
curl -I http://localhost:8000
# Expected: HTTP/1.1 200 OK (or 302/301)

# Stop server
kill $SERVER_PID

# Cleanup
cd /tmp
rm -rf dazzle-test
```

---

## Phase 4: VS Code Integration Test

### Step 4.1: Check Python Path

```bash
# Get Python path that VS Code should use
brew --prefix dazzle-simple
# Copy this path and append: /libexec/bin/python

# Example:
# /opt/homebrew/opt/dazzle-simple/libexec/bin/python
```

### Step 4.2: Test VS Code Extension

```bash
# Open VS Code in test project
cd /tmp/dazzle-test/my-test-app
code .

# In VS Code:
# 1. Open dsl/app.dsl
# 2. Check for syntax highlighting
# 3. Check LSP is working (hover for tooltips)
# 4. Check diagnostics panel for errors

# If LSP doesn't work, set manually:
# Settings → "dazzle.pythonPath" → paste path from Step 4.1
```

---

## Phase 5: Uninstall Test

### Step 5.1: Clean Uninstall

```bash
# Uninstall
brew uninstall dazzle-simple

# Verify dazzle command removed
which dazzle
# Expected: (empty - command not found)

# Verify files removed
ls /opt/homebrew/Cellar/ | grep dazzle
# Expected: (empty - no dazzle directories)
```

---

## Phase 6: Production Formula Test

**Note**: Only test this after creating a real GitHub release with tarball

### Step 6.1: Update Formula with Real Values

After creating v0.1.0 release:

1. Download tarball:
   ```bash
   wget https://github.com/manwithacat/dazzle/archive/refs/tags/v0.1.0.tar.gz
   ```

2. Calculate SHA256:
   ```bash
   shasum -a 256 v0.1.0.tar.gz
   # Copy the hash
   ```

3. Update `homebrew/dazzle.rb`:
   - Replace `TODO_CALCULATE_AFTER_RELEASE` with real SHA256
   - Verify URL points to actual release

### Step 6.2: Test Production Formula

```bash
# Install from production formula
brew install --verbose ./homebrew/dazzle.rb

# Run all tests from Phases 2-5
# Everything should work identically
```

---

## Troubleshooting Common Issues

### Issue: "Python not found"

**Symptom**: `dazzle` command not found after install

**Solution**:
```bash
# Check if brew bin is in PATH
echo $PATH | grep homebrew
# Should include /opt/homebrew/bin

# Add to PATH if missing (in ~/.zshrc or ~/.bashrc)
export PATH="/opt/homebrew/bin:$PATH"
source ~/.zshrc
```

### Issue: "Module not found"

**Symptom**: `ImportError: No module named 'pydantic'`

**Solution**:
```bash
# Check virtualenv integrity
brew --prefix dazzle-simple
ls -la $(brew --prefix dazzle-simple)/libexec/lib/python3.12/site-packages/

# Reinstall if needed
brew reinstall dazzle-simple
```

### Issue: "Permission denied"

**Symptom**: Can't install or run dazzle

**Solution**:
```bash
# Fix Homebrew permissions
sudo chown -R $(whoami) /opt/homebrew/*
brew doctor
# Follow any recommendations
```

### Issue: "Build failed"

**Symptom**: Formula installation fails

**Solution**:
```bash
# Check logs
brew gist-logs dazzle-simple

# Clean and retry
brew cleanup
brew install --build-from-source --verbose ./homebrew/dazzle-simple.rb
```

---

## Testing Checklist

Use this checklist to verify all tests pass:

### Formula Validation
- [ ] Ruby syntax valid (brew ruby)
- [ ] Formula audit passes (or acceptable warnings)
- [ ] All resource URLs accessible

### Installation
- [ ] Formula installs without errors
- [ ] `dazzle` command in PATH
- [ ] Python virtualenv created
- [ ] All dependencies installed

### Functionality
- [ ] `dazzle --version` works
- [ ] `dazzle --help` works
- [ ] `dazzle init` creates project
- [ ] `dazzle validate` validates DSL
- [ ] `dazzle build` generates Django app
- [ ] Django migrations work
- [ ] Django server runs

### VS Code Integration
- [ ] Extension detects Homebrew Python
- [ ] LSP server starts
- [ ] Syntax highlighting works
- [ ] Diagnostics work

### Cleanup
- [ ] Uninstall removes all files
- [ ] No leftover directories
- [ ] `dazzle` command removed from PATH

---

## Platform Testing Matrix

| Platform | Tester | Status | Notes |
|----------|--------|--------|-------|
| macOS 14+ (Apple Silicon) | [ ] | ⏳ | Primary platform |
| macOS 14+ (Intel) | [ ] | ⏳ | Secondary |
| macOS 13 (Apple Silicon) | [ ] | ⏳ | Compatibility |
| Linux (Homebrew) | [ ] | ⏳ | Optional |

---

## Performance Benchmarks

Record these metrics during testing:

| Metric | Target | Actual | Pass? |
|--------|--------|--------|-------|
| Install time | < 2 min | | |
| Disk space | < 200 MB | | |
| `dazzle init` time | < 5 sec | | |
| `dazzle validate` time | < 2 sec | | |
| `dazzle build` time | < 30 sec | | |

---

## Reporting Issues

If you find issues during testing:

1. **Collect information**:
   ```bash
   brew --version
   sw_vers  # macOS version
   dazzle --version
   brew --prefix dazzle-simple
   brew gist-logs dazzle-simple
   ```

2. **Create GitHub issue**:
   - Title: "Homebrew: [Brief description]"
   - Label: `distribution`, `homebrew`
   - Include all commands and output
   - Include error messages
   - Include platform details

3. **Fix and retest**:
   - Update formula
   - Increment version
   - Retest all phases

---

## Sign-off

**Tester**: ___________________
**Date**: ___________________
**Platform**: ___________________
**Result**: ✅ PASS / ❌ FAIL

**Notes**:
_____________________________________
_____________________________________
_____________________________________

---

**After successful testing, proceed to**: Release process (v0.1.0)
