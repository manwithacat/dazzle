#!/bin/bash
# Import GitHub rulesets for DAZZLE repository
#
# Usage: ./scripts/import-rulesets.sh [--repo owner/repo]
#
# Requires: GitHub CLI (gh) authenticated

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RULESETS_DIR="$PROJECT_ROOT/.github/rulesets"

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

echo "Importing rulesets for: $REPO"
echo "================================="
echo

# Import each ruleset
for ruleset_file in "$RULESETS_DIR"/*.json; do
    if [ -f "$ruleset_file" ]; then
        ruleset_name=$(basename "$ruleset_file" .json)
        echo -n "  $ruleset_name... "

        # Check if ruleset already exists
        existing=$(gh api "/repos/$REPO/rulesets" --jq ".[] | select(.name == \"$ruleset_name\") | .id" 2>/dev/null || echo "")

        if [ -n "$existing" ]; then
            # Update existing ruleset
            if gh api \
                --method PUT \
                -H "Accept: application/vnd.github+json" \
                "/repos/$REPO/rulesets/$existing" \
                --input "$ruleset_file" > /dev/null 2>&1; then
                echo "updated"
            else
                echo "failed to update"
            fi
        else
            # Create new ruleset
            if gh api \
                --method POST \
                -H "Accept: application/vnd.github+json" \
                "/repos/$REPO/rulesets" \
                --input "$ruleset_file" > /dev/null 2>&1; then
                echo "created"
            else
                echo "failed to create"
            fi
        fi
    fi
done

echo
echo "================================="
echo "Ruleset import complete!"
echo
echo "View rulesets at: https://github.com/$REPO/settings/rules"
