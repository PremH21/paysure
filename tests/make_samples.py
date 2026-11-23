"""Generate synthetic TEST screens (generic layout, not any real app) to exercise the pipeline.
These are only for unit testing; real accuracy needs your own consented screenshots."""
import io
import os
import sys
import random
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "train"))
from fontutil import get_font  # noqa: E402


def make_screen(amount: str, utr: str, when: str, upi="shopkeeper@okbank", size=(540, 960), status="Payment Successful") -> Image.Image:
    img = Image.new("RGB", size, (250, 250, 252))
    d = ImageDraw.Draw(img)
    # Photo-like noise on the header so JPEG behaves like a real capture
    rnd = random.Random(7)
    for _ in range(4000):
        x, y = rnd.randrange(size[0]), rnd.randrange(0, 200)
        d.point((x, y), fill=(rnd.randrange(60, 120), rnd.randrange(100, 160), rnd.randrange(150, 220)))
    d.text((60, 260), status, font=get_font(34, True), fill=(20, 120, 50))
    d.text((60, 340), f"Rs {amount}", font=get_font(56, True), fill=(10, 10, 10))
    d.text((60, 440), f"Paid to {upi}", font=get_font(26), fill=(30, 30, 30))
    d.text((60, 500), when, font=get_font(26), fill=(30, 30, 30))
    d.text((60, 560), f"UPI Ref No: {utr}", font=get_font(26), fill=(30, 30, 30))
    return img


def to_jpeg(img: Image.Image, q=85) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=q)
    return b.getvalue()


def tamper_amount(jpeg_bytes: bytes, new_amount: str, q=85) -> bytes:
    """Realistic edit: open the JPEG, cover the amount, type a new one, re-save."""
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    d = ImageDraw.Draw(img)
    d.rectangle((55, 335, 400, 415), fill=(250, 250, 252))
    d.text((60, 340), f"Rs {new_amount}", font=get_font(56, True), fill=(10, 10, 10))
    return to_jpeg(img, q)
