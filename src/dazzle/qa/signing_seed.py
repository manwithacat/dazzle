"""Ephemeral cert + mock inbox provisioning for `dazzle qa trial` signing scenarios.

Provides three pieces of state needed before a signing trial run:
1. Signing cert chain env vars (SIGNING_CERT_PFX_B64, SIGNING_CERT_PASSWORD)
2. Token secret (SIGNING_TOKEN_SECRET)
3. Mock inbox JSON file containing seeded signing links for the persona's read_inbox tool

All provisioned state is per-trial-run and should be torn down on exit.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SeededDoc:
    """A document pre-seeded into the mock inbox for a trial run.

    ``token_state`` records how the token was minted (TR-51):

    - ``"fresh"`` — normal 72h-valid token; the persona can sign/decline.
    - ``"expired"`` — minted already-expired so the scenario exercises the
      "Invalid or expired link" page. The verifier reads this to expect
      the row to stay untouched instead of inferring from sign attempts.

    The state is harness-internal — it is deliberately NOT written to the
    mock inbox, so the persona discovers expiry the way a real signer
    would: by opening the link.

    ``validator_reject`` (#1382) records that this row's id was armed in
    ``DAZZLE_QA_SIGNING_REJECT_IDS`` before boot, so the project-side
    ``signing_validator`` rejects the signature. Like ``token_state`` it
    fixes the verifier's expectation (row stays ``sent``) rather than
    inferring "signed" the moment the persona attempts a signature — without
    it a successful rejection mis-scores as a failure and the persona's
    "no authority check" verdict reads as a false-critical.
    """

    entity: str
    id: str
    token: str
    signing_url: str
    signatory_email: str
    token_state: str = "fresh"
    validator_reject: bool = False


@dataclass
class SigningSeedContext:
    """All ephemeral state provisioned for one trial run.

    Not frozen so callers can accumulate seeded_docs after initial construction
    (e.g. Task 10 integration rebuilds the context with docs added incrementally).

    ``signable_ids`` (#1382) maps signable-entity name → the UUID pre-generated
    *before* boot, so the seed can insert the row under a known id and that same
    id can be armed in ``DAZZLE_QA_SIGNING_REJECT_IDS`` (set pre-boot, the only
    point the subprocess env is fixed). ``validator_reject`` flags that the
    reject env var was armed for this run.
    """

    env: dict[str, str]
    inbox_path: Path
    seeded_docs: list[SeededDoc] = field(default_factory=list)
    signable_ids: dict[str, str] = field(default_factory=dict)
    validator_reject: bool = False


def mint_ephemeral_cert_env(tmpdir: Path, *, project_name: str) -> dict[str, str]:
    """Mint a one-shot ECDSA P-256 cert chain + token secret.

    Uses :func:`dazzle.signing.cert.generate_cert_chain_b64` to produce a
    PKCS#12 bundle (base64-encoded) plus a random password.  A separate
    URL-safe token secret is generated for HMAC signing of trial tokens.

    Args:
        tmpdir: Scratch directory for the trial run (not used for file output
            here — cert is returned as base64 — but accepted for API symmetry
            with :func:`write_mock_inbox`).
        project_name: Organisation name embedded in the cert's X.509 subject.

    Returns:
        Dict with keys ``SIGNING_CERT_PFX_B64``, ``SIGNING_CERT_PASSWORD``,
        and ``SIGNING_TOKEN_SECRET``, ready to merge into a subprocess env.
    """
    from dazzle.signing.cert import generate_cert_chain_b64

    pfx_b64, password_str = generate_cert_chain_b64(project_name)
    return {
        "SIGNING_CERT_PFX_B64": pfx_b64,
        "SIGNING_CERT_PASSWORD": password_str,
        "SIGNING_TOKEN_SECRET": secrets.token_urlsafe(48),
    }


def write_mock_inbox(tmpdir: Path, docs: list[SeededDoc]) -> Path:
    """Serialize *docs* to a JSON file the persona's ``read_inbox`` tool reads.

    Args:
        tmpdir: Directory in which to write ``mock_inbox.json``.
        docs: Pre-seeded documents to expose to the persona.

    Returns:
        Path to the written ``mock_inbox.json`` file.
    """
    inbox_path = tmpdir / "mock_inbox.json"
    inbox_path.write_text(
        json.dumps(
            [
                {
                    "entity": d.entity,
                    "id": d.id,
                    "token": d.token,
                    "signing_url": d.signing_url,
                    "signatory_email": d.signatory_email,
                }
                for d in docs
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    return inbox_path
