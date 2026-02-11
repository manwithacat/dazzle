Bump the project's semantic version. The user may specify a bump level as an argument: `major`, `minor`, or `patch` (default: `patch`). They may also pass an explicit version like `1.2.3`.

## Steps

1. **Read current version** from `pyproject.toml` (the `version = "X.Y.Z"` line near the top).

2. **Compute new version**:
   - If the argument is `major`: bump X, reset Y and Z to 0.
   - If the argument is `minor`: bump Y, reset Z to 0.
   - If the argument is `patch` (or no argument): bump Z.
   - If the argument matches `\d+\.\d+\.\d+`: use it as-is.
   - Otherwise: tell the user the argument was not understood and stop.

3. **Update version in all canonical locations** (use the Edit tool for each):
   - `pyproject.toml` — the `version = "..."` line (near line 7)
   - `.claude/CLAUDE.md` — the `**Version**: X.Y.Z` line at the bottom
   - `ROADMAP.md` — the `**Current Version**: vX.Y.Z` line near the top
   - `src/dazzle/mcp/semantics_kb/core.toml` — the `version = "..."` line
   - `homebrew/dazzle.rb` — the `version "X.Y.Z"` line AND the `url "...vX.Y.Z.tar.gz"` line

   **Do NOT** touch version references in code comments (e.g. `# v0.19.0 HLESS`) or dependency pins (e.g. `aiosqlite>=0.19.0`). Those refer to the version a feature was introduced, not the current project version.

4. **Do NOT create a git tag yet.** The tag must be created AFTER the commit so it points to the correct commit. `/ship` handles tagging automatically.

5. **Report** the change: `Bumped version: OLD → NEW` and list the files modified.
   Remind the user: run `/ship` to commit, push, and create + push the tag (which triggers PyPI + Homebrew releases).

Do NOT commit or tag. The user will run `/ship` separately.
