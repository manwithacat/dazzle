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

4. **Update CHANGELOG.md** following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions:
   - Read `CHANGELOG.md` and find the `## [Unreleased]` section.
   - If the Unreleased section has content (entries under Added/Changed/Deprecated/Fixed/Removed/Security):
     1. Insert a new heading `## [X.Y.Z] - YYYY-MM-DD` (today's date) immediately after the Unreleased section heading's blank line.
     2. Move **all** subsection headings and entries from Unreleased under the new version heading.
     3. Leave the `## [Unreleased]` heading in place with empty subsections beneath it, ready for future work:
        ```
        ## [Unreleased]

        ## [X.Y.Z] - YYYY-MM-DD

        ### Added
        - (the entries that were under Unreleased)
        ...
        ```
   - If the Unreleased section is already empty, just add the new version heading with no content.
   - **Do NOT** alter any existing released version sections below.

5. **Do NOT create a git tag yet.** The tag must be created AFTER the commit so it points to the correct commit. `/ship` handles tagging automatically.

6. **Report** the change: `Bumped version: OLD → NEW` and list the files modified.
   Remind the user: run `/ship` to commit, push, and create + push the tag (which triggers PyPI + Homebrew releases).

Do NOT commit or tag. The user will run `/ship` separately.
