# DAZZLE Version Command - Implementation Summary

**Date**: 2025-11-23
**Status**: ✅ Implemented and Documented

## Overview

Implemented comprehensive `--version` flag for the DAZZLE CLI that displays version and environment information to help users troubleshoot installation and configuration issues.

## Problem Solved

Users had no easy way to:
- Check which version of DAZZLE is installed
- Verify their Python environment
- Confirm LSP server availability
- See which stacks are available
- Troubleshoot installation issues

## Implementation

### 1. CLI Changes (`src/dazzle/cli.py`)

#### Added Version Functions

```python
def get_version() -> str:
    """Get DAZZLE version from package metadata."""
    try:
        from importlib.metadata import version
        return version("dazzle")
    except Exception:
        return "0.1.0-dev"

def version_callback(value: bool) -> None:
    """Display version and environment information."""
    if value:
        dazzle_version = get_version()
        python_version = platform.python_version()
        python_impl = platform.python_implementation()
        system = platform.system()
        machine = platform.machine()

        # ... displays comprehensive environment info
```

#### Added Callback to Typer App

```python
@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and environment information",
        ),
    ] = None,
) -> None:
    """DAZZLE CLI - Domain-Aware DSL for LLM-Enabled Apps."""
    pass
```

### 2. Output Format

The `--version` command displays:

```
DAZZLE version 0.1.0

Environment:
  Python:        CPython 3.12.11
  Platform:      Darwin 25.2.0
  Architecture:  arm64

Installation:
  Method:        pip (editable)
  Location:      /Volumes/SSD/Dazzle

Features:
  LSP Server:    ✓ Available
  LLM Support:   ✗ Not available (install with: pip install dazzle[llm])

Available Stacks:
  - django_api
  - django_micro_modular
  - docker
  - express_micro
  - openapi
  - terraform
```

## Updates to Distribution Artifacts

### 1. Homebrew Formula (`homebrew/dazzle.rb`)

#### Updated Caveats
- Changed quick start from `dazzle init my-project` to `mkdir my-project && cd my-project && dazzle init`
- Added "Check installation: dazzle --version"
- Added troubleshooting section mentioning version command

```ruby
def caveats
  <<~EOS
    DAZZLE has been installed!

    Quick start:
      mkdir my-project && cd my-project
      dazzle init
      dazzle build

    Check installation:
      dazzle --version

    ...

    Troubleshooting:
      Run 'dazzle --version' to see your environment details
  EOS
end
```

#### Updated Tests
Added version command test:

```ruby
test do
  # Test that the CLI works
  assert_match "dazzle", shell_output("#{bin}/dazzle --help").downcase

  # Test version command
  output = shell_output("#{bin}/dazzle --version")
  assert_match "DAZZLE version", output
  assert_match "Environment:", output
  assert_match "Python:", output

  # ... existing tests
end
```

### 2. Main README (`README.md`)

#### Added to Installation Section
```bash
# Verify installation
dazzle --version
```

#### Added to CLI Commands Section
```bash
# Check version and environment info
dazzle --version
```

## Features Displayed

### Version Information
- DAZZLE version from package metadata
- Handles dev installations gracefully

### Environment Details
- Python version and implementation (CPython, PyPy, etc.)
- Operating system and version
- CPU architecture

### Installation Information
- Installation method detection:
  - `pip (editable)` - Development installation (`pip install -e .`)
  - `pip (standard)` - Regular pip installation
  - `homebrew` - Installed via brew
  - `unknown` - Other installation methods
- Installation location (full path)

### Feature Availability
- **LSP Server**: Checks if `dazzle.lsp.server` module is available
  - ✓ Available
  - ✗ Not available (with installation instructions)
- **LLM Support**: Checks if Anthropic/OpenAI packages are installed
  - ✓ Available
  - ✗ Not available (with installation instructions: `pip install dazzle[llm]`)

### Available Stacks
Lists all registered stacks:
- django_api
- django_micro_modular
- docker
- express_micro
- openapi
- terraform

## Implementation Details

### Version Source
Uses `importlib.metadata.version("dazzle")` which reads from:
- `pyproject.toml` line 7: `version = "0.1.0"`
- Package metadata when installed

No separate VERSION file needed - pyproject.toml is single source of truth.

### Installation Method Detection
```python
try:
    location = dazzle.__file__
    if location:
        location_path = Path(location).parent
        if any(parent.name == "site-packages" for parent in location_path.parents):
            install_method = "pip (standard)"
        elif any(parent.name == "Cellar" for parent in location_path.parents):
            install_method = "homebrew"
        else:
            install_method = "pip (editable)"
except Exception:
    install_method = "unknown"
```

### LSP Detection
```python
try:
    import dazzle.lsp.server
    lsp_available = True
except ImportError:
    lsp_available = False
```

**Note**: LSP import triggers verbose pygls logging (INFO level). This is cosmetic and doesn't affect functionality.

### LLM Support Detection
```python
try:
    import anthropic
    import openai
    llm_available = True
except ImportError:
    llm_available = False
```

### Stack Discovery
Uses existing stack registry:
```python
from dazzle.stacks import get_available_stacks
stacks = get_available_stacks()
```

## Usage Examples

### Basic Version Check
```bash
$ dazzle --version
DAZZLE version 0.1.0
...

$ dazzle -v
DAZZLE version 0.1.0
...
```

### In Scripts
```bash
#!/bin/bash
# Check DAZZLE is installed
if ! command -v dazzle &> /dev/null; then
    echo "DAZZLE not found"
    exit 1
fi

# Get version info
dazzle --version

# Check for LSP (for IDE integration)
if dazzle --version | grep -q "LSP Server:.*✓"; then
    echo "LSP available for IDE"
fi
```

### Troubleshooting Workflow
1. User reports issue
2. Ask for `dazzle --version` output
3. Check Python version, installation method, feature availability
4. Provide specific fix based on environment

## Benefits

1. **Easy Troubleshooting**: Single command shows all relevant environment info
2. **Installation Verification**: Confirms DAZZLE is properly installed
3. **Feature Discovery**: Shows which optional features are available
4. **Support**: Makes it easy to provide environment info when reporting issues
5. **CI/CD**: Useful in build scripts to verify installation

## Backwards Compatibility

✅ **Fully backwards compatible**

- No breaking changes to existing commands
- `--version` is a new optional flag
- Works with all installation methods (pip, homebrew, development)

## Files Modified

1. **`src/dazzle/cli.py`**
   - Added `get_version()` function (lines 20-28)
   - Added `version_callback()` function (lines 31-126)
   - Added logging suppression for pygls during LSP check (lines 66-76)
   - Added `@app.callback()` with `--version` option (lines 129-144)

2. **`homebrew/dazzle.rb`**
   - Updated caveats section (lines 79-105)
   - Added version command test (lines 112-116)

3. **`README.md`**
   - Added version verification to Installation section (line 36)
   - Added version command to CLI Commands section (lines 243-244)

## Testing

### Manual Testing
```bash
# Test short flag
$ dazzle -v
✅ Works - shows version info

# Test long flag
$ dazzle --version
✅ Works - shows version info

# Test with other flags (should show version and exit)
$ dazzle --version --help
✅ Works - shows version (eager flag takes precedence)

# Test environment detection
$ which python3
/opt/homebrew/bin/python3
$ dazzle --version | grep Python
✅ Shows correct Python version

# Test LSP detection
$ python3 -c "import dazzle.lsp.server"
$ dazzle --version | grep LSP
✅ Shows LSP available

# Test stack listing
$ dazzle --version | grep "Available Stacks"
✅ Lists all stacks
```

### Homebrew Formula Test
```bash
$ brew test dazzle
✅ All tests pass including version command test
```

## Known Issues

### LSP Import Logging
~~When checking LSP availability, pygls emits INFO logs~~

**Status**: ✅ Fixed

The verbose pygls logging during LSP availability check has been suppressed by temporarily setting the pygls logger to ERROR level during import:

```python
# Suppress verbose pygls logging during import check
import logging
pygls_logger = logging.getLogger("pygls")
original_level = pygls_logger.level
pygls_logger.setLevel(logging.ERROR)

import dazzle.lsp.server
lsp_available = True

# Restore original logging level
pygls_logger.setLevel(original_level)
```

This provides a clean binary ready/not-ready status without verbose output.

## Future Enhancements

Potential improvements:

1. **JSON Output**: Add `--version --json` for machine-readable output
2. **Verbose Mode**: Add `--version --verbose` for even more detail
3. **Check Updates**: Compare with latest PyPI version
4. **Config Display**: Show active configuration from `dazzle.toml`
5. **Stack Details**: Show version/info for each stack
6. **Plugin Info**: List installed plugins and their versions

## Documentation Updated

- ✅ README.md - Installation and CLI sections
- ✅ homebrew/dazzle.rb - Caveats and tests
- ✅ This summary document

## Related Changes

This implementation complements:
- **Init Command UX** (2025-11-23): Improved init to work in current directory
- **VS Code Extension** (2025-11-23): Extension can use version info for troubleshooting

## Success Metrics

- ✅ Users can verify installation with single command
- ✅ Support requests can quickly gather environment info
- ✅ CI/CD scripts can verify DAZZLE installation
- ✅ Documentation clearly shows how to check version

## Conclusion

The `--version` command provides comprehensive environment information in a user-friendly format, making it easy to verify installation, troubleshoot issues, and discover available features.

**Implementation time**: ~1 hour
**Testing time**: ~30 minutes
**Documentation time**: ~30 minutes
**Total effort**: ~2 hours
**Impact**: High value for support and troubleshooting
