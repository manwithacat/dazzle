#!/bin/bash
# Setup GitHub labels for DAZZLE repository
#
# This script creates all the labels needed for issue quality tracking,
# AI co-authorship verification, and project organization.
#
# Usage: ./scripts/setup-github-labels.sh [--repo owner/repo]
#
# Requires: GitHub CLI (gh) authenticated

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABELS_FILE="$PROJECT_ROOT/.github/labels.yml"

# Default to current repo
REPO=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            REPO="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is required but not installed."
    echo "Install: https://cli.github.com/"
    exit 1
fi

# Check authentication
if ! gh auth status &> /dev/null; then
    echo "Error: GitHub CLI not authenticated. Run: gh auth login"
    exit 1
fi

# Get repo if not specified
if [ -z "$REPO" ]; then
    REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
    if [ -z "$REPO" ]; then
        echo "Error: Could not determine repository. Use --repo owner/repo"
        exit 1
    fi
fi

echo "Setting up labels for: $REPO"
echo "================================="
echo

# Parse YAML and create labels
# This is a simple parser - for production use, consider yq or Python
create_labels() {
    local name=""
    local color=""
    local description=""

    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue

        if [[ "$line" =~ ^-\ name:\ (.+)$ ]]; then
            # Save previous label if exists
            if [ -n "$name" ]; then
                create_or_update_label "$name" "$color" "$description"
            fi
            name="${BASH_REMATCH[1]}"
            # Remove quotes if present
            name="${name%\"}"
            name="${name#\"}"
            color=""
            description=""
        elif [[ "$line" =~ ^[[:space:]]+color:\ (.+)$ ]]; then
            color="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ ^[[:space:]]+description:\ (.+)$ ]]; then
            description="${BASH_REMATCH[1]}"
            # Remove quotes if present
            description="${description%\"}"
            description="${description#\"}"
        fi
    done < "$LABELS_FILE"

    # Create last label
    if [ -n "$name" ]; then
        create_or_update_label "$name" "$color" "$description"
    fi
}

create_or_update_label() {
    local name="$1"
    local color="$2"
    local description="$3"

    echo -n "  $name... "

    # Try to create, if exists update
    if gh label create "$name" --color "$color" --description "$description" --repo "$REPO" 2>/dev/null; then
        echo "created"
    else
        # Label exists, update it
        if gh label edit "$name" --color "$color" --description "$description" --repo "$REPO" 2>/dev/null; then
            echo "updated"
        else
            echo "failed"
        fi
    fi
}

echo "Creating/updating labels..."
create_labels

echo
echo "================================="
echo "Label setup complete!"
echo
echo "View labels at: https://github.com/$REPO/labels"
