#!/bin/bash
#
# Prepare a new DAZZLE release
#
# Usage: ./scripts/prepare-release.sh <version>
# Example: ./scripts/prepare-release.sh 0.1.0

set -e

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.1.0"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 Preparing DAZZLE Release v$VERSION"
echo "====================================="
echo

# Check if on main branch
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo "⚠️  Not on main branch (current: $BRANCH)"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if working directory is clean
if ! git diff-index --quiet HEAD --; then
    echo "❌ Working directory is not clean. Commit or stash changes first."
    exit 1
fi

echo "✅ Git working directory is clean"
echo

# Update version in pyproject.toml
echo "📝 Updating version in pyproject.toml..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^version = .*/version = \"$VERSION\"/" "$PROJECT_ROOT/pyproject.toml"
else
    sed -i "s/^version = .*/version = \"$VERSION\"/" "$PROJECT_ROOT/pyproject.toml"
fi

echo "✅ Updated pyproject.toml"
echo

# Update version in __init__.py if it exists
INIT_FILE="$PROJECT_ROOT/src/dazzle/__init__.py"
if [ -f "$INIT_FILE" ]; then
    echo "📝 Updating version in __init__.py..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^__version__ = .*/__version__ = \"$VERSION\"/" "$INIT_FILE"
    else
        sed -i "s/^__version__ = .*/__version__ = \"$VERSION\"/" "$INIT_FILE"
    fi
    echo "✅ Updated __init__.py"
    echo
fi

# Create tarball for Homebrew
echo "📦 Creating source tarball..."
TARBALL="dazzle-$VERSION.tar.gz"
git archive --format=tar.gz --prefix="dazzle-$VERSION/" -o "/tmp/$TARBALL" HEAD

echo "✅ Created tarball: /tmp/$TARBALL"
echo

# Calculate SHA256
echo "🔐 Calculating SHA256..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    SHA256=$(shasum -a 256 "/tmp/$TARBALL" | awk '{print $1}')
else
    SHA256=$(sha256sum "/tmp/$TARBALL" | awk '{print $1}')
fi

echo "✅ SHA256: $SHA256"
echo

# Update Homebrew formula
FORMULA_PATH="$PROJECT_ROOT/homebrew/dazzle.rb"
if [ -f "$FORMULA_PATH" ]; then
    echo "📝 Updating Homebrew formula..."

    # Update URL and SHA256
    TEMP_FORMULA=$(mktemp)
    awk -v version="$VERSION" -v sha="$SHA256" '
        /^  url / { print "  url \"https://github.com/manwithacat/dazzle/archive/refs/tags/v" version ".tar.gz\""; next }
        /^  sha256 / { print "  sha256 \"" sha "\""; next }
        { print }
    ' "$FORMULA_PATH" > "$TEMP_FORMULA"

    mv "$TEMP_FORMULA" "$FORMULA_PATH"

    echo "✅ Updated Homebrew formula"
    echo
fi

# Create CHANGELOG entry template
CHANGELOG="$PROJECT_ROOT/CHANGELOG.md"
if [ ! -f "$CHANGELOG" ]; then
    touch "$CHANGELOG"
fi

echo "📝 Creating CHANGELOG entry..."
TEMP_CHANGELOG=$(mktemp)
cat > "$TEMP_CHANGELOG" << EOF
# Changelog

## [v$VERSION] - $(date +%Y-%m-%d)

### Added
- TODO: List new features

### Changed
- TODO: List changes

### Fixed
- TODO: List bug fixes

---

EOF

cat "$CHANGELOG" >> "$TEMP_CHANGELOG"
mv "$TEMP_CHANGELOG" "$CHANGELOG"

echo "✅ Created CHANGELOG template"
echo

# Commit changes
echo "📝 Committing changes..."
git add pyproject.toml "$INIT_FILE" "$FORMULA_PATH" "$CHANGELOG"
git commit -m "chore: bump version to v$VERSION"

echo "✅ Committed version bump"
echo

# Create git tag
echo "🏷️  Creating git tag..."
git tag -a "v$VERSION" -m "Release v$VERSION"

echo "✅ Created tag v$VERSION"
echo

echo "====================================="
echo "✅ Release preparation complete!"
echo
echo "Next steps:"
echo "  1. Edit CHANGELOG.md and fill in release notes"
echo "  2. Review the changes:"
echo "     git show HEAD"
echo "  3. Push to GitHub:"
echo "     git push origin main"
echo "     git push origin v$VERSION"
echo "  4. Create GitHub release at:"
echo "     https://github.com/manwithacat/dazzle/releases/new?tag=v$VERSION"
echo "  5. Upload tarball to release:"
echo "     /tmp/$TARBALL"
echo "  6. Update Homebrew tap (if separate repo):"
echo "     cd ../homebrew-tap"
echo "     cp ../dazzle/homebrew/dazzle.rb Formula/"
echo "     git commit -am 'Update dazzle to v$VERSION'"
echo "     git push"
echo
echo "Formula details:"
echo "  URL: https://github.com/manwithacat/dazzle/archive/refs/tags/v$VERSION.tar.gz"
echo "  SHA256: $SHA256"
echo
