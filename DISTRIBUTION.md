# DAZZLE Distribution Strategy

Complete strategy for distributing DAZZLE as a standalone CLI tool across platforms.

---

## Overview

**Goal**: Make DAZZLE installable with a single command on macOS, Linux, and Windows.

**Primary Method**: Homebrew (macOS/Linux), Chocolatey/winget (Windows)
**Secondary**: PyPI (pip install), Docker, Pre-built binaries

---

## Phase 1: Homebrew Formula (macOS/Linux)

### Installation UX

```bash
# Install from Homebrew
brew install dazzle

# Or from our tap
brew tap dazzle/tap
brew install dazzle

# Verify installation
dazzle --version
# → DAZZLE 0.1.0

# Start using immediately
dazzle init my-app
cd my-app
dazzle build
```

### What Gets Installed

```
/opt/homebrew/Cellar/dazzle/0.1.0/
├── libexec/
│   ├── bin/python3            # Isolated Python 3.12
│   └── lib/python3.12/
│       └── site-packages/
│           ├── dazzle/         # DAZZLE package
│           ├── typer/          # Dependencies
│           ├── pydantic/
│           └── ...
└── bin/dazzle                  # CLI entry point

/opt/homebrew/bin/dazzle -> ../Cellar/dazzle/0.1.0/bin/dazzle
```

### Benefits

- ✅ **Isolated**: Own Python virtualenv, no conflicts
- ✅ **Complete**: All dependencies included
- ✅ **Fast**: Binary cache, quick install
- ✅ **Reliable**: SHA256 verification
- ✅ **Updatable**: `brew upgrade dazzle`
- ✅ **Uninstallable**: `brew uninstall dazzle`

---

## Phase 2: Homebrew Tap (Official Repository)

### Setup

```bash
# Create tap repository
# https://github.com/dazzle/homebrew-tap

homebrew-tap/
└── Formula/
    └── dazzle.rb

# Users install via:
brew tap dazzle/tap
brew install dazzle
```

### Auto-update Strategy

```bash
# CI/CD on release:
1. Tag release: git tag v0.1.0
2. GitHub Actions:
   - Build tarball
   - Calculate SHA256
   - Update Formula/dazzle.rb
   - Commit to homebrew-tap
3. Users get update:
   brew upgrade dazzle
```

---

## Phase 3: VS Code Extension Integration

### Auto-detect Homebrew Installation

Update `lspClient.ts`:

```typescript
function getPythonPath(): string {
  // 1. Try Homebrew installation first
  const homebrewPaths = [
    '/opt/homebrew/opt/dazzle/libexec/bin/python',  // Apple Silicon
    '/usr/local/opt/dazzle/libexec/bin/python',      // Intel Mac
    '/home/linuxbrew/.linuxbrew/opt/dazzle/libexec/bin/python',  // Linux
  ];

  for (const path of homebrewPaths) {
    if (fs.existsSync(path)) {
      return path;
    }
  }

  // 2. Check Homebrew bin (alternative location)
  const homebrewBin = which('dazzle');
  if (homebrewBin) {
    return extractPythonFromDazzleScript(homebrewBin);
  }

  // 3. Fall back to existing detection...
}
```

### User Experience

```bash
# Install DAZZLE
brew install dazzle

# Install VS Code extension
code --install-extension dazzle.dazzle-dsl

# Extension automatically finds Homebrew Python
# No manual configuration needed! ✅
```

---

## Phase 4: Optional LLM Dependencies

### Approach A: Separate Install (Recommended)

```bash
# Core installation (no LLM)
brew install dazzle

# Add LLM support when needed
$(brew --prefix dazzle)/libexec/bin/pip install anthropic openai
```

### Approach B: Formula Variants

```ruby
class Dazzle < Formula
  # ...

  option "with-llm", "Install with LLM support (Anthropic, OpenAI)"

  def install
    virtualenv_install_with_resources

    if build.with? "llm"
      system libexec/"bin/pip", "install", "anthropic", "openai"
    end
  end
end
```

Install with:
```bash
brew install dazzle --with-llm
```

### Approach C: Separate Formula

```bash
brew install dazzle              # Core
brew install dazzle-llm          # Adds LLM deps
```

**Recommendation**: Use Approach A (simpler, more flexible)

---

## Phase 5: Windows Support

### Option 1: Chocolatey

```powershell
# Install via Chocolatey
choco install dazzle

# Verify
dazzle --version
```

Package: `dazzle.nuspec`

### Option 2: Winget (Microsoft)

```powershell
# Install via winget
winget install dazzle.dazzle

# Verify
dazzle --version
```

Manifest: `dazzle.yaml`

### Option 3: Scoop

```powershell
# Add bucket
scoop bucket add dazzle https://github.com/dazzle/scoop-bucket

# Install
scoop install dazzle
```

**Recommendation**: Support all three (different user bases)

---

## Phase 6: Linux Support

### Homebrew on Linux

```bash
# Works on Linux too!
brew install dazzle
```

### Debian/Ubuntu (APT)

Create `.deb` package:
```bash
sudo apt install ./dazzle_0.1.0_amd64.deb
```

### Red Hat/Fedora (RPM)

Create `.rpm` package:
```bash
sudo dnf install dazzle-0.1.0-1.x86_64.rpm
```

### Snap

```bash
sudo snap install dazzle
```

---

## Phase 7: PyPI (Fallback)

Always available as fallback:

```bash
# System-wide install
pip install dazzle

# With LLM support
pip install dazzle[llm]

# Development mode
pip install -e ".[dev,llm]"
```

**Use cases**:
- Development
- CI/CD environments
- Platforms without package managers
- Custom Python environments

---

## Phase 8: Docker Image

```dockerfile
# Official image
FROM python:3.12-slim

RUN pip install dazzle[llm]

WORKDIR /project

ENTRYPOINT ["dazzle"]
CMD ["--help"]
```

Usage:
```bash
docker run -v $(pwd):/project dazzle/dazzle build
```

---

## Implementation Roadmap

### **Milestone 1: Homebrew Formula** (Week 1)
- [ ] Create `homebrew/dazzle.rb`
- [ ] Test local installation
- [ ] Calculate SHA256 checksums
- [ ] Add all resource dependencies
- [ ] Write formula tests
- [ ] Test on Intel + Apple Silicon

### **Milestone 2: GitHub Release** (Week 1)
- [ ] Create v0.1.0 release
- [ ] Generate tarball
- [ ] Publish to GitHub releases
- [ ] Update formula with real URL/SHA256

### **Milestone 3: Homebrew Tap** (Week 2)
- [ ] Create github.com/dazzle/homebrew-tap
- [ ] Move formula to tap
- [ ] Setup CI/CD for auto-updates
- [ ] Document installation

### **Milestone 4: VS Code Integration** (Week 2)
- [ ] Update extension to detect Homebrew
- [ ] Test auto-detection
- [ ] Update documentation
- [ ] Release extension v0.4.1

### **Milestone 5: Documentation** (Week 2)
- [ ] Installation guide
- [ ] Platform-specific guides
- [ ] Troubleshooting
- [ ] Migration guide (from pip)

### **Milestone 6: Windows Support** (Week 3-4)
- [ ] Create Chocolatey package
- [ ] Create winget manifest
- [ ] Create Scoop manifest
- [ ] Test on Windows 11

### **Milestone 7: Linux Packages** (Week 4-5)
- [ ] Create .deb package
- [ ] Create .rpm package
- [ ] Test on Ubuntu, Debian, Fedora
- [ ] Setup package repositories

### **Milestone 8: Docker Image** (Week 5)
- [ ] Create Dockerfile
- [ ] Publish to Docker Hub
- [ ] Add to documentation

---

## Testing Strategy

### Local Testing (Before Release)

```bash
# Test formula locally
brew install --build-from-source ./homebrew/dazzle.rb

# Verify installation
which dazzle
dazzle --version
dazzle --help

# Test basic workflow
cd /tmp
dazzle init test-app
cd test-app
dazzle validate
dazzle build

# Test VS Code integration
code .
# Open .dsl file, verify LSP works

# Uninstall
brew uninstall dazzle
```

### Platform Testing

| Platform | Test Method | Tester |
|----------|-------------|--------|
| macOS (Intel) | Real hardware | CI + Manual |
| macOS (Apple Silicon) | Real hardware | CI + Manual |
| Linux (Ubuntu 22.04) | Docker/VM | CI |
| Linux (Fedora 38) | Docker/VM | CI |
| Windows 11 | VM | Manual |

---

## Documentation Updates

### README.md

```markdown
## Installation

### macOS / Linux (Homebrew)
```bash
brew install dazzle
```

### Windows (Chocolatey)
```powershell
choco install dazzle
```

### Python (pip) - All Platforms
```bash
pip install dazzle
```

### Quick Start
```bash
dazzle init my-app
cd my-app
dazzle build
```

---

## Distribution Metrics

Track adoption across platforms:

```
| Method      | Downloads | Platform        |
|-------------|-----------|-----------------|
| Homebrew    | 1,234     | macOS/Linux     |
| PyPI        | 567       | All             |
| Chocolatey  | 123       | Windows         |
| Docker      | 89        | All             |
| **Total**   | **2,013** | -               |
```

---

## Future Enhancements

### Shell Completions

```bash
# Auto-complete for bash/zsh/fish
dazzle completion bash > /usr/local/etc/bash_completion.d/dazzle
```

### Man Pages

```bash
man dazzle
# → Shows comprehensive manual
```

### GUI Installer (macOS)

```
dazzle-0.1.0.pkg
- Installs CLI
- Installs VS Code extension
- Adds to PATH
- Native macOS experience
```

### Update Notifications

```bash
$ dazzle --version
DAZZLE 0.1.0
⚠️  New version available: 0.2.0
Run: brew upgrade dazzle
```

---

## Maintenance Plan

### Regular Updates

- **Monthly**: Dependency updates
- **Quarterly**: Feature releases
- **Yearly**: Major version bumps

### Deprecation Policy

- 6 months warning before removing features
- Maintain N-1 version support
- Clear migration guides

---

## Success Metrics

**Goal: 1,000 installations in first month**

- [ ] 500+ Homebrew installs
- [ ] 300+ PyPI installs
- [ ] 100+ Chocolatey installs
- [ ] 100+ Docker pulls

**Goal: 90% "works out of the box"**

- [ ] < 10% users need troubleshooting
- [ ] Auto-detection works for 90%+ users
- [ ] < 5% GitHub issues related to installation

---

**Next Steps**: Create first Homebrew formula and test locally!
