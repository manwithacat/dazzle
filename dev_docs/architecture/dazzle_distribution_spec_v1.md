# DAZZLE Distribution & Tooling Specification (v1)

This specification is written for an LLM coding agent acting as an expert developer and release engineer.
Follow the instructions as *imperatives* and avoid asking for clarification unless absolutely necessary.

---

## 0. High-level goals

1. Provide a clean, repeatable way for users to install the `dazzle` CLI:
   - On macOS (and optionally Linux) via Homebrew tap.
   - On Windows via `winget` (primary) and optionally Scoop.
2. Provide a clean, repeatable way to publish and update the DAZZLE VS Code extension to the VS Code Marketplace.
3. Minimise manual steps by:
   - Generating the necessary manifest files.
   - Preparing GitHub Actions workflows where appropriate.
   - Documenting one-shot manual actions for the human operator (tokens, accounts, first-time setup).

Assume:
- There is a main DAZZLE repo: `github.com/<OWNER>/dazzle` (CLI + VS Code extension under `vscode-extension/`).
- There is a DAZZLE Homebrew tap repo: `github.com/<OWNER>/homebrew-dazzle`.
- There may be a Scoop bucket repo later: `github.com/<OWNER>/dazzle-scoop-bucket`.

Replace `<OWNER>` with the actual GitHub owner/organisation when generating real code.

---

## 1. Homebrew Tap & Formula (macOS / Linux)

### 1.1. Tap repository structure

1. Ensure the tap repository is named using the Homebrew convention:
   - `homebrew-dazzle`
2. Enforce the following directory layout in that repo:
   - `Formula/`
     - `dazzle.rb`
   - `README.md`
   - Optional: `.github/workflows/` for bottle-building automation.

3. If these paths do not exist:
   - Create the `Formula/` directory.
   - Create empty placeholder files where needed and fill them with the content defined below.

### 1.2. Release artefacts assumption

1. Assume the DAZZLE CLI is released via GitHub Releases on the main repo:
   - Release tag format: `vX.Y.Z` (e.g. `v0.1.0`).
   - Assets (examples):
     - `dazzle-darwin-arm64`
     - `dazzle-darwin-amd64`
     - `dazzle-linux-x86_64`
2. In the absence of explicit artefact names, default to:
   - `dazzle-darwin-arm64` and `dazzle-darwin-amd64` for macOS.
3. Expect that the human will build and upload these artefacts prior to updating the Homebrew formula.

### 1.3. Generate Homebrew formula (prebuilt binaries)

1. Implement a generator script (e.g. `scripts/generate_homebrew_formula.py` in the main repo) that:
   - Accepts:
     - Version (e.g. `0.1.0`).
     - Release tag (e.g. `v0.1.0`).
     - Owner (e.g. `jamesbarlow`).
   - Queries or is provided with:
     - SHA256 hash for each binary artefact (these may be provided manually as arguments).

2. The generator script must emit a `Formula/dazzle.rb` with logic similar to:

   ```ruby
   class Dazzle < Formula
     desc "DSL-driven app builder"
     homepage "https://github.com/<OWNER>/dazzle"
     version "X.Y.Z"

     if Hardware::CPU.arm?
       url "https://github.com/<OWNER>/dazzle/releases/download/vX.Y.Z/dazzle-darwin-arm64"
       sha256 "SHA256_FOR_ARM"
     else
       url "https://github.com/<OWNER>/dazzle/releases/download/vX.Y.Z/dazzle-darwin-amd64"
       sha256 "SHA256_FOR_AMD"
     end

     def install
       binary_name = if Hardware::CPU.arm?
         "dazzle-darwin-arm64"
       else
         "dazzle-darwin-amd64"
       end
       bin.install binary_name => "dazzle"
     end

     test do
       system "#{bin}/dazzle", "--version"
     end
   end
   ```

3. Ensure all `<OWNER>`, `X.Y.Z`, and SHA placeholders are replaced with actual values in generated output.

4. From within the tap repo, the formula must be committed and pushed by the human or by an automated workflow that opens a PR.

### 1.4. Basic Homebrew usage documentation

1. Generate or update `README.md` in the tap repo with usage instructions:

   ```markdown
   # DAZZLE Homebrew Tap

   ```bash
   brew tap <OWNER>/dazzle
   brew install dazzle
   # or, in one line:
   brew install <OWNER>/dazzle/dazzle
   ```
   ```

2. If the Linuxbrew audience is relevant, mention that the same tap should work on Linux with compatible binaries.

### 1.5. (Optional) GitHub Actions for bottle builds

1. Create a workflow file `.github/workflows/build-bottles.yml` in the tap repo that:
   - Triggers on changes to `Formula/dazzle.rb` or on manual dispatch.
   - Uses Homebrew’s official actions (`homebrew/actions`) to build and upload bottles, and update the formula.
2. Keep this step optional; prioritise the prebuilt binary formula first.

---

## 2. Windows Distribution

Primary: `winget`. Optional: Scoop bucket.

### 2.1. Assumptions for Windows artefacts

1. Assume DAZZLE provides at least one Windows artefact per version, either:
   - A standalone EXE, or
   - A ZIP containing an EXE and supporting files.

2. Assume the artefact is published under a GitHub Release in the main repo with a stable URL pattern.

### 2.2. winget manifest generation

1. Create a directory in the main repo: `packaging/winget/`.
2. Implement a script `packaging/winget/generate_winget_manifest.py` (or similar) that:
   - Takes as input:
     - Publisher ID (e.g. `JamesBarlow`).
     - Package ID (e.g. `JamesBarlow.Dazzle`).
     - Version (`X.Y.Z`).
     - Download URL for the Windows installer or binary.
     - SHA256 of the installer or binary.
   - Emits a set of YAML files in the structure expected by `winget-pkgs`:
     - `manifests/j/JamesBarlow/Dazzle/X.Y.Z/JamesBarlow.Dazzle.installer.yaml`
     - `manifests/j/JamesBarlow/Dazzle/X.Y.Z/JamesBarlow.Dazzle.locale.en-US.yaml`
     - `manifests/j/JamesBarlow/Dazzle/X.Y.Z/JamesBarlow.Dazzle.yaml`

3. The script must populate at minimum:
   - Package identifier, version, publisher, package name.
   - Installer type (`exe`, `zip`, or `portable` as appropriate).
   - Installer URL, SHA256.
   - Short description and homepage.
4. Provide a short `README.md` in `packaging/winget/` explaining that these manifests should be pushed as a PR to the `microsoft/winget-pkgs` repo.

5. Optionally, provide a script or documented steps to use the `wingetcreate` CLI to scaffold manifests automatically, with a note to copy the output into version-controlled manifest files.

### 2.3. Scoop bucket (optional)

1. Assume a separate repo: `dazzle-scoop-bucket`.
2. Enforce this structure:
   - `bucket/dazzle.json`
   - `README.md`

3. Implement a manifest generator script (could live in the main repo under `packaging/scoop/generate_scoop_manifest.py`) that emits JSON like:

   ```json
   {
     "version": "X.Y.Z",
     "description": "DSL-driven app builder",
     "homepage": "https://github.com/<OWNER>/dazzle",
     "license": "MIT",
     "architecture": {
       "64bit": {
         "url": "https://github.com/<OWNER>/dazzle/releases/download/vX.Y.Z/dazzle-windows-amd64.exe",
         "hash": "SHA256_FOR_WINDOWS_EXE"
       }
     },
     "bin": "dazzle-windows-amd64.exe"
   }
   ```

4. Add usage instructions to `README.md` in the bucket repo:

   ```bash
   scoop bucket add dazzle https://github.com/<OWNER>/dazzle-scoop-bucket
   scoop install dazzle
   ```

5. Keep Scoop as an optional/advanced channel; do not block release on it.

### 2.4. WSL note

1. Add a “WSL users” section to the main DAZZLE README with instructions:

   ```bash
   # inside WSL (Ubuntu, Debian, etc.)
   brew tap <OWNER>/dazzle
   brew install dazzle
   ```

2. Explicitly state that using the Homebrew tap inside WSL is a recommended path for Linux/WSL users.

---

## 3. VS Code Extension Publishing

Assume:
- The VS Code extension lives inside the main repo at `vscode-extension/`.
- The extension is named `dazzle` and uses a publisher like `jamesbarlow`.

### 3.1. Directory structure

1. Enforce at minimum:

   ```text
   vscode-extension/
     package.json
     README.md
     CHANGELOG.md
     src/
     out/          # or dist/, depending on build
     .vscodeignore
   ```

2. Ensure `package.json` contains:
   - `"name": "dazzle"` (or similar).
   - `"publisher": "<publisher-id>"` (e.g. `jamesbarlow`).
   - `"version": "X.Y.Z"`.
   - `"engines": { "vscode": "^1.95.0" }` (or whatever minimum VS Code version is targeted).
   - `"categories": [...]` including `"Other"` at minimum.
   - Appropriate `activationEvents` and `contributes` sections for the extension’s features.

### 3.2. VSCE tooling setup

1. Add a `dev-tools` section to the main repo documentation recommending installation of `vsce` globally:

   ```bash
   npm install -g vsce
   ```

2. In the `vscode-extension/` directory, provide npm scripts in `package.json`:

   ```json
   "scripts": {
     "build": "tsc -p ./",
     "package": "vsce package",
     "publish": "vsce publish"
   }
   ```

3. Assume the human will create:
   - A publisher on the Visual Studio Marketplace.
   - A Personal Access Token (PAT) with Marketplace publish rights.

4. Document the one-time login step in `vscode-extension/README.md`:

   ```bash
   vsce login <publisher-id>
   # paste PAT when prompted
   ```

### 3.3. Automated packaging and publishing

1. Create a GitHub Actions workflow in the main repo at `.github/workflows/vscode-extension-publish.yml` with the following behaviour:
   - Trigger on tag push matching `v*` OR manual dispatch.
   - Check out the repo.
   - Install Node.js (use a reasonably current LTS).
   - Run `npm ci` or `npm install` inside `vscode-extension/`.
   - Run `npm run build` (if TypeScript or a build step exists).
   - Run `npm run package` to produce a `.vsix` file.
   - Upload the resulting `.vsix` as a workflow artefact.
   - Optionally, if a secret `VSCE_TOKEN` is available, run `vsce publish` non-interactively.

2. Ensure the workflow uses environment variables/inputs so that publishing can be toggled:
   - e.g. an `input: publish` boolean on `workflow_dispatch`.
   - Or use the presence/absence of `VSCE_TOKEN` to decide whether to publish or just build.

3. Ensure that the workflow fails loudly if `vsce` or `VSCE_TOKEN` is missing when `publish` is requested.

### 3.4. Manual publish fallback

1. Document fallback commands in `vscode-extension/README.md`:

   ```bash
   # from vscode-extension/
   npm run build
   npm run package   # produces dazzle-X.Y.Z.vsix
   vsce publish      # uses previously configured vsce login
   ```

2. Note that the `.vsix` file can be installed manually if needed:

   ```bash
   code --install-extension dazzle-X.Y.Z.vsix
   ```

---

## 4. Versioning & Release Workflow

### 4.1. Single source of truth for version

1. Use a single version string per release cycle:
   - For example, keep a `VERSION` file in the repo root containing `X.Y.Z`.
2. Ensure that:
   - The CLI reports `X.Y.Z` via `dazzle --version`.
   - The VS Code extension `package.json.version` matches `X.Y.Z`.
   - The Homebrew formula, winget manifests, and Scoop manifest all use `X.Y.Z`.

3. Implement a small script (e.g. `scripts/bump_version.py`) to:
   - Update the `VERSION` file.
   - Update the VS Code `package.json` version.
   - Optionally update any manifest templates that reference the version.

### 4.2. Release pipeline outline

Implement or document the following release steps for a new version `X.Y.Z`:

1. Bump version in repo (using `scripts/bump_version.py` or equivalent).
2. Build DAZZLE CLI binaries for:
   - macOS arm64.
   - macOS amd64.
   - Windows amd64 (and optionally Linux).

3. Create a GitHub Release `vX.Y.Z` in the main repo and upload binaries.
4. Run Homebrew formula generator and commit updated `dazzle.rb` to `homebrew-dazzle`.
5. Generate winget manifests for `X.Y.Z` and open a PR to `microsoft/winget-pkgs`.
6. (Optional) Generate Scoop manifest and commit to `dazzle-scoop-bucket`.
7. Build and package VS Code extension:
   - Use GitHub Actions workflow and/or local `vsce` CLI.
   - Ensure extension is published or `.vsix` is attached to GitHub Release.

### 4.3. Documentation updates

1. Ensure the main DAZZLE README includes a “Installation” section with subsections:
   - macOS / Linux via Homebrew.
   - Windows via winget.
   - Windows via Scoop (optional).
   - WSL via Homebrew.
   - VS Code extension installation (Marketplace search and CLI `code --install-extension <publisher>.dazzle`).

2. Ensure each packaging subdirectory (`packaging/winget/`, `packaging/scoop/`) has a short `README.md` explaining the purpose and usage of its scripts.

---

## 5. Agent Behaviour Summary

When acting on this specification, you as the coding agent must:

1. Generate concrete code files and manifests wherever possible:
   - Ruby formula file (`dazzle.rb`).
   - YAML manifests for winget.
   - JSON manifest for Scoop.
   - GitHub Actions workflow YAML.
   - Helper Python scripts (`generate_homebrew_formula.py`, `generate_winget_manifest.py`, `generate_scoop_manifest.py`, `bump_version.py`).

2. Use clear placeholders (`<OWNER>`, `<publisher-id>`, `X.Y.Z`, `SHA256_FOR_*`) and, where feasible, provide command examples for the human to compute SHA256 hashes (e.g. `shasum -a 256 <file>`).

3. Maintain idempotence:
   - Running generators multiple times should overwrite or update existing files predictably.
   - Avoid generating conflicting duplicate files.

4. Prefer simple, explicit logic over clever abstractions:
   - Scripts should be easy for a human to read and modify.
   - Avoid unnecessary dependencies beyond the standard library where possible.

5. Avoid making network calls unless explicitly requested:
   - Assume that the human will paste in any required SHA hashes or URLs.
   - Design scripts to accept such values as command-line arguments or environment variables.

6. Provide inline comments in generated code where behaviour might be unclear, especially around versioning and file paths.

End of specification.
