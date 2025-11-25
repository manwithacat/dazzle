# GitHub Rulesets

This directory contains importable rulesets for configuring repository rules.

## Available Rulesets

| File | Description |
|------|-------------|
| `copilot-review.json` | Enables automatic Copilot code review on PRs |
| `branch-protection.json` | Standard branch protection for main branch |

## How to Import

### Via GitHub UI

1. Go to **Settings → Rules → Rulesets**
2. Click **New ruleset** dropdown
3. Select **Import a ruleset**
4. Upload the JSON file

### Via GitHub CLI

```bash
# Import a single ruleset
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  /repos/OWNER/REPO/rulesets \
  --input .github/rulesets/copilot-review.json

# Or use the helper script
./scripts/import-rulesets.sh
```

### Via GitHub API

```bash
curl -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/OWNER/REPO/rulesets \
  -d @.github/rulesets/copilot-review.json
```

## Ruleset Details

### copilot-review.json

Configures GitHub Copilot to automatically review all pull requests:

- **Target**: Default branch
- **Review drafts**: Yes (catch issues early)
- **Review on push**: Yes (re-review when commits are added)

Requirements:
- Repository must have Copilot enabled
- Requires Copilot Pro, Pro+, Business, or Enterprise plan

### branch-protection.json

Standard branch protection rules:

- Require pull request before merging
- Require status checks to pass
- Require linear history (no merge commits)
- Block force pushes

## Customization

Edit the JSON files to customize:

- `enforcement`: `"active"`, `"evaluate"` (dry-run), or `"disabled"`
- `conditions.ref_name.include`: Target branches (`~DEFAULT_BRANCH`, `refs/heads/main`, etc.)
- `bypass_actors`: Teams/users who can bypass rules

## References

- [GitHub Docs: Managing Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository)
- [REST API: Repository Rules](https://docs.github.com/en/rest/repos/rules)
- [Copilot Code Review](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/configure-automatic-review)
