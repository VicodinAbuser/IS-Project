"""Add real product photos to the shop.

    python tools/add_product_photos.py <folder with photos> [<another folder> ...]

Each photo must be named after its product's SKU, e.g. EL-011.jpg, BC-003.png
(.jpg, .jpeg, .png or .webp, any size). Each one is fitted onto an 800 x 600 (4:3) canvas
with the whole product visible (white around studio shots, a soft blurred copy of the photo
around the rest) and saved as frontend/public/products/<SKU>.jpg.

Afterwards the dataset generator and 03_seed_data.sql use the photo (.jpg) for every SKU
that has one, and the icon picture (.svg) for the rest. To update a database that is
already loaded, run the SQL line this script prints.
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "products"
SEED = ROOT / "database" / "03_seed_data.sql"
SIZE = (800, 600)
SKU_RE = re.compile(r"^[A-Z]{2}-\d{3}$")


def known_skus() -> set[str]:
    sys.path.insert(0, str(ROOT / "tools"))
    from generate_dataset import PRODUCTS
    return {p[0] for p in PRODUCTS}


def white_background(im: Image.Image) -> bool:
    """True when the photo's border is (nearly) white, like a studio product shot."""
    w, h = im.size
    border = [im.getpixel((x, y)) for x in range(0, w, max(1, w // 40)) for y in (0, h - 1)] + \
             [im.getpixel((x, y)) for y in range(0, h, max(1, h // 40)) for x in (0, w - 1)]
    return sum(min(p) for p in border) / len(border) > 235


def fit(path: Path) -> Image.Image:
    """The whole product on a 4:3 canvas: white margins for studio shots, a soft blurred
    copy of the photo behind it for photos with a background (so the card is never half empty)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)          # respect the phone's rotation flag
        if im.mode in ("RGBA", "LA", "P"):        # transparent parts become white
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, "white")
            im = Image.alpha_composite(bg, im)
        im = im.convert("RGB")
    if white_background(im):
        canvas = Image.new("RGB", SIZE, "white")
        im.thumbnail((SIZE[0] - 40, SIZE[1] - 40), Image.LANCZOS)
    else:
        canvas = ImageOps.fit(im, SIZE, Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
        canvas = Image.blend(canvas, Image.new("RGB", SIZE, "white"), 0.25)
        im.thumbnail(SIZE, Image.LANCZOS)
    canvas.paste(im, ((SIZE[0] - im.width) // 2, (SIZE[1] - im.height) // 2))
    return canvas


def update_seed(photo_skus: list[str]) -> None:
    """03_seed_data.sql: the products it creates use the photo when there is one."""
    text = SEED.read_text(encoding="utf-8")
    listed = ", ".join(f"'{s}'" for s in sorted(photo_skus)) or "'-'"
    new_line = f"UPDATE products SET image_url = '/products/' || sku || '.jpg' WHERE sku IN ({listed});"
    marker = "-- Real photos (tools/add_product_photos.py) for these SKUs; the others keep their icon picture."
    if marker in text:
        text = re.sub(re.escape(marker) + r"\nUPDATE products SET image_url[^\n]*", marker + "\n" + new_line, text)
    else:
        anchor = "-- Opening stock + about 260 paid orders"
        text = text.replace(anchor, marker + "\n" + new_line + "\n\n" + anchor, 1)
    SEED.write_text(text, encoding="utf-8")


def main():
    folders = [Path(a) for a in sys.argv[1:]]
    if not folders:
        raise SystemExit(__doc__)
    skus = known_skus()
    OUT.mkdir(parents=True, exist_ok=True)
    added, skipped = [], []
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp") or not path.is_file():
                continue
            sku = path.stem.upper()
            if not SKU_RE.match(sku) or sku not in skus:
                skipped.append(f"{path.name} (not a product SKU)")
                continue
            fit(path).save(OUT / f"{sku}.jpg", "JPEG", quality=84, optimize=True, progressive=True)
            added.append(sku)
    all_photos = sorted(p.stem for p in OUT.glob("*.jpg"))
    update_seed(all_photos)
    print(f"Added {len(added)} photos to {OUT.relative_to(ROOT)}; {len(all_photos)} products now have a photo.")
    for s in skipped:
        print("  skipped:", s)
    print("\nTo show them in a database that is already loaded, run this in SQL Developer (INVENTORY):")
    print(f"UPDATE products SET image_url = '/products/' || sku || '.jpg' WHERE sku IN "
          f"({', '.join(repr(s) for s in all_photos)});\nCOMMIT;")


if __name__ == "__main__":
    main()
