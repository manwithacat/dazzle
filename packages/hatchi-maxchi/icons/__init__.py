"""HaTchi-MaXchi icon registry — the design system's Lucide subset.

Source of truth for the icon set. Dazzle vendors ``registry.py`` into
``src/dazzle/render/fragment/icon_registry.py`` (byte-identical data;
drift-gated). Regenerate both via ``gen_registry.py``.
"""

from .html import lucide_icon_html, lucide_svg_html
from .registry import ICONS, LUCIDE_VERSION

__all__ = ["ICONS", "LUCIDE_VERSION", "lucide_icon_html", "lucide_svg_html"]
