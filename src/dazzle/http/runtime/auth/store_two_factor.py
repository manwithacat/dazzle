"""Two-factor half of the auth store (DD-014): factors, codes, challenges.

``TwoFactorStoreMixin`` is composed into ``AuthStore``. It owns:

* the TOTP secret on ``users.totp_secret`` — AES-256-GCM ciphertext under the
  enterprise-connection key (``connection_crypto``; ``DAZZLE_CONNECTION_SECRET``),
  never plaintext — and ``users.totp_last_step``, the last accepted time step, so a
  code is never accepted twice;
* hashed single-use recovery codes (``_dazzle_recovery_codes``) and hashed email
  one-time codes (``_dazzle_otp_codes``, 5-minute TTL, 3 attempts, single use);
* pending sign-in challenges (``_dazzle_2fa_challenges``): a short-lived token that is
  NOT a session — it opens nothing but the second-factor step, is stored only as a
  SHA-256 hash, dies after 5 wrong codes, 10 minutes, or one success. #1842 (WCAG
  2.2.1): "More time" pushes the deadline out by another 10 minutes, never past 30
  minutes from creation (``CHALLENGE_MAX_LIFETIME``);
* the second factor a session completed (``sessions.mfa_*``).

``TWO_FACTOR_DDL`` is the one DDL source for the three tables: the auth store's boot DDL
(``ensure_auth_core_tables``) and Alembic revision ``0027_two_factor_restore`` both run it.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from dazzle.http.runtime.auth.connection_crypto import decrypt_secret, encrypt_secret
from dazzle.http.runtime.auth.models import SecondFactorProof

TWO_FACTOR_DDL: tuple[str, ...] = (
    """
        CREATE TABLE IF NOT EXISTS _dazzle_otp_codes (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            method TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            used BOOLEAN DEFAULT FALSE
        )
    """,
    "CREATE INDEX IF NOT EXISTS idx_otp_user_method ON _dazzle_otp_codes(user_id, method)",
    "CREATE INDEX IF NOT EXISTS idx_otp_expires ON _dazzle_otp_codes(expires_at)",
    """
        CREATE TABLE IF NOT EXISTS _dazzle_recovery_codes (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            used_at TEXT,
            created_at TEXT NOT NULL
        )
    """,
    "CREATE INDEX IF NOT EXISTS idx_recovery_user ON _dazzle_recovery_codes(user_id)",
    """
        CREATE TABLE IF NOT EXISTS _dazzle_2fa_challenges (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            purpose TEXT NOT NULL,
            primary_method TEXT NOT NULL DEFAULT '',
            membership_id TEXT,
            redirect_to TEXT NOT NULL DEFAULT '/app',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            consumed BOOLEAN NOT NULL DEFAULT FALSE
        )
    """,
    "CREATE INDEX IF NOT EXISTS idx_2fa_challenges_user ON _dazzle_2fa_challenges(user_id)",
)

CHALLENGE_TTL = timedelta(minutes=10)
# #1842 (WCAG 2.2.1 Timing Adjustable): "More time" extends a live challenge by another
# CHALLENGE_TTL, but never past this hard cap from creation — the token stays short-lived.
CHALLENGE_MAX_LIFETIME = timedelta(minutes=30)
MAX_CODE_ATTEMPTS = 5
EMAIL_CODE_TTL = timedelta(minutes=5)
EMAIL_CODE_ATTEMPTS = 3
# Recovery-code alphabet: no I, O, 0 or 1 (unambiguous when read aloud or retyped).
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# A base32 TOTP secret as the pre-DD-014 runtime stored it, in plaintext.
_PLAINTEXT_TOTP_SECRET = re.compile(r"^[A-Z2-7]{16,64}=*$")

PURPOSE_VERIFY = "verify"  # the user has a factor: prove it to finish signing in
PURPOSE_ENROL = "enrol"  # enforce_for_roles, nothing enrolled: enrol to finish signing in
_PURPOSE_ATTEMPTS = "attempts"  # per-session attempt counter (step-up, enrolment)


@dataclass(frozen=True)
class TwoFactorChallenge:
    """A pending sign-in that still owes a second factor. Not a session."""

    token: str
    user_id: str
    purpose: str
    primary_method: str
    membership_id: str | None
    redirect_to: str
    attempts: int
    created_at: datetime
    expires_at: datetime

    @property
    def hard_deadline(self) -> datetime:
        """The latest this challenge can live, however often it is extended."""
        return self.created_at + CHALLENGE_MAX_LIFETIME

    @property
    def can_extend(self) -> bool:
        """Whether "More time" can still move the deadline (it is short of the cap)."""
        return self.expires_at < self.hard_deadline

    def extended_expiry(self, now: datetime) -> datetime | None:
        """The deadline "More time" would set, or None when it would gain nothing."""
        new = min(now + CHALLENGE_TTL, self.hard_deadline)
        return new if new > self.expires_at else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def factor_reference(user_id: str, method: str, qualifier: str = "") -> str:
    """Stable hashed reference for a user's factor (never derived from a secret)."""
    tail = f":{qualifier}" if qualifier else ""
    return _sha256(f"dazzle-mfa:{user_id}:{method}{tail}")


def generate_recovery_codes(count: int) -> list[str]:
    """``count`` codes shaped ``XXXX-XXXX`` from the unambiguous alphabet."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def normalise_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def is_plaintext_totp_secret(value: str | None) -> bool:
    """True for a TOTP secret a pre-DD-014 runtime stored unencrypted (bare base32).

    Revision ``0027`` encrypts those rows; AES-GCM ciphertext (base64 of nonce +
    ciphertext + tag) is never all upper-case base32.
    """
    return bool(value) and _PLAINTEXT_TOTP_SECRET.match(value or "") is not None


class TwoFactorStoreMixin:
    """Second-factor state on the auth store (DD-014). Composed into ``AuthStore``."""

    _execute: Any
    _execute_one: Any
    _execute_modify: Any
    _transaction: Any

    # -- TOTP ----------------------------------------------------------------

    def store_pending_totp_secret(self, user_id: UUID, secret: str) -> None:
        """Store a new TOTP secret (encrypted) before its first code is verified.

        No-op when TOTP is already enabled: re-enrolment needs ``disable_totp`` first.
        """
        self._execute_modify(
            "UPDATE users SET totp_secret = %s, totp_last_step = NULL, updated_at = %s "
            "WHERE id = %s AND COALESCE(totp_enabled, FALSE) = FALSE",
            (encrypt_secret(secret), datetime.now(UTC).isoformat(), str(user_id)),
        )

    def get_totp_secret(self, user_id: UUID) -> str | None:
        """The user's TOTP secret, decrypted; ``None`` when none is stored."""
        row = self._execute_one("SELECT totp_secret FROM users WHERE id = %s", (str(user_id),))
        enc = row.get("totp_secret") if row else None
        return decrypt_secret(enc) if enc else None

    def accept_totp_step(self, user_id: UUID, step: int) -> bool:
        """Record ``step`` as used; False if it (or a later step) was already accepted."""
        return bool(
            self._execute_modify(
                "UPDATE users SET totp_last_step = %s WHERE id = %s "
                "AND (totp_last_step IS NULL OR totp_last_step < %s)",
                (step, str(user_id), step),
            )
            == 1
        )

    def enable_totp(self, user_id: UUID) -> None:
        self._set_user_flags(user_id, "totp_enabled = TRUE")

    def disable_totp(self, user_id: UUID) -> None:
        self._set_user_flags(
            user_id, "totp_enabled = FALSE, totp_secret = NULL, totp_last_step = NULL"
        )

    def enable_email_otp(self, user_id: UUID) -> None:
        self._set_user_flags(user_id, "email_otp_enabled = TRUE")

    def disable_email_otp(self, user_id: UUID) -> None:
        self._set_user_flags(user_id, "email_otp_enabled = FALSE")

    def _set_user_flags(self, user_id: UUID, assignments: str) -> None:
        # ``assignments`` is one of the fixed literals above, never user input.
        self._execute_modify(
            f"UPDATE users SET {assignments}, updated_at = %s WHERE id = %s",  # nosemgrep
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    # -- recovery codes -------------------------------------------------------

    def replace_recovery_codes(self, user_id: UUID, codes: list[str]) -> None:
        """Store ``codes`` (hashed) as the user's only valid set."""
        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("DELETE FROM _dazzle_recovery_codes WHERE user_id = %s", (str(user_id),))
            for code in codes:
                cur.execute(
                    "INSERT INTO _dazzle_recovery_codes (user_id, code_hash, created_at) "
                    "VALUES (%s, %s, %s)",
                    (str(user_id), _sha256(normalise_recovery_code(code)), now),
                )
            cur.execute(
                "UPDATE users SET recovery_codes_generated = TRUE, updated_at = %s WHERE id = %s",
                (now, str(user_id)),
            )

    def consume_recovery_code(self, user_id: UUID, code: str) -> bool:
        """Spend one recovery code; False if it is wrong or already used."""
        return bool(
            self._execute_modify(
                "UPDATE _dazzle_recovery_codes SET used = TRUE, used_at = %s "
                "WHERE user_id = %s AND code_hash = %s AND used = FALSE",
                (
                    datetime.now(UTC).isoformat(),
                    str(user_id),
                    _sha256(normalise_recovery_code(code)),
                ),
            )
            == 1
        )

    def recovery_codes_remaining(self, user_id: UUID) -> int:
        row = self._execute_one(
            "SELECT COUNT(*) AS n FROM _dazzle_recovery_codes WHERE user_id = %s AND used = FALSE",
            (str(user_id),),
        )
        return int(row["n"]) if row else 0

    # -- email one-time codes -------------------------------------------------

    def issue_email_code(self, user_id: UUID, purpose: str = "email_otp") -> str:
        """A new 6-digit code for ``purpose``; earlier unused ones for it stop working."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = datetime.now(UTC)
        with self._transaction() as cur:
            cur.execute(
                "UPDATE _dazzle_otp_codes SET used = TRUE "
                "WHERE user_id = %s AND method = %s AND used = FALSE",
                (str(user_id), purpose),
            )
            cur.execute(
                "INSERT INTO _dazzle_otp_codes "
                "(user_id, code_hash, method, created_at, expires_at, max_attempts) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    str(user_id),
                    _sha256(code),
                    purpose,
                    now.isoformat(),
                    (now + EMAIL_CODE_TTL).isoformat(),
                    EMAIL_CODE_ATTEMPTS,
                ),
            )
        return code

    def check_email_code(self, user_id: UUID, code: str, purpose: str = "email_otp") -> bool:
        """Spend the latest live code for ``purpose`` if ``code`` matches it."""
        with self._transaction() as cur:
            cur.execute(
                "SELECT id, code_hash, attempts, max_attempts FROM _dazzle_otp_codes "
                "WHERE user_id = %s AND method = %s AND used = FALSE AND expires_at > %s "
                "ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                (str(user_id), purpose, datetime.now(UTC).isoformat()),
            )
            row = cur.fetchone()
            if row is None:
                return False
            if row["attempts"] >= row["max_attempts"]:
                cur.execute("UPDATE _dazzle_otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
                return False
            ok = hmac.compare_digest(row["code_hash"], _sha256(code))
            cur.execute(
                "UPDATE _dazzle_otp_codes SET attempts = attempts + 1, used = %s WHERE id = %s",
                (ok or row["attempts"] + 1 >= row["max_attempts"], row["id"]),
            )
            return ok

    # -- pending sign-in challenges ------------------------------------------

    def create_2fa_challenge(
        self,
        user_id: UUID,
        *,
        purpose: str,
        primary_method: str,
        membership_id: str | None,
        redirect_to: str,
    ) -> str:
        """Open a challenge for a proven primary sign-in; return its (unhashed) token."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._execute_modify(
            "INSERT INTO _dazzle_2fa_challenges (token_hash, user_id, purpose, primary_method, "
            "membership_id, redirect_to, created_at, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                _sha256(token),
                str(user_id),
                purpose,
                primary_method,
                membership_id,
                redirect_to,
                now.isoformat(),
                (now + CHALLENGE_TTL).isoformat(),
            ),
        )
        return token

    def get_2fa_challenge(self, token: str) -> TwoFactorChallenge | None:
        """The live challenge for ``token``, or None (unknown, expired, spent or locked)."""
        if not token:
            return None
        row = self._execute_one(
            "SELECT * FROM _dazzle_2fa_challenges WHERE token_hash = %s "
            "AND purpose IN (%s, %s) AND consumed = FALSE AND expires_at > %s AND attempts < %s",
            (
                _sha256(token),
                PURPOSE_VERIFY,
                PURPOSE_ENROL,
                datetime.now(UTC).isoformat(),
                MAX_CODE_ATTEMPTS,
            ),
        )
        if row is None:
            return None
        return TwoFactorChallenge(
            token=token,
            user_id=row["user_id"],
            purpose=row["purpose"],
            primary_method=row["primary_method"],
            membership_id=row.get("membership_id"),
            redirect_to=row["redirect_to"],
            attempts=int(row["attempts"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

    def extend_2fa_challenge(self, token: str) -> datetime | None:
        """Push a live challenge's deadline out (#1842, WCAG 2.2.1); the new deadline.

        None when the challenge is gone (unknown, expired, spent, locked) or already at
        ``CHALLENGE_MAX_LIFETIME``. Only the challenge moves: an emailed code keeps its
        own ``EMAIL_CODE_TTL`` (a code that travelled by email stays short-lived).
        """
        ch = self.get_2fa_challenge(token)
        if ch is None:
            return None
        now = datetime.now(UTC)
        new = ch.extended_expiry(now)
        if new is None:
            return None
        updated = self._execute_modify(
            "UPDATE _dazzle_2fa_challenges SET expires_at = %s "
            "WHERE token_hash = %s AND consumed = FALSE AND expires_at > %s AND attempts < %s",
            (new.isoformat(), _sha256(token), now.isoformat(), MAX_CODE_ATTEMPTS),
        )
        return new if updated == 1 else None

    def expired_2fa_challenge_user_id(self, token: str) -> str | None:
        """The user of a sign-in challenge that ran out of time (not spent or locked).

        Lets the sign-in page say the code expired and prefill the email (#1842).
        """
        if not token:
            return None
        row = self._execute_one(
            "SELECT user_id FROM _dazzle_2fa_challenges WHERE token_hash = %s "
            "AND purpose IN (%s, %s) AND consumed = FALSE AND expires_at <= %s AND attempts < %s",
            (
                _sha256(token),
                PURPOSE_VERIFY,
                PURPOSE_ENROL,
                datetime.now(UTC).isoformat(),
                MAX_CODE_ATTEMPTS,
            ),
        )
        return str(row["user_id"]) if row else None

    def fail_2fa_challenge(self, token: str) -> None:
        """Count a wrong code; the fifth kills the challenge."""
        self._bump_attempts(_sha256(token))

    def consume_2fa_challenge(self, token: str) -> bool:
        """Spend the challenge; False if another request already did (single use)."""
        return bool(
            self._execute_modify(
                "UPDATE _dazzle_2fa_challenges SET consumed = TRUE "
                "WHERE token_hash = %s AND consumed = FALSE AND expires_at > %s",
                (_sha256(token), datetime.now(UTC).isoformat()),
            )
            == 1
        )

    # -- per-session attempt limits (step-up, enrolment) ---------------------

    def session_attempts_locked(self, session_id: str, action: str) -> bool:
        row = self._execute_one(
            "SELECT attempts FROM _dazzle_2fa_challenges WHERE token_hash = %s AND expires_at > %s",
            (self._attempts_key(session_id, action), datetime.now(UTC).isoformat()),
        )
        return bool(row and int(row["attempts"]) >= MAX_CODE_ATTEMPTS)

    def fail_session_attempt(self, session_id: str, action: str, user_id: UUID) -> None:
        key = self._attempts_key(session_id, action)
        now = datetime.now(UTC)
        self._execute_modify(
            "INSERT INTO _dazzle_2fa_challenges (token_hash, user_id, purpose, created_at, "
            "expires_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (token_hash) DO NOTHING",
            (
                key,
                str(user_id),
                _PURPOSE_ATTEMPTS,
                now.isoformat(),
                (now + CHALLENGE_TTL).isoformat(),
            ),
        )
        self._bump_attempts(key)

    def clear_session_attempts(self, session_id: str, action: str) -> None:
        self._execute_modify(
            "DELETE FROM _dazzle_2fa_challenges WHERE token_hash = %s",
            (self._attempts_key(session_id, action),),
        )

    @staticmethod
    def _attempts_key(session_id: str, action: str) -> str:
        return _sha256(f"attempts:{action}:{session_id}")

    def _bump_attempts(self, token_hash: str) -> None:
        self._execute_modify(
            "UPDATE _dazzle_2fa_challenges SET attempts = attempts + 1, "
            "consumed = (attempts + 1 >= %s) WHERE token_hash = %s",
            (MAX_CODE_ATTEMPTS, token_hash),
        )

    # -- the session's second factor -----------------------------------------

    def record_session_second_factor(self, session_id: str, proof: SecondFactorProof) -> bool:
        """Record ``proof`` on an existing session (step-up)."""
        return bool(
            self._execute_modify(
                "UPDATE sessions SET mfa_method = %s, mfa_verified_at = %s, mfa_reference = %s "
                "WHERE id = %s",
                (proof.method, proof.verified_at.isoformat(), proof.reference, session_id),
            )
            == 1
        )
