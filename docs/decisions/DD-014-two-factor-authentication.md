# DD-014: Two-factor authentication — parked until a consumer requires MFA

```yaml
id: DD-014
status: PARKED
issues: [829, 838]
adrs: [0057, 0044, 0047, 0017, 0003]
decided: 2026-10-15
decided_at_sha: 229226a8875324aba49a3b8b927fcc513e830968
parent: flense-programme
```

## One-line intent

Two-factor authentication (TOTP enrolment, an email one-time code, single-use
recovery codes, the `/2fa/setup`, `/2fa/settings` and `/2fa/challenge` pages and
the `/auth/2fa/*` API) was mounted for every app, but no consumer enrolled a
user: no checkout links to `/2fa/*`, and none configures the IR-only
`SecurityConfig.two_factor` (there was never a `security:` DSL block; the
config could only be set in Python). Flense ship AG (ADR-0057, operator
decision 2026-10-15, plan §9.4 decision 3) removed it: about 2.2k lines of
`src`, 3.2k of tests, the `segno` dependency and the two tables. Password,
magic-link and social-OAuth sign-in, sessions, CSRF binding and logout are a
different plane and stay.

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`229226a8875324aba49a3b8b927fcc513e830968`, the parent of flense ship AG);
`git show 229226a88:<path>` returns every file below.

**Primitives** (`src/dazzle/http/runtime/`):
- `totp.py` — pure-Python RFC 6238 (HMAC-SHA1, 6 digits, 30 s step,
  `verify_totp(..., window=1)` accepts one step of drift each way,
  constant-time compare), `generate_totp_secret` (20 random bytes, base32) and
  `get_totp_uri` (`otpauth://totp/<issuer>:<email>?secret=…`).
- `otp_store.py` — `OTPStore`: 6-digit email codes stored as SHA-256 hashes in
  `_dazzle_otp_codes` with `ttl=300`, `max_attempts=3`, single use, and a new
  code invalidating the user's earlier unused codes for the same method.
- `recovery_codes.py` — `generate_recovery_codes(count=8)`: `XXXX-XXXX` from an
  unambiguous alphabet (no I, O, 0, 1); `RecoveryCodeStore` keeps SHA-256 hashes
  (dashes stripped, upper-cased) in `_dazzle_recovery_codes`, each usable once;
  regeneration replaces the set.

**State on `users`.** Four columns, still in the schema (see below):
`totp_secret`, `totp_enabled`, `email_otp_enabled`,
`recovery_codes_generated`. `UserRecord.two_factor_enabled` was
`totp_enabled or email_otp_enabled`; `AuthStore` carried a `TwoFactorMixin`
(`enable_totp`, `disable_totp`, `enable_email_otp`, `disable_email_otp`,
`set_recovery_codes_generated`, `get_totp_secret`) and
`store_totp_secret_pending` for enrolment before the first code verified.

**Routes.** `auth/routes_2fa.py` (`create_2fa_routes`, prefix `/auth/2fa`):
`POST /setup/totp` (secret + QR as a `data:` PNG rendered server-side by
`segno`, never a third-party QR service, #829), `POST /verify/totp` (confirm
enrolment, mint recovery codes once), `POST /setup/email-otp`,
`POST /challenge` (send an email code), `POST /verify` (TOTP, email code or
recovery code against the pending session, then a fresh session, cookie and
CSRF secret, pre-auth id deleted for #1198), `POST /recovery`,
`POST /recovery/regenerate`, `GET /status`, `DELETE /totp`,
`DELETE /email-otp`. `auth/two_factor_form_routes.py` added the no-JS form
posts `/auth/2fa/verify/submit` and `/auth/2fa/email-otp-send/submit`.
`auth/leftover_2fa_code.py` and the `leftover_honest_2fa_mode` /
`leftover_honest_2fa_sent` helpers held the stay-put 400 for junk `?mode=`,
`?sent=` and codes. The `twofa_limit` rate limit (`DAZZLE_RATE_LIMIT_2FA`,
5/min standard, 3/min strict) guarded the verify endpoints.

**Login hook.** JSON `POST /auth/login` answered `{"status": "2fa_required",
"methods": [...], "session_token": <pending>}` and form
`POST /auth/login/password` redirected to `/2fa/challenge?session=<pending>`
when `user.two_factor_enabled`; no cookie was set until verification.

**UI.** Typed-Fragment views in `auth/two_factor_views.py`
(`build_2fa_setup_view`, `build_2fa_settings_view`, `build_2fa_challenge_view`)
served by `site_routes.create_auth_page_routes` (setup and settings behind
`get_auth_context`, challenge public), with client scripts
`page/runtime/static/js/dz-2fa-setup.js` and `dz-2fa-settings.js`. The chrome
is the HaTchi-MaXchi `two-factor` Hyperpart, which stays in the HM gallery
(HM is exempt from the flense; `test_hyperpart_fleet_coverage` marks it exempt
until a Dazzle emitter returns).

**Config.** `dazzle.core.ir.security.TwoFactorConfig` (`enabled`, `methods`
of `TwoFactorMethod.EMAIL_OTP | TOTP`, `recovery_code_count=8`) on
`SecurityConfig.two_factor` (#838), threaded into `create_2fa_routes` by
`AuthSubsystem`. Nothing set it from DSL or `dazzle.toml`.

**Schema.** `_dazzle_otp_codes` and `_dazzle_recovery_codes` were dropped by
Alembic revision `0024_flense_park_two_factor`, whose `downgrade` holds the
exact DDL. Re-add them with a new revision (ADR-0017), register them in
`dazzle.db.artifact_registry` (ADR-0047) and regenerate
`FRAMEWORK_SCHEMA_SNAPSHOT`. The four `users` columns were kept pending a
separate operator decision; if they are dropped before a reopen, the restore
re-adds them in the same revision.

**Counter-priors (hold even when forced).**
- Make the opt-in a declared surface (a `security:` / `[auth]` setting a
  consumer writes), not an IR default nobody can reach from DSL.
- A pending-challenge token must not be an ordinary authenticated session. The
  removed code minted a real `sessions` row (10 minutes on the JSON path, the
  default seven days on the form path) and trusted `validate_session` on it;
  restore with a distinct, short-lived, non-authenticating challenge token.
- Encrypt `totp_secret` at rest; the removed store kept it in plaintext despite
  its docstring.
- Never send a TOTP secret or QR payload to a third party; render QR locally.
- Never echo a code, never accept a code twice, never skip the attempt limit.
- Regenerating recovery codes invalidates the old set; show codes once.

## Reopen when (consumer force)

1. **Named consumer** — a consumer declares two-factor sign-in in its app
   configuration (the restored equivalent of `security: two_factor`), **or** a
   consumer's assurance pack (flense Phase 4) names MFA as a required control.
   AegisMark (school staff accounts holding pupil data) is the likely candidate.
2. **Evidence** — the requirement is written in the consumer's repo (assurance
   pack, DPIA or security policy), not inferred.
3. **Acceptance that unblocks** — in the consumer's staging, a user enrols an
   authenticator, signs out, signs in with password + TOTP, recovers with a
   recovery code, and a wrong or replayed code is refused; the challenge token
   cannot be used as a session cookie.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on #829 / #838 with the consumer + this DD path.
3. Restore from `229226a88` the factors the consumer needs (TOTP + recovery by
   default; email OTP only if asked), with its tables (new revision), the login
   hook, the pages, `segno`, and tests; apply the counter-priors above.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- The code and tests at `229226a8875324aba49a3b8b927fcc513e830968` (use the
  SHA; the `archive` branch holds retired docs, not this code).
- Kept in the tree: password, magic-link and social-OAuth sign-in, sessions and
  the session-fixation defence (#1198), session-bound CSRF, `/auth/logout`, the
  rate-limit profiles (`auth`, `api`, `upload`, `download`), the `users` 2FA
  columns, and the HM `two-factor` Hyperpart and its gallery entry.

## Explicitly out of scope until force

- WebAuthn / passkeys, SMS codes, push approval, "remember this device",
  admin-enforced per-org MFA policy. A consumer asking for these gets a new
  plan, not this restore.
- Making 2FA mandatory for every app by default.

## Trail

| Date | Event |
|------|--------|
| 2026-10-15 | Parked (this DD); two-factor auth removed in flense ship AG, tables dropped by `0024_flense_park_two_factor` |
