---
name: bump
description: Bump the semantic version across all six canonical locations and update CHANGELOG
---

Bump the project's semantic version. The user may specify a bump level as an argument: `major`, `minor`, or `patch` (default: `patch`). They may also pass an explicit version like `1.2.3`.

## Steps

1. **Read current version** from `pyproject.toml` (the `version = "X.Y.Z"` line near the top).

2. **Compute new version**:
   - If the argument is `major`: bump X, reset Y and Z to 0.
   - If the argument is `minor`: bump Y, reset Z to 0.
   - If the argument is `patch` (or no argument): bump Z.
   - If the argument matches `\d+\.\d+\.\d+`: use it as-is.
   - Otherwise: tell the user the argument was not understood and stop.

3. **Apply ALL version-line bumps in a single Bash invocation.** Five files carry the project's canonical version string, plus a sixth file (homebrew) carries it on two lines. Editing them one-by-one with the Edit tool triggers a pre-commit reformat race that costs ~30s of agent time per bump (closed #1063 surface A; this step closes surface B).

   Substitute `OLD` and `NEW` and run:

   ```bash
   OLD="0.67.126"
   NEW="0.67.127"

   # pyproject.toml + core.toml — `version = "X.Y.Z"`
   sed -i.bak "s/^version = \"${OLD}\"$/version = \"${NEW}\"/" pyproject.toml src/dazzle/mcp/semantics_kb/core.toml

   # AGENTS.md — `**Version**: X.Y.Z`
   sed -i.bak "s/\\*\\*Version\\*\\*: ${OLD}/**Version**: ${NEW}/" AGENTS.md

   # ROADMAP.md — `**Current Version**: vX.Y.Z`
   sed -i.bak "s/\\*\\*Current Version\\*\\*: v${OLD}/**Current Version**: v${NEW}/" ROADMAP.md

   # homebrew/dazzle.rb — `version "X.Y.Z"` AND `tags/vX.Y.Z.tar.gz`
   sed -i.bak \
     -e "s/^  version \"${OLD}\"$/  version \"${NEW}\"/" \
     -e "s|tags/v${OLD}\\.tar\\.gz|tags/v${NEW}.tar.gz|" \
     homebrew/dazzle.rb

   # Clean up sed's .bak files (BSD sed on macOS requires the extension).
   # maxdepth 6 covers src/dazzle/mcp/semantics_kb/core.toml.bak; bump if
   # any future target moves deeper.
   find . -maxdepth 6 -name "*.bak" -delete

   # Verify all six version lines moved exactly. Expected: 6 matching lines.
   # Note: \*\*Version\*\* on AGENTS.md has trailing text on the same line
   # (`| **Python**: 3.12+ | ...`) so don't anchor with `$`.
   grep -E "^version = \"${NEW}\"$|^\\*\\*Version\\*\\*: ${NEW} |^\\*\\*Current Version\\*\\*: v${NEW}$|^  version \"${NEW}\"$|tags/v${NEW}\\.tar\\.gz" \
     pyproject.toml src/dazzle/mcp/semantics_kb/core.toml AGENTS.md ROADMAP.md homebrew/dazzle.rb
   ```

   If the final `grep` prints fewer than 6 lines, **stop and investigate** — one of the canonical locations didn't match the expected shape and needs manual attention.

   **Do NOT** touch version references in code comments (e.g. `# v0.19.0 HLESS`) or dependency pins (e.g. `aiosqlite>=0.19.0`). Those refer to the version a feature was introduced, not the current project version. The sed patterns above are anchored (`^`) to avoid matching those.

4. **Update CHANGELOG.md** following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions. This is the only step that needs structured logic, so use the Edit tool here:
   - Read `CHANGELOG.md` and find the `## [Unreleased]` section.
   - **Drift guard (#1259):** if the Unreleased section already carries content from a previous commit that *didn't* run `/bump` (i.e. it's not just the work you're about to bundle into this release), **stop and warn** rather than swallowing it into this version. The v0.72–v0.74 cycle accumulated ~200 lines of orphaned entries under Unreleased because multiple commits shipped without bumps; backfilling them later required a separate hygiene pass. A rough heuristic: if Unreleased has entries that span multiple unrelated themes / multiple `### ` subsections referencing distinct issue numbers, ask the user whether to (a) bundle them all into this version, (b) backfill them to past versions first, or (c) split this bump into multiple targeted versions.
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
