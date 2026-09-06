"""On-brand icons (SEP for `Icon`/`icons`, mcp SDK 2.x's `mcp_types.Icon`) for
the server itself and its tools.

One icon per tool *domain* rather than a bespoke icon per tool: clients that
render tool icons show them small, in a list or menu, where 49 unique glyphs
would mostly read as noise. A shared icon per group (accounts, transactions,
categories, ...) gives a quick visual anchor for what each tool touches
without commissioning one-off art per tool.

Each per-domain icon is a gold rounded-square background — Nyuchi's own
Mzizi ecosystem mineral (`mzizi_get_tokens` family=ecosystem/minerals;
distinct from Bundu's copper, since this is specifically a Nyuchi product,
not a generic cross-ecosystem one), matching `worker/site`'s favicon and
`--color-accent` — with a simple dark-brown glyph (the same token's
light-mode value, chosen over white for contrast against the bright gold
background). Carrying its own background rather than a transparent glyph
keeps contrast solid regardless of the host's light/dark theme, at the cost
of not tinting per-theme the way `Icon.theme` would allow.

The server-level icon (`SERVER`, below) is different: it's Nyuchi's actual
bee logo — the real asset from nyuchi.com/icon-dark.png (assets/nyuchi-bee.png
here), not a hand-drawn recreation of it. "Nyuchi" is Shona for "Bee".
"""

import base64
from importlib import resources
from urllib.parse import quote

from mcp_types import Icon

_GOLD = "#FFD740"  # Nyuchi's ecosystem mineral (dark backgrounds; see module docstring)
# Glyph ink is a literal "#5D4037" throughout below (that mineral's light-mode
# value) rather than a shared constant, since each glyph is a plain string.


def _data_uri(svg: str) -> str:
    return f"data:image/svg+xml,{quote(svg)}"


def _icon(glyph: str) -> Icon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<rect width="24" height="24" rx="6" fill="{_GOLD}"/>'
        f"{glyph}"
        "</svg>"
    )
    return Icon(src=_data_uri(svg), mime_type="image/svg+xml", sizes=["any"])


def _png_icon(filename: str) -> Icon:
    png_bytes = resources.files(__package__).joinpath("assets", filename).read_bytes()
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return Icon(src=f"data:image/png;base64,{b64}", mime_type="image/png", sizes=["200x200"])


# Server-level icon — Nyuchi's actual bee mark (the same asset as
# worker/site's favicon/header), for MCP clients that show a server icon.
SERVER = _png_icon("nyuchi-bee.png")

USER = _icon(
    '<circle cx="12" cy="9" r="3.2" fill="none" stroke="#5D4037" stroke-width="1.8"/>'
    '<path d="M5.5 19c1-3.2 3.8-5 6.5-5s5.5 1.8 6.5 5" fill="none" stroke="#5D4037" '
    'stroke-width="1.8" stroke-linecap="round"/>'
)

PLAN = _icon(
    '<rect x="6" y="4" width="12" height="16" rx="1.5" fill="none" stroke="#5D4037" stroke-width="1.6"/>'
    '<path d="M9 9h6M9 12.5h6M9 16h3.5" stroke="#5D4037" stroke-width="1.6" stroke-linecap="round"/>'
)

ACCOUNT = _icon(
    '<rect x="4" y="7" width="16" height="11" rx="1.8" fill="none" stroke="#5D4037" stroke-width="1.6"/>'
    '<path d="M4 11h16" stroke="#5D4037" stroke-width="1.6"/>'
    '<path d="M7 15h4" stroke="#5D4037" stroke-width="1.6" stroke-linecap="round"/>'
)

CATEGORY = _icon(
    '<path d="M11 4h4.5L20 8.5V13l-9 9-9-9z" fill="none" stroke="#5D4037" '
    'stroke-width="1.6" stroke-linejoin="round"/>'
    '<circle cx="14.2" cy="9.8" r="1.3" fill="#5D4037"/>'
)

PAYEE = _icon(
    '<path d="M4 9l1.4-4h13.2L20 9" fill="none" stroke="#5D4037" stroke-width="1.6" stroke-linejoin="round"/>'
    '<path d="M5 9v9h14V9" fill="none" stroke="#5D4037" stroke-width="1.6" stroke-linejoin="round"/>'
    '<path d="M10 18v-5h4v5" fill="none" stroke="#5D4037" stroke-width="1.6" stroke-linejoin="round"/>'
)

PAYEE_LOCATION = _icon(
    '<path d="M12 21s6.5-6.1 6.5-11A6.5 6.5 0 0 0 5.5 10c0 4.9 6.5 11 6.5 11z" '
    'fill="none" stroke="#5D4037" stroke-width="1.6" stroke-linejoin="round"/>'
    '<circle cx="12" cy="10" r="2.1" fill="#5D4037"/>'
)

MONTH = _icon(
    '<rect x="4.5" y="5.5" width="15" height="14" rx="1.5" fill="none" stroke="#5D4037" stroke-width="1.6"/>'
    '<path d="M4.5 9.5h15M8 4v3M16 4v3" stroke="#5D4037" stroke-width="1.6" stroke-linecap="round"/>'
)

MONEY_MOVEMENT = _icon(
    '<path d="M4 8h13M17 8l-3-3M17 8l-3 3" fill="none" stroke="#5D4037" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M20 16H7M7 16l3-3M7 16l3 3" fill="none" stroke="#5D4037" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
)

TRANSACTION = _icon(
    '<path d="M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3z" fill="none" '
    'stroke="#5D4037" stroke-width="1.5" stroke-linejoin="round"/>'
    '<path d="M8.5 8h7M8.5 11.5h7M8.5 15h4.5" stroke="#5D4037" stroke-width="1.4" stroke-linecap="round"/>'
)

SCHEDULED = _icon(
    '<circle cx="12" cy="13" r="7.5" fill="none" stroke="#5D4037" stroke-width="1.6"/>'
    '<path d="M12 8.5V13l3 2" fill="none" stroke="#5D4037" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M9 3.5h6" stroke="#5D4037" stroke-width="1.6" stroke-linecap="round"/>'
)

ANALYTICS = _icon(
    '<path d="M5 19V11M11 19V5M17 19v-6" fill="none" stroke="#5D4037" stroke-width="2" stroke-linecap="round"/>'
)

RECONCILE = _icon(
    '<circle cx="12" cy="12" r="8" fill="none" stroke="#5D4037" stroke-width="1.6"/>'
    '<path d="M8.5 12.5l2.2 2.2 4.8-5.4" fill="none" stroke="#5D4037" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
)
