"""HYPERPART: search-select — typeahead open/close + hidden FK submit."""

from __future__ import annotations

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="search-select",
    root='[data-dz-widget="search_select"]',
    nodes=(Node('[data-dz-widget="search_select"]', attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
