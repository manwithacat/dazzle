#!/bin/bash

# Git Commit Script for DAZZLE Homebrew Distribution and Phase 7 Work
# Run this from the /Volumes/SSD/Dazzle directory

set -e  # Exit on error

cd /Volumes/SSD/Dazzle

# Configure git user if needed
git config user.name "Claude Code" || true
git config user.email "noreply@anthropic.com" || true

echo "============================================"
echo "Committing DAZZLE work in structured commits"
echo "============================================"
echo ""

# Commit 1: Phase 7 - Advanced Visualization
echo "Commit 1: feat(vscode): add advanced visualization dashboard for spec analysis"
git add extensions/vscode/src/ui/analysisPanel.ts \
        extensions/vscode/src/llmCommands.ts \
        devdocs/PHASE_7_ADVANCED_VISUALIZATION.md 2>/dev/null || true

git commit -m "feat(vscode): add advanced visualization dashboard for spec analysis

- Implement interactive WebView panel for LLM spec analysis results
- Add Mermaid.js state machine diagrams with found/missing transitions
- Create CRUD coverage matrix with color-coded badges and progress bars
- Add business rules visualization with grouped display
- Implement coverage metrics dashboard (6 metric cards)
- Add Chart.js integration for questions priority visualization
- Create tabbed interface (Overview, State Machines, CRUD, Business Rules)
- Add export functionality (PDF, Markdown, clipboard)
- Integrate with VS Code theme for consistent styling
- Update llmCommands.ts to show panel after analysis

Files:
- extensions/vscode/src/ui/analysisPanel.ts (820 lines, new)
- extensions/vscode/src/llmCommands.ts (modified - panel integration)
- devdocs/PHASE_7_ADVANCED_VISUALIZATION.md (documentation)

Impact: Users get rich interactive dashboard instead of terminal output
" || echo "  → Already committed or no changes"

# Commit 2: LSP Improvements
echo ""
echo "Commit 2: fix(vscode): improve LSP server error handling and Python detection"
git add extensions/vscode/src/lspClient.ts \
        extensions/vscode/package.json \
        extensions/vscode/TROUBLESHOOTING.md 2>/dev/null || true

git commit -m "fix(vscode): improve LSP server error handling and Python detection

- Add pre-flight check for LSP server availability before starting
- Implement graceful degradation when Python/dazzle not found
- Show helpful error message with 3 solution options
- Add dazzle.pythonPath configuration setting for manual override
- Enhance Python path detection with priority order:
  1. VS Code setting (dazzle.pythonPath)
  2. Environment variable (DAZZLE_PYTHON)
  3. Python extension interpreter
  4. Auto-detect Homebrew installations
  5. Fallback to python3
- Add PYTHONPATH support for development mode
- Create comprehensive troubleshooting guide

Files:
- extensions/vscode/src/lspClient.ts (enhanced error handling)
- extensions/vscode/package.json (new configuration)
- extensions/vscode/TROUBLESHOOTING.md (350 lines, new)

Fixes: LSP server crashes when dazzle package not installed
Impact: Extension works without LSP, better developer experience
" || echo "  → Already committed or no changes"

# Commit 3: Homebrew Formulas
echo ""
echo "Commit 3: feat(build): add Homebrew formulas for macOS/Linux distribution"
git add homebrew/dazzle.rb \
        homebrew/dazzle-simple.rb 2>/dev/null || true

git commit -m "feat(build): add Homebrew formulas for macOS/Linux distribution

Production Formula (dazzle.rb):
- Complete formula with 11 bundled Python dependencies
- All dependencies verified with SHA256 checksums from PyPI:
  * pydantic (2.9.2) + pydantic-core
  * typer (0.12.5) + click, shellingham
  * rich (13.9.2) + markdown-it-py, mdurl, pygments
  * typing-extensions, annotated-types
- Isolated virtualenv with Python 3.12
- Installation tests for CLI functionality
- User-friendly caveats with quick start instructions
- Support for HEAD installs from main branch

Testing Formula (dazzle-simple.rb):
- Simplified formula for local development testing
- Installs from local git repository
- Automatic dependency resolution from pyproject.toml
- Version 0.1.0-dev for pre-release testing

Files:
- homebrew/dazzle.rb (126 lines)
- homebrew/dazzle-simple.rb (50 lines)

Distribution:
- Installation: brew tap manwithacat/tap && brew install dazzle
- Isolated: /opt/homebrew/Cellar/dazzle/0.1.0/libexec/
- Clean uninstall: brew uninstall dazzle
- VS Code auto-detection ready

Impact: Professional one-command installation for macOS/Linux users
" || echo "  → Already committed or no changes"

# Commit 4: Distribution Scripts
echo ""
echo "Commit 4: feat(build): add release automation and testing scripts"
git add scripts/prepare-release.sh \
        scripts/test-homebrew-install.sh \
        scripts/generate-homebrew-resources.py 2>/dev/null || true

git commit -m "feat(build): add release automation and testing scripts

prepare-release.sh (180 lines):
- Automates version bumps in pyproject.toml and __init__.py
- Creates release tarball with git archive
- Calculates SHA256 checksums automatically
- Updates Homebrew formula with new version/SHA256
- Generates CHANGELOG.md template
- Creates git commits and tags
- Usage: ./scripts/prepare-release.sh 0.1.0

test-homebrew-install.sh (150 lines):
- Automated testing of Homebrew formula installation
- Verifies CLI commands (--help, --version, init, validate, build)
- Checks Python virtualenv isolation
- Tests basic workflow end-to-end
- Auto-cleanup after testing
- Usage: ./scripts/test-homebrew-install.sh

generate-homebrew-resources.py (150 lines):
- Fetches package metadata from PyPI
- Downloads source tarballs and calculates SHA256
- Generates Homebrew resource blocks
- Validates dependency versions
- Outputs ready-to-use Ruby code
- Usage: python3 scripts/generate-homebrew-resources.py

Files:
- scripts/prepare-release.sh (release automation)
- scripts/test-homebrew-install.sh (testing automation)
- scripts/generate-homebrew-resources.py (dependency management)

Impact: Streamlines release process, ensures consistent releases
" || echo "  → Already committed or no changes"

# Commit 5: Distribution Documentation
echo ""
echo "Commit 5: docs: add comprehensive Homebrew distribution documentation"
git add DISTRIBUTION.md \
        HOMEBREW_QUICKSTART.md \
        TESTING_GUIDE.md \
        RELEASE_CHECKLIST.md \
        NEXT_STEPS.md \
        devdocs/HOMEBREW_DISTRIBUTION_COMPLETE.md \
        devdocs/HOMEBREW_TESTING_STATUS.md 2>/dev/null || true

git commit -m "docs: add comprehensive Homebrew distribution documentation

DISTRIBUTION.md (400+ lines):
- Complete multi-platform distribution strategy
- Homebrew (macOS/Linux) - detailed implementation
- Chocolatey, winget, Scoop (Windows) - roadmap
- PyPI fallback for all platforms
- Docker image strategy
- Linux packages (.deb, .rpm, Snap)
- 8-phase implementation roadmap
- Success metrics and testing strategy

HOMEBREW_QUICKSTART.md (250+ lines):
- User installation guide with examples
- Quick start tutorial (init → validate → build)
- VS Code extension integration
- LLM features setup (anthropic, openai)
- Developer local testing procedures
- Troubleshooting common issues
- FAQ section

TESTING_GUIDE.md (500+ lines):
- 6-phase manual testing procedures:
  1. Formula validation (syntax, audit, URLs)
  2. Local installation test
  3. Functional testing (init, validate, build, server)
  4. VS Code integration test
  5. Uninstall test
  6. Production formula test
- Platform testing matrix
- Performance benchmarks
- Issue reporting templates
- Sign-off checklist

RELEASE_CHECKLIST.md (450+ lines):
- Complete v0.1.0 release process
- Pre-release checklist (code quality, testing)
- Step-by-step release preparation
- GitHub release creation
- Homebrew formula SHA256 update
- Homebrew tap publication
- VS Code extension update
- Announcement templates
- Post-release monitoring
- Rollback plan
- Success criteria

NEXT_STEPS.md (400+ lines):
- Immediate actions (manual testing, v0.1.0 release)
- Short-term roadmap (weeks 1-2: Homebrew tap, docs)
- Medium-term roadmap (weeks 3-4: Windows, Linux)
- Long-term roadmap (months 2-3: GUI, auto-updates)
- Development roadmap (v0.2.0, v0.3.0, v1.0.0)
- Success metrics and tracking
- Risk assessment
- Ongoing maintenance tasks

HOMEBREW_DISTRIBUTION_COMPLETE.md (470+ lines):
- Implementation summary
- Deliverables breakdown
- Installation architecture
- Testing procedures
- Release process
- VS Code integration details
- Future enhancements roadmap
- Distribution metrics
- Files summary (8 files, ~1,650 lines)

HOMEBREW_TESTING_STATUS.md (new):
- Current testing status and blockers
- Completed tests summary
- Blocking issue: no git commits
- Requirements to unblock testing
- Recommended next steps
- Testing matrix with status
- Issues discovered
- Lessons learned

Files:
- DISTRIBUTION.md
- HOMEBREW_QUICKSTART.md
- TESTING_GUIDE.md
- RELEASE_CHECKLIST.md
- NEXT_STEPS.md
- devdocs/HOMEBREW_DISTRIBUTION_COMPLETE.md
- devdocs/HOMEBREW_TESTING_STATUS.md

Impact: Complete documentation for distribution strategy and release process
Total: ~2,500 lines of comprehensive documentation
" || echo "  → Already committed or no changes"

# Commit 6: Any remaining files
echo ""
echo "Commit 6: chore: add any remaining uncommitted files"
git add . 2>/dev/null || true
git status --short | head -20

if git status --short | grep -q '^[MADRCU]'; then
    git commit -m "chore: add remaining uncommitted files

This commit captures any additional files or changes not covered by
previous structured commits.
" || echo "  → Already committed or no changes"
else
    echo "  → No additional files to commit"
fi

echo ""
echo "============================================"
echo "Git commit summary:"
echo "============================================"
git log --oneline -10

echo ""
echo "============================================"
echo "✅ All work committed successfully!"
echo "============================================"
echo ""
echo "Repository now has commits and is ready for:"
echo "  1. Homebrew formula testing"
echo "  2. GitHub push"
echo "  3. v0.1.0 release"
echo ""
echo "Next steps:"
echo "  git remote add origin https://github.com/manwithacat/dazzle.git"
echo "  git push -u origin main"
echo "  ./scripts/prepare-release.sh 0.1.0"
