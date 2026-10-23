# DD-018: Auth mailers take one message object, with a framework-rendered default

```yaml
# Machine-readable header (keep keys stable — greppable by agents)
id: DD-018
status: PARKED
issues: [1842]
adrs: [ADR-0003, ADR-0005]
decided: 2026-10-23
decided_at_sha: e507ba02f
parent: null
```

## One-line intent

The auth mailer Protocols (`src/dazzle/http/runtime/auth/mailer.py`) pass bare
keyword arguments (`send_magic_link(*, to_email, link_url)`), so the framework
cannot add a field (the link's expiry, #1842 WCAG 2.2.1) without breaking every
host mailer. We know the shape the contract should have. We are not changing it
until a consumer needs a field the current signature cannot carry.

## Plan (what we already concluded)

**Industry consensus (researched 2026-10-23).** Auth.js, Better Auth, Laravel and Supabase
share three traits:

1. **Expiry is owned centrally by the token issuer.** Examples: Auth.js `maxAge`,
   Better Auth `expiresIn`, Laravel `auth.passwords.*.expire`. Mail code never sets it.
2. **Message content is separate from transport.** Either the framework ships a default
   message the host can override (Laravel's default `ResetPassword` notification plus
   `toMailUsing`; Supabase's hosted templates with `{{ .ConfirmationURL }}` and similar),
   or the framework gives the host everything needed to write one.
3. **The sender receives one structured object.** Auth.js `sendVerificationRequest(params)`
   gets `{ identifier, url, token, expires, provider, theme, request }`, which let it add
   `expires` and `theme` without signature breaks.

Dazzle already satisfies (1): `EMAIL_MAGIC_LINK_TTL` in `auth/magic_link.py`, and
`CHALLENGE_TTL` for two-factor. It misses (2) and (3). It is also inconsistent:
`OneTimeCodeMailer.send_one_time_code` receives `ttl_minutes`, while the magic-link,
verification and invitation mailers receive nothing about expiry.

**The design, one clean break (ADR-0003) across all four mailers:**

- Each Protocol method takes a single Pydantic message (Style Guide: Pydantic for data
  crossing module boundaries):
  - `send_magic_link(message: MagicLinkMessage)`
  - `send_verification_email(message: VerificationMessage)`
  - `send_invitation(message: InvitationMessage)`
  - `send_one_time_code(message: OneTimeCodeMessage)`
- Common fields: `to_email`, `product_name` (from `auth/product_name.py`), `expires_at`
  (aware UTC datetime) and `ttl_minutes`. Kind-specific fields: `link_url`, `accept_url`
  plus `org_name`, `code`.
- Each message also carries a **framework-rendered default** `subject`, `text` and `html`,
  built from the same fields.
  - A transport-only host (SES, SMTP) sends those as they are.
  - A host with its own brand voice renders from the fields and ignores the defaults.
  - Both keep working when a field is added.
- The defaults state the expiry ("This link expires in 15 minutes"). That closes the
  #1842 magic-link item for every host that uses them.
- `LogMailer` logs the message summary and keeps today's never-log-the-code rule for
  one-time codes in production.
- Protocol selection is unchanged: `app.state.magic_link_mailer` plus the
  `isinstance(…, capability)` fallback to `LogMailer` (ADR-0005, no new singleton).

**Counter-priors (will not do even when forced):**

- No template engine or per-host template files in the framework. Defaults are built
  in Python, like the rest of the typed render substrate (ADR-0023). Host overrides live
  in the host's mailer, not in framework config.
- No compatibility shim that accepts both the keyword and the message signature
  (ADR-0003).
- No extra positional or keyword parameters on the current signatures. Adding
  `ttl_minutes=` to `send_magic_link` would break hosts now and again next time.

## Reopen when (consumer force)

1. **Named consumer**: cyfuture or AegisMark asks for the expiry (or another field, such as
   the product name or the requesting IP) inside a magic-link, verification or invitation
   email. Or a consumer's WCAG / regulatory audit fails on the email body.
2. **Evidence of host workaround**: a host mailer that imports `EMAIL_MAGIC_LINK_TTL` or
   re-derives product branding to fill a gap the message would carry.
3. **Acceptance that unblocks**: the four Protocols take message objects whose default
   `text`/`html` state the expiry. cyfuture's and AegisMark's mailers are migrated in the
   same release (CHANGELOG `### Agent Guidance` bullet, plus an upgrade note naming each
   method).

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer and this DD path.
3. Implement against the plan above. Open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- `EMAIL_MAGIC_LINK_TTL` and `email_magic_link_ttl_minutes()` in `auth/magic_link.py`.
  Both issuance routes use the constant, and `/login/sent` states the expiry
  (#1842 partial, 2026-10-23). Hosts can already import the constant.
- `OneTimeCodeMailer` already receives `ttl_minutes` (DD-014).
- The capability-checked mailer lookup (`_capable_mailer`) and the `LogMailer` fallback.

## Explicitly out of scope until force

- HTML email theming and brand assets in the framework's default bodies, beyond plain,
  accessible markup.
- Localisation of the default bodies.
- A delivery-status or bounce feedback channel. The Protocols remain fire-and-forget.

## Trail

| Date | Event |
|------|--------|
| 2026-10-23 | Parked (this DD), from #1842's magic-link expiry item |
