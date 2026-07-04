"""Console-domain regression gates — no browser needed.

1. Every ``dz-*`` class used in the registry's canonical HTML has a rule
   in the built bundle (the "no unstyled published markup" contract).
2. The committed gallery CSS equals a fresh ``build_css()`` — catches
   editing component CSS without rebuilding the gallery.
3. The prefix transform is total: no ``dz-`` survives ``--prefix ax-``.
"""

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "site"))

from build import build_css, build_js  # noqa: E402
from registry import HYPERPARTS  # noqa: E402

# hx-* attributes that make a server request (each REQUIRES a declared
# Exchange). hx-confirm is a client affordance (no round-trip) → exempt.
_REQUEST_ATTR_RE = re.compile(r'hx-(get|post|put|patch|delete)="([^"]+)"')

# Structural wrappers that intentionally carry no rule of their own
# (styled via inheritance / parent selectors). Additions here need a
# comment in the component's CSS explaining why.
SEMANTIC_ONLY = {
    "dz-alert__body",
    "dz-empty-state__description",
}


def _used_classes() -> set[str]:
    used: set[str] = set()
    for c in HYPERPARTS:
        for m in re.finditer(r'class="([^"]+)"', c.partial):
            used.update(cls for cls in m.group(1).split() if cls.startswith("dz-"))
    return used


def test_every_registry_class_has_a_rule() -> None:
    # Registry partials carry the dz- SOURCE form; check against the dz-
    # build (the published default is unprefixed, but the source is dz-).
    css = build_css("dz-")
    missing = sorted(
        cls for cls in _used_classes() if f".{cls}" not in css and cls not in SEMANTIC_ONLY
    )
    assert not missing, (
        f"registry HTML uses classes with no rule in the bundle: {missing}. "
        "Style them or (if genuinely structural) add to SEMANTIC_ONLY with a comment."
    )


def test_semantic_only_list_is_not_stale() -> None:
    css = build_css("dz-")
    stale = sorted(cls for cls in SEMANTIC_ONLY if f".{cls}" in css)
    assert not stale, f"now styled — remove from SEMANTIC_ONLY: {stale}"


def test_committed_dist_is_current() -> None:
    """dist/ is committed so jsDelivr can serve it straight from the repo
    at any tag (https://cdn.jsdelivr.net/gh/manwithacat/hatchi-maxchi@TAG/dist/…).
    A stale committed dist would be served to CDN users — fail loudly."""
    css = (PKG / "dist" / "hatchi-maxchi.css").read_text(encoding="utf-8")
    js = (PKG / "dist" / "hatchi-maxchi.js").read_text(encoding="utf-8")
    assert css == build_css() and js == build_js(), (
        "dist/ is stale — run `python build.py` and commit (CDN users get the committed files)"
    )
    for font in ("geist-var.woff2", "geist-mono-var.woff2", "OFL.txt"):
        assert (PKG / "dist" / "fonts" / font).exists(), f"dist/fonts/{font} missing"


def test_committed_gallery_css_is_current() -> None:
    committed = (PKG / "site" / "hatchi-maxchi.css").read_text(encoding="utf-8")
    assert committed == build_css(), (
        "site/hatchi-maxchi.css is stale — re-run the gallery build "
        "(in the Dazzle monorepo: python packages/hatchi-maxchi/site/build_site.py)"
    )


def test_committed_gallery_js_carries_current_controllers() -> None:
    committed = (PKG / "site" / "hatchi-maxchi.js").read_text(encoding="utf-8")
    assert build_js() in committed, (
        "site/hatchi-maxchi.js does not embed the current controllers — re-run the gallery build"
    )


def test_gallery_regenerates_byte_identically(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The committed gallery must equal a fresh standalone rebuild — the
    boundary acceptance test (Phase 3): the split repo regenerates its own
    docs with zero Dazzle code, and what it regenerates is what's shipped."""
    import build_site

    build_site.build(tmp_path)
    for name in ("index.html", "hatchi-maxchi.css", "hatchi-maxchi.js"):
        fresh = (tmp_path / name).read_text(encoding="utf-8")
        committed = (PKG / "site" / name).read_text(encoding="utf-8")
        assert fresh == committed, (
            f"site/{name} is stale or the build is nondeterministic — "
            "re-run python site/build_site.py and commit"
        )


def test_prefix_transform_is_total() -> None:
    css = build_css(prefix="ax-")
    js = build_js(prefix="ax-")
    # `dz-` survives ONLY in `--dz-*` custom-property names (internal, never
    # reprefixed — see build.apply_prefix). Everything else must be renamed.
    css_no_customprops = re.sub(r"--dz-[a-z0-9*-]*", "", css)
    assert "dz-" not in css_no_customprops, "class/attr/keyframe dz- leaked through --prefix ax-"
    assert "dz-" not in js
    assert ".ax-button" in css and ".ax-alert" in css
    assert "ax-command" in js and "data-ax-native-confirm" in js


def test_default_prefix_is_unprefixed() -> None:
    # HM ships clean/unprefixed by default (developer engagement); a consumer
    # (Dazzle) applies its own namespace at ingest via build_css("dz-").
    css = build_css()
    assert ".button" in css and ".badge" in css
    assert ".dz-button" not in css and "data-dz-tone" not in css


def test_dazzle_namespace_roundtrips() -> None:
    # The production consumption path: build_css("dz-") is the dz- form Dazzle
    # ingests (byte-identical to the pre-flip artifact).
    css = build_css("dz-")
    assert ".dz-button" in css and "data-dz-tone" in css


# ── Hypermedia exchange contracts (the "partial + endpoint contract"
#    concept) — every request a partial makes must be a DECLARED contract,
#    and every declared contract must correspond to a real affordance. ──


def test_every_request_affordance_has_a_declared_exchange() -> None:
    """A partial that makes an hx request it doesn't declare is an
    undocumented contract — an agent consuming the component can't know
    what endpoint to build. Fail loudly."""
    gaps = []
    for c in HYPERPARTS:
        declared = {(e.method.upper(), e.endpoint) for e in c.exchanges}
        for method, _url in _REQUEST_ATTR_RE.findall(c.partial):
            # markup uses mock endpoints; exchanges declare the REAL contract
            # — so we require one exchange per request METHOD, not per URL.
            if not any(m == method.upper() for m, _ in declared):
                gaps.append(f"{c.id}: hx-{method} in markup with no declared Exchange")
    assert not gaps, (
        "components make requests they don't declare as Exchange contracts:\n  " + "\n  ".join(gaps)
    )


def test_no_orphan_exchange_without_an_affordance() -> None:
    """An Exchange with no matching hx-* control in the markup is a stale
    contract — the partial doesn't actually make that request."""
    orphans = []
    for c in HYPERPARTS:
        methods_in_markup = {m.upper() for m, _ in _REQUEST_ATTR_RE.findall(c.partial)}
        for e in c.exchanges:
            if e.method.upper() not in methods_in_markup:
                orphans.append(f"{c.id}: Exchange {e.method} {e.endpoint} has no hx-* affordance")
    assert not orphans, "stale Exchange contracts (no affordance in markup):\n  " + "\n  ".join(
        orphans
    )


def test_exchange_fields_are_populated() -> None:
    """Each contract must actually document trigger / response / swap — a
    blank field is an undocumented contract masquerading as a documented one."""
    thin = [
        f"{c.id}: {e.method} {e.endpoint}"
        for c in HYPERPARTS
        for e in c.exchanges
        if not (e.trigger.strip() and e.response.strip() and e.swap.strip())
    ]
    assert not thin, "Exchange contracts with empty trigger/response/swap:\n  " + "\n  ".join(thin)


def test_interactive_htmx_components_declare_contracts() -> None:
    """A component tagged htmx that makes requests must carry exchanges —
    guards against the tag drifting from reality."""
    missing = [
        c.id
        for c in HYPERPARTS
        if "htmx" in c.tags and _REQUEST_ATTR_RE.search(c.partial) and not c.exchanges
    ]
    assert not missing, f"htmx components making requests but declaring no Exchange: {missing}"


_DATA_ATTR_RE = re.compile(r"\bdata-([a-z][a-z0-9-]*)=")


def test_data_attributes_follow_the_namespace_grammar() -> None:
    """Component data-attributes must be namespaced — `data-dz-*` (framework)
    or `data-hm-*` (gallery). This stops an agent inventing inconsistent
    alternatives like `data-color`/`data-type`/`data-style` (agent-review
    naming-contract). Visual variants use `data-dz-variant`, semantic tone
    `data-dz-tone`, size `data-dz-size`."""
    offenders: dict[str, set[str]] = {}
    for c in HYPERPARTS:
        for m in _DATA_ATTR_RE.finditer(c.partial):
            name = m.group(1)
            if not name.startswith(("dz-", "hm-")):
                offenders.setdefault(c.id, set()).add("data-" + name)
    assert not offenders, f"non-grammar data-attributes (use data-dz-*/data-hm-*): {offenders}"
