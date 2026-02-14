Sync documentation with recently closed GitHub issues using LLM-powered analysis. Follow these steps exactly:

## 1. Scan issues

Run `dazzle docs update --dry-run --since "$ARGUMENTS"` to scan closed GitHub issues and preview proposed documentation changes.

- If no argument was provided, run `dazzle docs update --dry-run` (defaults to issues closed since the latest release tag).
- If the command fails (e.g. `gh` not authenticated, no API key), report the error clearly and stop.

## 2. Review the plan

Read the dry-run output carefully. For each proposed patch:

- **CHANGELOG**: Check that entries are correctly categorised (Added/Changed/Fixed/Deprecated) and that summaries are clear and concise.
- **README**: Check that updates preserve the existing tone and structure. Flag any section that looks substantially rewritten rather than surgically updated.
- **MkDocs**: Check that page updates make sense and don't remove existing content.

Report a brief summary: how many issues were scanned, how many are relevant, and what patches are proposed.

## 3. Ask for confirmation

Ask the user whether to:
1. **Apply all patches** — run `dazzle docs update --yes --since <same-since-value>`
2. **Apply specific targets only** — e.g. `dazzle docs update --yes --since <value> --target changelog`
3. **Abort** — stop without writing anything

## 4. Apply

Run the chosen command. After it completes:

- Run `git diff --stat` to show what changed.
- Read each modified file and verify the changes look correct.
- If anything looks wrong, revert the specific file with `git checkout -- <file>` and explain what went wrong.

## 5. Offer to ship

Ask the user if they want to commit and push the documentation updates. If yes, use `/ship`.
