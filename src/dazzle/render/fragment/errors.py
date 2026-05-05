"""Exception hierarchy for the Fragment system.

All Fragment-construction or rendering errors derive from FragmentError so
callers can catch the family. Specific subclasses name the structural rule
that was violated, which becomes useful in test failure messages.
"""


class FragmentError(Exception):
    """Base class for all Fragment-system errors."""


class CardSafetyError(FragmentError):
    """Violation of card-safety invariants (no nested cards, no duplicate
    titles, etc). Replaces the runtime scanner at construction time."""


class HtmxBindingError(FragmentError):
    """An htmx attribute combination is incoherent (e.g. both hx_get and
    hx_post on the same primitive)."""


class PrimitiveRegistrationError(FragmentError):
    """A primitive was registered with a duplicate name or an unsupported
    shape."""
