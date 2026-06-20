# dazzle-python-models

A CodeQL **model pack** (data extensions) for the [Dazzle](https://github.com/manwithacat/dazzle)
framework's Python code. It teaches CodeQL's `py/url-redirection` (CWE-601) analysis
that Dazzle's canonical redirect guard —
`dazzle.http.runtime.auth.redirect_safety.is_safe_redirect_path()` — is a
**barrier guard**, so auth-route redirects that pass through it are not reported as
open-redirect false positives.

Published to GHCR as `ghcr.io/manwithacat/dazzle-python-models` and consumed by the
repository's advanced CodeQL setup via `.github/codeql/codeql-config.yml`.

## Contents

- `codeql-pack.yml` — pack manifest (`library: true`, `extensionTargets: codeql/python-all`).
- `models/redirect_safety.model.yml` — the `barrierGuardModel` data-extension row.

## Versioning

Published versions are **immutable**: once a version tag is published it is never
re-published with different content. Any change to the model is a new version —
bump `version:` in `codeql-pack.yml`, `codeql pack publish`, then update the pinned
version in the consuming `codeql-config.yml`. (Earlier published versions remain so
that older Dazzle tags reproduce against the exact model they shipped with.)

## License

The **contents of this pack** — the data-extension YAML and the manifest — are
licensed under the [MIT License](./LICENSE), the same terms as the Dazzle framework.

**This MIT grant covers only this pack's own source. It does not extend to the
CodeQL engine.** Loading or running these data extensions requires GitHub's CodeQL
CLI / CodeQL Action, which is **not** MIT-licensed — it is governed by the
[GitHub CodeQL Terms & Conditions](https://github.com/github/codeql-cli-binaries/blob/main/LICENSE.md)
(notably, CodeQL may be used to analyze open-source codebases and for academic
research, but other uses are restricted). Nothing in this repository grants any
right to use the CodeQL engine itself; consult GitHub's terms for that.
