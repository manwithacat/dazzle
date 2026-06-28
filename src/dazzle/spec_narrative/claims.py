"""Framework value-claim catalogue: model + loader (claims.toml)."""

import tomllib
from pathlib import Path

from pydantic import BaseModel

_CLAIMS_PATH = Path(__file__).parent / "claims.toml"


class Claim(BaseModel):
    """A curated, stakeholder-facing statement about a framework guarantee."""

    id: str
    detector: str
    group: str
    audience: str
    claim: str
    evidence: str


def load_claims(path: Path | None = None) -> list[Claim]:
    """Load and validate the claim catalogue from ``claims.toml``."""
    data = tomllib.loads((path or _CLAIMS_PATH).read_text(encoding="utf-8"))
    return [Claim(id=claim_id, **body) for claim_id, body in data.items()]
