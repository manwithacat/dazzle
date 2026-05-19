"""On-demand local tracing for ``dazzle perf`` (#1153 follow-on).

Public surface — re-exported from submodules so callers don't need to
remember which file each helper lives in:

- :func:`configure_tracer` (in ``tracer.py``)
- :func:`dazzle_span` (in ``tracer.py``)
- :func:`instrument_app` (in ``instrument.py``)

The exporter, serializer, storage, and findings layers stay namespaced
under their submodules — those are read by the CLI / MCP handlers,
not by framework callers.
"""

from __future__ import annotations
