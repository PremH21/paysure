"""Cross-platform fonts for the synthetic test/demo images (Linux, macOS, Windows).
Tries common font files, then falls back to the font bundled inside Pillow, so it never fails on a missing file."""
import os
from PIL import ImageFont

_CANDIDATES = {
    False: [  # regular
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arial.ttf",
    ],
    True: [   # bold
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ],
}


def get_font(size: int, bold: bool = False, variant: int = 0):
    """variant lets the data generator rotate between several candidate fonts (more visual variety)."""
    cands = [p for p in _CANDIDATES[bold] if os.path.exists(p)]
    for i in range(len(cands)):
        try:
            return ImageFont.truetype(cands[(variant + i) % len(cands)], size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)       # bundled with Pillow 10.1+; always available
