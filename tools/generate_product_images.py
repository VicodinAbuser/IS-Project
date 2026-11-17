"""Make one product picture per SKU: frontend/public/products/<SKU>.svg

    python tools/generate_product_images.py

Each picture shows an icon that matches the product name, on a background in its
category's colour, with the product name underneath. They are stored in the project
(no outside image website), so they always load and always match the product.
The database points to them with  PRODUCTS.IMAGE_URL = '/products/<SKU>.svg'.
"""
from html import escape
from pathlib import Path

from generate_dataset import PRODUCTS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "products"

# Icon for each product (emoji, drawn by the computer's own emoji font)
ICONS = {
    "EL-001": "🖱️", "EL-002": "🎧", "EL-003": "🔌", "EL-004": "⌨️", "EL-005": "🔋", "EL-006": "⌚", "EL-007": "🎧",
    "EL-008": "🔊", "EL-009": "📷", "EL-010": "💾", "EL-011": "💽", "EL-012": "💡", "EL-013": "🔌", "EL-014": "📡",
    "EL-015": "💻",
    "ST-001": "📓", "ST-002": "🖊️", "ST-003": "🗂️", "ST-004": "🗒️", "ST-005": "🖍️", "ST-006": "📔", "ST-007": "🧮",
    "ST-008": "📎", "ST-009": "✏️", "ST-010": "📁", "ST-011": "📋", "ST-012": "✒️",
    "HK-001": "🍶", "HK-002": "🍳", "HK-003": "☕", "HK-004": "🍲", "HK-005": "🥡", "HK-006": "🫖", "HK-007": "🔪",
    "HK-008": "🛏️", "HK-009": "🍹", "HK-010": "🍱", "HK-011": "🛁", "HK-012": "🍽️",
    "AP-001": "👕", "AP-002": "🧥", "AP-003": "👖", "AP-004": "👔", "AP-005": "👘", "AP-006": "👟", "AP-007": "🧥",
    "AP-008": "👖", "AP-009": "🧦", "AP-010": "🧢",
    "SP-001": "🧘", "SP-002": "🏋️", "SP-003": "🤸", "SP-004": "🏏", "SP-005": "⚽", "SP-006": "🏸", "SP-007": "💪",
    "SP-008": "🎒", "SP-009": "🥤", "SP-010": "⌚",
    "BC-001": "🧼", "BC-002": "🧴", "BC-003": "🧴", "BC-004": "☀️", "BC-005": "🪒", "BC-006": "💨", "BC-007": "🌸",
    "BC-008": "💄", "BC-009": "🦷", "BC-010": "🧼",
    "BK-001": "📘", "BK-002": "🐍", "BK-003": "📗", "BK-004": "🧠", "BK-005": "📜", "BK-006": "💰", "BK-007": "📖",
    "BK-008": "📝", "BK-009": "📕", "BK-010": "📐",
    "TG-001": "🧱", "TG-002": "♟️", "TG-003": "🧩", "TG-004": "🏎️", "TG-005": "🎲", "TG-006": "🧸", "TG-007": "🎲",
    "TG-008": "🎨", "TG-009": "🃏", "TG-010": "🔬",
}
# Category -> (light, dark) background colours
COLOURS = {
    "Electronics": ("#e8eeff", "#c7d4ff"), "Stationery": ("#fff4dc", "#ffe0a3"),
    "Home & Kitchen": ("#e6f6ee", "#bfe8d3"), "Apparel": ("#fdeaf1", "#f8c6d9"),
    "Sports & Fitness": ("#e4f6fb", "#b8e6f3"), "Beauty & Personal Care": ("#f3ebff", "#dccbff"),
    "Books": ("#f1ece4", "#e0d3bf"), "Toys & Games": ("#fff0e6", "#ffd2b3"),
}


def svg(name: str, category: str, icon: str) -> str:
    light, dark = COLOURS[category]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300" role="img" aria-label="{escape(name)}">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{light}"/><stop offset="1" stop-color="{dark}"/></linearGradient></defs>
  <rect width="400" height="300" fill="url(#g)"/>
  <circle cx="200" cy="128" r="82" fill="#ffffff" fill-opacity="0.65"/>
  <text x="200" y="128" font-size="96" text-anchor="middle" dominant-baseline="central"
        font-family="'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif">{icon}</text>
  <text x="200" y="262" font-size="20" font-weight="600" fill="#1d2433" text-anchor="middle"
        font-family="'Segoe UI',system-ui,-apple-system,Roboto,sans-serif">{escape(name)}</text>
</svg>
"""


PLACEHOLDER = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300" role="img" aria-label="No picture">
  <rect width="400" height="300" fill="#eef0f4"/>
  <circle cx="200" cy="128" r="82" fill="#ffffff" fill-opacity="0.7"/>
  <text x="200" y="128" font-size="96" text-anchor="middle" dominant-baseline="central"
        font-family="'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif">📦</text>
  <text x="200" y="262" font-size="18" fill="#667085" text-anchor="middle" font-family="'Segoe UI',system-ui,sans-serif">No picture yet</text>
</svg>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [p[0] for p in PRODUCTS if p[0] not in ICONS]
    assert not missing, f"no icon for {missing}"
    for sku, name, category, *_ in PRODUCTS:
        (OUT / f"{sku}.svg").write_text(svg(name, category, ICONS[sku]), encoding="utf-8")
    (OUT / "placeholder.svg").write_text(PLACEHOLDER, encoding="utf-8")
    print(f"wrote {len(PRODUCTS)} product pictures + placeholder.svg to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
