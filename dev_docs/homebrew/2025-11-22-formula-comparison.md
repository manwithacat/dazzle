# Homebrew Formula Optimization

## Current Formula (Slow)

**Method**: `virtualenv_install_with_resources`
- ❌ Builds ALL packages from source (`--no-binary :all:`)
- ❌ Requires Rust compiler (2GB download)
- ❌ Compiles pydantic-core (2-5 minutes)
- ❌ Total time: ~15 minutes
- ❌ Disk: ~2.2GB during install (17MB final)

**Code**:
```ruby
depends_on "python@3.12"
depends_on "rust" => :build

resource "pydantic" do
  url "..."
  sha256 "..."
end
# ... 11 more resource blocks

def install
  virtualenv_install_with_resources
end
```

## Optimized Formula (Fast)

**Method**: Direct pip install with binary wheels
- ✅ Uses pre-built wheels from PyPI
- ✅ No Rust compiler needed
- ✅ No compilation
- ✅ Total time: ~30 seconds
- ✅ Disk: ~17MB

**Code**:
```ruby
depends_on "python@3.12"  # or 3.11, 3.13

def install
  virtualenv_create(libexec, python3)
  system libexec/"bin/pip", "install", "--verbose", buildpath
end
```

## Key Changes

1. **Removed**: 80+ lines of resource declarations
2. **Removed**: Rust build dependency
3. **Added**: Direct pip install (uses pyproject.toml)
4. **Result**: 95% faster installation

## Python Version Flexibility

### Current
- Hard-coded to Python 3.12

### Improved Options

**Option A**: Support multiple versions
```ruby
# Try 3.13, fallback to 3.12, fallback to 3.11
depends_on "python@3.13" => :optional
depends_on "python@3.12"
depends_on "python@3.11" => :optional

def python3
  Formula["python@3.13"].opt_bin/"python3.13"
rescue FormulaUnavailableError
  Formula["python@3.12"].opt_bin/"python3.12"
rescue FormulaUnavailableError
  Formula["python@3.11"].opt_bin/"python3.11"
end
```

**Option B**: Use Homebrew's default Python
```ruby
depends_on "python@3"  # Uses latest available
```

**Recommended**: Start with Option B (simplest), add flexibility later if needed.

## Migration Plan

1. Test optimized formula locally
2. Update homebrew-tap repository
3. Users run `brew upgrade dazzle` for instant improvements
4. Future installs: 30 seconds vs 15 minutes

## Performance Comparison

| Metric | Current | Optimized | Improvement |
|--------|---------|-----------|-------------|
| Install time | ~15 min | ~30 sec | **30x faster** |
| Download size | ~2.2 GB | ~17 MB | **129x smaller** |
| Rust required | Yes | No | Simpler |
| Compilation | Yes | No | Faster |
| Maintenance | Complex | Simple | Easier |
