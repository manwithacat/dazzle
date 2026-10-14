# DD-012: String translation catalogue (`.po`/`.mo`, `translate`, `dazzle i18n`)

```yaml
id: DD-012
status: PARKED
issues: [955]
adrs: [0023, 0057]
decided: 2026-10-14
decided_at_sha: 3844ec995a00a9d93ed93a277dce15562e9590dc
parent: flense-programme
```

## One-line intent

Dazzle does not translate UI strings. The message catalogue, the `.po`/`.mo`
loader, the Babel format helpers and the `dazzle i18n` CLI were removed in
flense ship AB because no consumer ships a catalogue and no renderer ever
looked a string up; date/number/currency **presentation** (the display-locale
profile) is a separate, live concern and stays.

## Plan (what we already concluded)

The removed design (#955 cycles 2–5), restorable from `3844ec995`:

- `src/dazzle/i18n/__init__.py` — process-global `MessageCatalogue`
  (`register_translations`, `get_catalogue`, `translate(locale, msgid, **kw)`)
  with primary-subtag fallback (`en-GB` → `en`) and identity fallback on miss;
  `locale_ctxvar` / `get_current_locale()` set by `LocaleMiddleware`.
- `src/dazzle/i18n/loader.py` — boot-time discovery of
  `locale/<locale>/LC_MESSAGES/messages.{mo,po}` (Babel `read_po`/`read_mo`),
  called from `DazzleBackendApp._load_i18n_translations`; `compile_po_to_mo`.
- `src/dazzle/i18n/babel_format.py` — `format_date|datetime|time|number|decimal|currency`
  keyed off the request locale, degrading without Babel.
- `src/dazzle/cli/i18n.py` — `dazzle i18n extract|init|compile|stats`.
- `i18n = ["babel>=2.13"]` optional extra.

When forced, restore along these lines but **wire a caller first**: the
pre-removal catalogue had no renderer calling `translate`, so the typed
Fragment renderers (ADR-0023) need a translation seam — e.g. a `RenderContext`
locale plus a `t()` helper used by the shell, form and table chrome — before
the catalogue earns its keep. Counter-priors, even when forced:

- **Never** let the browser language drive date/number/currency presentation;
  that stays the tenant's `DisplayLocaleProfile` (#1597).
- **No** per-tenant catalogue machinery in the framework; namespaced msgids in
  project code if a consumer needs it.
- **No** LLM call that writes or edits `.po` content for the user's DSL
  (Authoring vs API boundary, #1222).

## Reopen when (consumer force)

1. **Named consumer** — AegisMark, cyfuture or pennydreadful ships a `locale/`
   tree with `.po` files, or files an issue asking for a non-English UI.
2. **Evidence of a host workaround** — a consumer monkey-patching renderer
   strings or carrying its own gettext layer.
3. **Acceptance that unblocks** — one consumer page renders its chrome in a
   second language from a project catalogue.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- `LocaleMiddleware` is mounted (flense ship AB): it binds
  `request.state.locale` (cookie → `Accept-Language` → `[i18n] default`) and
  the tenant's `DisplayLocaleProfile` from `locale.*` params + per-tenant config.
- `POST /_dazzle/i18n/locale` writes the `dazzle_locale` cookie the middleware reads.
- `[i18n]` in dazzle.toml (`default`, `supported`, `cookie_name`) stays — the
  middleware and the cookie route read it.

## Explicitly out of scope until force

- A locale-switcher UI primitive.
- Right-to-left layout.
- Pluralisation / ICU message format.

## Trail

| Date | Event |
|------|--------|
| 2026-10-14 | Parked (this DD); catalogue, loader, Babel helpers, `dazzle i18n` CLI and the `i18n` extra removed in flense ship AB |
