@../AGENTS.md

# Claude Code adapter

Repository instructions and operator playbooks live in `AGENTS.md` and
`.agents/skills/`. Files under `.claude/commands/` and `.claude/skills/` are
discovery shims; follow the linked portable skill.

Claude-specific permissions and hooks are configured in `.claude/settings.json`;
hook scripts and their contract are documented in `.claude/hooks/README.md`.

## Claude runtime notes

- The SessionStart hook prepends `.venv/bin` to PATH for every Bash call, so
  bare `dazzle`, `ruff`, `mypy`, `pytest`, `python` are the repo's uv venv.
  Outside this harness (or if the hook failed) prefix with `uv run`.
- This machine also carries pyenv shims and a stale `~/.local/bin/dazzle`
  wrapper (pyenv `dazzle-dev`, Python 3.12). If `python --version` is not the
  `.python-version` pin, the PATH fix did not apply — use `uv run`.
- The repo root is not a Dazzle project: `dazzle validate|lint` need
  `-p examples/<app>`.
- Postgres 17 and Redis run as brew services. Postgres-backed tests are opt-in
  via `TEST_DATABASE_URL`, which `tests/conftest.py` loads from `.env`; do not
  export a host `DATABASE_URL` for the test suite (conftest strips it).
