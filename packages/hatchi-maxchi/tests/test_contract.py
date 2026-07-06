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

from blueprints import BLUEPRINTS  # noqa: E402
from build import build_css, build_js  # noqa: E402
from registry import HYPERPARTS  # noqa: E402

# hx-* attributes that make a server request (each REQUIRES a declared
# Exchange). hx-confirm is a client affordance (no round-trip) → exempt.
_REQUEST_ATTR_RE = re.compile(r'hx-(get|post|put|patch|delete)="([^"]+)"')

# Extension affordances that request OUTSIDE htmx (a raw fetch on a
# controller seam) — attribute → HTTP method. The inline-edit extension
# commits `PUT {data-dz-grid-edit-url}/{id}`; declaring the attribute in a
# partial is making that request, so it needs (and satisfies) an Exchange.
_EXTENSION_REQUEST_ATTRS = {"data-dz-grid-edit-url": "PUT"}


def _methods_in_markup(partial: str) -> set[str]:
    methods = {m.upper() for m, _ in _REQUEST_ATTR_RE.findall(partial)}
    for attr, method in _EXTENSION_REQUEST_ATTRS.items():
        if attr + "=" in partial:
            methods.add(method)
    return methods


# Structural wrappers that intentionally carry no rule of their own
# (styled via inheritance / parent selectors). Additions here need a
# comment in the component's CSS explaining why.
SEMANTIC_ONLY = {
    "dz-alert__body",
    "dz-empty-state__description",
    # tab panel container: identity for the controller + a swap target; its
    # visibility rides the native `hidden` attribute, so it carries no rule.
    "dz-tabs__panel",
    # the select-column <col> in the grid's colgroup: a structural marker so
    # the resize/visibility extensions can address data cols by exclusion —
    # the table stays layout:auto, so the col itself needs no width rule.
    "dz-table-col-select",
}


def _all_partials():
    """Every published markup string — Hyperpart demos AND Blueprint pages
    (a typo'd class in either ships unstyled to every consumer)."""
    for c in HYPERPARTS:
        yield c.id, c.partial
    for bp in BLUEPRINTS:
        yield f"blueprint:{bp.id}", bp.partial


def _used_classes() -> set[str]:
    used: set[str] = set()
    for _pid, partial in _all_partials():
        for m in re.finditer(r'class="([^"]+)"', partial):
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


def test_public_css_props_follow_the_prefix() -> None:
    """Custom-property KNOBS that consumers set (inline in snippets, or
    server-emitted like the list row floor) are public API — they must
    follow the namespace prefix exactly like classes/data-attributes/
    keyframes do. Internal tokens keep their source names (private).

    The 2026-07-06 case: the progress demo showed
    `style="--dz-progress-value:62%"` against an otherwise unprefixed
    gallery — the one place the source namespace leaked into the
    published artifact."""
    from build import PUBLIC_CSS_PROPS

    stripped = build_css("")
    renamed = build_css("ax-")
    kept = build_css("dz-")
    for prop in PUBLIC_CSS_PROPS:
        bare = prop.removeprefix("--dz-")
        assert f"--dz-{bare}" not in stripped, f"{prop} must strip with the prefix"
        assert f"--{bare}" in stripped, f"--{bare} missing from the stripped bundle"
        assert f"--ax-{bare}" in renamed, f"{prop} must follow a custom prefix"
        assert f"--dz-{bare}" in kept, f"{prop} must survive the dz- (no-op) build"


def test_no_private_css_prop_leaks_into_snippets() -> None:
    """A registry partial (the copy-paste snippet) may only reference
    custom properties declared public — a private token in a snippet is
    an undocumented API a consumer would copy and depend on."""
    from build import PUBLIC_CSS_PROPS

    leaks = []
    for pid, partial in _all_partials():
        for name in re.findall(r"--dz-[a-z0-9-]+", partial):
            if name not in PUBLIC_CSS_PROPS:
                leaks.append(f"{pid}: {name}")
    assert not leaks, (
        "private custom properties referenced in snippets (declare in "
        "PUBLIC_CSS_PROPS or use a public knob):\n  " + "\n  ".join(leaks)
    )


def test_js_assigned_classes_have_rules() -> None:
    """Classes a controller assigns at runtime (`el.className = …`,
    `classList.add(…)`) are invisible to the registry-class gate above —
    the 0.1.26 blind spot where the inline-edit editor rendered unstyled
    in the gallery because its input classes existed only in Dazzle CSS.
    Every dz-* class a controller can put in the DOM must have a rule in
    the built bundle. State classes (`is-*`) are exempt: they style via
    compound selectors on their host."""
    css = build_css("dz-")
    controllers = sorted((PKG / "controllers").glob("*.js"))
    assign_re = re.compile(r"""(?:className\s*=\s*|classList\.add\()["']([^"']+)["']""")
    missing = []
    for f in controllers:
        for m in assign_re.finditer(f.read_text(encoding="utf-8")):
            for cls in m.group(1).split():
                if not cls.startswith("dz-") or cls in SEMANTIC_ONLY:
                    continue
                if f".{cls}" not in css:
                    missing.append(f"{f.name}: .{cls}")
    assert not missing, (
        "controller-assigned classes with no CSS rule in the bundle:\n  " + "\n  ".join(missing)
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
    # Blueprint sub-pages regenerate byte-identically too — stale committed
    # HTML would make test_blueprints.py exercise outdated markup while green.
    for bp_html in sorted((tmp_path / "blueprints").glob("*.html")):
        fresh = bp_html.read_text(encoding="utf-8")
        committed = (PKG / "site" / "blueprints" / bp_html.name).read_text(encoding="utf-8")
        assert fresh == committed, (
            f"site/blueprints/{bp_html.name} is stale — re-run python site/build_site.py and commit"
        )


def test_prefix_transform_is_total() -> None:
    css = build_css(prefix="ax-")
    js = build_js(prefix="ax-")
    # `dz-` survives ONLY in PRIVATE `--dz-*` custom-property names (the
    # public knobs in PUBLIC_CSS_PROPS are reprefixed like any API name —
    # see build.apply_prefix). Everything else must be renamed.
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
        for method in sorted(_methods_in_markup(c.partial)):
            # markup uses mock endpoints; exchanges declare the REAL contract
            # — so we require one exchange per request METHOD, not per URL.
            if not any(m == method for m, _ in declared):
                gaps.append(f"{c.id}: {method} affordance in markup with no declared Exchange")
    assert not gaps, (
        "components make requests they don't declare as Exchange contracts:\n  " + "\n  ".join(gaps)
    )


def test_no_orphan_exchange_without_an_affordance() -> None:
    """An Exchange with no matching hx-* control in the markup is a stale
    contract — the partial doesn't actually make that request."""
    orphans = []
    for c in HYPERPARTS:
        methods_in_markup = _methods_in_markup(c.partial)
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
    for pid, partial in _all_partials():
        for m in _DATA_ATTR_RE.finditer(partial):
            name = m.group(1)
            if not name.startswith(("dz-", "hm-")):
                offenders.setdefault(pid, set()).add("data-" + name)
    assert not offenders, f"non-grammar data-attributes (use data-dz-*/data-hm-*): {offenders}"


def test_composes_references_real_hyperparts() -> None:
    """A composite's `composes` must name real Hyperparts — a dangling child
    id means the 'Composed of' links and dependency aggregation are wrong."""
    ids = {c.id for c in HYPERPARTS}
    dangling = {c.id: [x for x in c.composes if x not in ids] for c in HYPERPARTS if c.composes}
    dangling = {k: v for k, v in dangling.items() if v}
    assert not dangling, f"composes references unknown Hyperparts: {dangling}"
