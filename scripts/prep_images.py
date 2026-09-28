"""Prepare word pictures dropped into media/images/<topic>/<slug>.png.

A photo comes in as it is: large, with the object somewhere in the frame. The
card wants a small square with the object filling it, so every PNG is cropped
to its opaque pixels, padded to a square with a little air around the object,
shrunk to SIZE and written back in place. A file that already looks like that
is left untouched, so the script is safe to run again and again. SVG files are
served as they are and skipped.

Only PNG with a transparent background is accepted: a photo on white would
show as a white square on the dark theme.

Run from the repo root:

    make images
    # or
    uv run --no-project --with pillow python scripts/prep_images.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_DIR = Path(__file__).resolve().parents[1]
IMAGES_DIR = REPO_DIR / "media" / "images"

SIZE = 384  # card circle is 96 px, so 4x for retina and some zoom
AIR = 0.04  # padding around the object, a share of the longer side
ALPHA_MIN = 8  # pixels fainter than this count as background


def prepare(path: Path) -> bool:
    """Crop, square and shrink one PNG in place; returns whether it was rewritten."""
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    if image.getchannel("A").getextrema()[0] == 255:
        raise SystemExit(f"{path.relative_to(REPO_DIR)}: no transparent background")

    bbox = image.getchannel("A").point(lambda a: 255 if a >= ALPHA_MIN else 0).getbbox()
    if bbox is None:
        raise SystemExit(f"{path.relative_to(REPO_DIR)}: fully transparent picture")
    left, top, right, bottom = bbox
    width, height = right - left, bottom - top
    side = round(max(width, height) * (1 + 2 * AIR))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image.crop(bbox), ((side - width) // 2, (side - height) // 2))
    canvas = canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)

    fills_the_square = max(width, height) >= SIZE * (1 - 3 * AIR)
    if image.size == (SIZE, SIZE) and fills_the_square:
        return False
    canvas.save(path, optimize=True)
    return True


def main() -> None:
    done = skipped = 0
    for path in sorted(IMAGES_DIR.rglob("*.png")):
        if prepare(path):
            done += 1
            print(f"{path.relative_to(REPO_DIR)}  ←  cropped and shrunk to {SIZE} px")
        else:
            skipped += 1
    print(f"done: {done} prepared, {skipped} skipped (already prepared)")


if __name__ == "__main__":
    main()
