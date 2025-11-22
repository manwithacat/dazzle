# DAZZLE v0.1.0 Release Checklist

Complete checklist for preparing and publishing the first DAZZLE release.

---

## Pre-Release

### Code Quality
- [ ] All tests pass: `pytest tests/`
- [ ] Linting clean: `flake8 src/`
- [ ] Type checking: `mypy src/`
- [ ] No critical TODOs in code
- [ ] Documentation up to date

### Version Management
- [ ] Update `pyproject.toml` version to `0.1.0`
- [ ] Update `src/dazzle/__init__.py` version to `0.1.0`
- [ ] Update CHANGELOG.md with release notes
- [ ] Update README.md (if needed)

### Testing
- [ ] Manual testing complete (see TESTING_GUIDE.md)
- [ ] Homebrew formula tested locally
- [ ] VS Code extension tested with Homebrew install
- [ ] Django backend builds successfully
- [ ] Example projects work

---

## Release Preparation

### Step 1: Run Release Script

```bash
./scripts/prepare-release.sh 0.1.0
```

This automatically:
- Updates versions
- Creates tarball
- Calculates SHA256
- Updates Homebrew formula
- Creates CHANGELOG template
- Commits changes
- Creates git tag

### Step 2: Review Changes

```bash
# Review commit
git show HEAD

# Review formula
cat homebrew/dazzle.rb

# Review CHANGELOG
cat CHANGELOG.md
```

### Step 3: Edit CHANGELOG

Edit `CHANGELOG.md` and fill in:

```markdown
## [v0.1.0] - 2025-11-22

### Added
- Initial release of DAZZLE
- DSL parser and validator
- Django micro-modular backend generator
- CLI tool (dazzle)
- VS Code extension with LSP support
- LLM-assisted spec analysis (Claude, OpenAI)
- Interactive state machine visualizer
- CRUD coverage analysis
- Homebrew distribution

### Features
- Entity and surface definition DSL
- Automatic Django model generation
- Django views and templates generation
- State machine support
- Business rules documentation
- Spec analysis with coverage metrics

### Documentation
- Complete README
- API documentation
- Homebrew installation guide
- VS Code extension guide
- LLM integration guide
```

### Step 4: Amend Commit (if needed)

```bash
git add CHANGELOG.md
git commit --amend
```

---

## Release Publication

### Step 5: Push to GitHub

```bash
# Push main branch
git push origin main

# Push tag
git push origin v0.1.0
```

### Step 6: Create GitHub Release

1. Go to: https://github.com/manwithacat/dazzle/releases/new?tag=v0.1.0

2. Fill in:
   - **Tag**: v0.1.0
   - **Title**: DAZZLE v0.1.0 - Initial Release
   - **Description**: Copy from CHANGELOG.md

3. Upload files:
   - [ ] Upload `/tmp/dazzle-0.1.0.tar.gz`

4. Options:
   - [ ] Check "Set as latest release"
   - [ ] Uncheck "Set as pre-release"

5. Click "Publish release"

### Step 7: Verify Release

```bash
# Download tarball
wget https://github.com/manwithacat/dazzle/archive/refs/tags/v0.1.0.tar.gz

# Verify it downloaded
ls -lh v0.1.0.tar.gz

# Calculate SHA256
shasum -a 256 v0.1.0.tar.gz

# Compare with expected SHA256 from prepare-release script
# They should match!
```

---

## Homebrew Formula Update

### Step 8: Update Formula with Real SHA256

Edit `homebrew/dazzle.rb`:

```ruby
url "https://github.com/manwithacat/dazzle/archive/refs/tags/v0.1.0.tar.gz"
sha256 "REAL_SHA256_FROM_STEP_7"  # Replace TODO with actual hash
```

Commit:
```bash
git add homebrew/dazzle.rb
git commit -m "Update formula with release SHA256"
git push origin main
```

### Step 9: Test Production Formula

```bash
# Test installation from real tarball
brew install --verbose ./homebrew/dazzle.rb

# Run all tests from TESTING_GUIDE.md
# Everything should work

# Uninstall after testing
brew uninstall dazzle
```

---

## Homebrew Tap Publication

### Step 10: Create Homebrew Tap Repository

1. Create repository: https://github.com/manwithacat/homebrew-tap

2. Clone locally:
   ```bash
   cd ~/Projects  # or your preferred location
   git clone https://github.com/manwithacat/homebrew-tap.git
   cd homebrew-tap
   ```

3. Create Formula directory:
   ```bash
   mkdir -p Formula
   ```

4. Copy formula:
   ```bash
   cp /Volumes/SSD/Dazzle/homebrew/dazzle.rb Formula/
   ```

5. Create README:
   ```bash
   cat > README.md << 'EOF'
# DAZZLE Homebrew Tap

Homebrew tap for DAZZLE - DSL-first application framework.

## Installation

```bash
brew tap manwithacat/tap
brew install dazzle
```

## Documentation

See https://github.com/manwithacat/dazzle
EOF
   ```

6. Commit and push:
   ```bash
   git add .
   git commit -m "Add dazzle formula v0.1.0"
   git push origin main
   ```

### Step 11: Test Tap Installation

```bash
# Add tap
brew tap manwithacat/tap

# Verify tap added
brew tap

# Install from tap
brew install manwithacat/tap/dazzle

# Test (run all tests from TESTING_GUIDE.md)
dazzle --version

# Uninstall
brew uninstall dazzle
brew untap manwithacat/tap
```

---

## VS Code Extension Update

### Step 12: Update Extension

1. Update `extensions/vscode/package.json`:
   - [ ] Version → `0.4.1` (or appropriate version)
   - [ ] Update changelog

2. Test extension:
   ```bash
   cd extensions/vscode
   npm install
   npm run compile
   ```

3. Package extension:
   ```bash
   npm run package
   # Creates: dazzle-dsl-0.4.1.vsix
   ```

### Step 13: Publish Extension (Optional)

If publishing to VS Code Marketplace:

```bash
# Login (first time only)
npx vsce login manwithacat

# Publish
npx vsce publish
```

Or publish manually:
1. Go to: https://marketplace.visualstudio.com/manage
2. Upload `.vsix` file

---

## Documentation Update

### Step 14: Update Main README

Update `README.md` with installation instructions:

```markdown
## Installation

### Homebrew (macOS/Linux)

```bash
brew tap manwithacat/tap
brew install dazzle
```

### pip (All platforms)

```bash
pip install dazzle
```

### Verify Installation

```bash
dazzle --version
```
```

### Step 15: Update Documentation

- [ ] Update installation docs
- [ ] Update quick start guide
- [ ] Add release notes
- [ ] Update screenshots (if needed)

---

## Announcement

### Step 16: Prepare Announcement

Draft announcement post:

```
🎉 DAZZLE v0.1.0 Released!

We're excited to announce the first release of DAZZLE - a DSL-first application framework with LLM-assisted development.

🚀 Key Features:
- Declarative DSL for defining applications
- Automatic Django code generation
- LLM-powered spec analysis
- VS Code extension with LSP support
- Interactive visualization dashboard

📦 Installation:
brew tap manwithacat/tap
brew install dazzle

📖 Documentation:
https://github.com/manwithacat/dazzle

Try it out and let us know what you think!
```

### Step 17: Announce Release

Post to:
- [ ] GitHub Discussions
- [ ] Twitter/X
- [ ] Reddit (r/django, r/Python)
- [ ] Hacker News (Show HN)
- [ ] Dev.to
- [ ] LinkedIn
- [ ] Discord/Slack communities

---

## Post-Release

### Step 18: Monitor

Watch for:
- [ ] GitHub release downloads
- [ ] GitHub issues
- [ ] Homebrew install errors
- [ ] User feedback
- [ ] Bug reports

### Step 19: Update Metrics

Track:
- Downloads (GitHub releases)
- Homebrew installs (via analytics)
- VS Code extension installs
- GitHub stars/forks
- Issue reports

### Step 20: Plan Next Release

Create milestone for v0.2.0:
- [ ] List new features
- [ ] List bug fixes
- [ ] Set target date
- [ ] Create roadmap

---

## Rollback Plan

If critical issues found after release:

### Option 1: Patch Release

1. Fix critical issues
2. Release v0.1.1
3. Update Homebrew formula
4. Announce fix

### Option 2: Deprecate Release

1. Mark release as deprecated on GitHub
2. Remove from Homebrew tap (or add deprecation warning)
3. Work on v0.2.0 with fixes

---

## Success Criteria

Release is successful if:

- [x] GitHub release published
- [x] Tarball downloadable
- [x] Homebrew tap published
- [x] Formula installs without errors
- [ ] < 10% error rate in first week
- [ ] > 50 downloads in first week
- [ ] No critical bugs reported
- [ ] Positive user feedback

---

## Sign-off

**Release Manager**: ___________________
**Date**: ___________________
**Release**: v0.1.0
**Status**: ✅ COMPLETE

**Issues Encountered**:
_____________________________________
_____________________________________

**Notes**:
_____________________________________
_____________________________________

---

**Next Steps**: Monitor adoption, gather feedback, plan v0.2.0
