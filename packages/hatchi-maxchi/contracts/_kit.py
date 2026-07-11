"""Contract kit — structured DOM contracts for Hyperparts.

A DomContract is the machine-readable half of a controller's prose
`Contract:` header: root selector + per-node required attributes with
value validators. validate_dom() is used by HM CI (exemplar output) and,
test-time, by Dazzle's conformance gate. Selector support is deliberately
tiny: conjunctions of [attr] / [attr="value"] — enough for data-dz-*
contracts, no CSS engine.
"""

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


class Present:
    """Attribute must be present; any value accepted."""

    def check(self, value: str) -> str | None:
        return None


@dataclass(frozen=True)
class OneOf:
    values: tuple[str, ...]

    def __init__(self, *values: str) -> None:
        object.__setattr__(self, "values", values)

    def check(self, value: str) -> str | None:
        return None if value in self.values else f"expected one of {self.values}, got {value!r}"


@dataclass(frozen=True)
class JsonPairs:
    """Attribute must be JSON of shape [[str, str], ...]. If required_when
    is set, the attribute is required only on nodes whose OTHER attributes
    match; on non-matching nodes it must be absent."""

    required_when: dict[str, str] | None = None

    def check(self, value: str) -> str | None:
        try:
            data = json.loads(value)
        except ValueError:
            return f"not valid JSON: {value!r}"
        if not isinstance(data, list) or not all(
            isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) for s in p) for p in data
        ):
            return f"not a list of [value, label] string pairs: {value!r}"
        return None


@dataclass(frozen=True)
class Node:
    selector: str
    attrs: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DomContract:
    part: str
    root: str
    nodes: tuple[Node, ...] = ()


_SEL = re.compile(r"\[([a-zA-Z0-9_-]+)(?:=\"([^\"]*)\")?\]")


def _sel_conditions(selector: str) -> list[tuple[str, str | None]]:
    return [(m.group(1), m.group(2)) for m in _SEL.finditer(selector)]


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append({k: (v if v is not None else "") for k, v in attrs})


def _matches(el: dict[str, str], selector: str) -> bool:
    return all(
        (name in el) and (want is None or el[name] == want)
        for name, want in _sel_conditions(selector)
    )


def validate_dom(html: str, contract: DomContract, require_root: bool = True) -> list[str]:
    """Validate an HTML string against a DomContract. Returns violation
    strings; empty list = conforming. require_root=False validates a
    fragment (node contracts only) — e.g. a tbody rows response whose grid
    root is page furniture."""
    parser = _Collector()
    parser.feed(html)
    els = parser.elements
    out: list[str] = []
    if require_root and not any(_matches(e, contract.root) for e in els):
        out.append(f"{contract.part}: no element matches root {contract.root!r}")
    for node in contract.nodes:
        for el in (e for e in els if _matches(e, node.selector)):
            for attr, validator in node.attrs.items():
                required = True
                # Duck-typed (not isinstance): consumers may load this kit
                # standalone (importlib from a repo path) while the contract
                # module imports it as a package — two class identities.
                required_when = getattr(validator, "required_when", None)
                if required_when:
                    required = all(el.get(k) == v for k, v in required_when.items())
                    if not required and attr in el:
                        out.append(
                            f"{contract.part}: {node.selector} has {attr} but "
                            f"required_when {required_when} does not match"
                        )
                if attr not in el:
                    if required:
                        out.append(f"{contract.part}: {node.selector} missing {attr}")
                    continue
                err = validator.check(el[attr]) if hasattr(validator, "check") else None
                if err:
                    out.append(f"{contract.part}: {node.selector}[{attr}] {err}")
    return out
