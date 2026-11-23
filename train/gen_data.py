"""Generate a labelled synthetic dataset and extract features. SYNTHETIC: replace/extend with real consented screenshots.
Usage: python gen_data.py N_PER_GROUP OUT.json"""
import io
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
from paysure.features import extract_features  # noqa: E402

from fontutil import get_font  # noqa: E402


def screen(r: random.Random):
    W, H = r.choice([(540, 960), (480, 900), (600, 1000)])
    bg = tuple(r.randrange(235, 256) for _ in range(3))
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    hdr = tuple(r.randrange(40, 200) for _ in range(3))
    for _ in range(r.randrange(2000, 6000)):                       # photo/gradient-like header texture
        d.point((r.randrange(W), r.randrange(0, 200)), fill=tuple(min(255, c + r.randrange(-30, 30)) for c in hdr))
    amt = f"{r.randrange(10, 20000)}"
    utr = "".join(r.choice("0123456789") for _ in range(12))
    f_big = get_font(r.randrange(44, 64), bold=bool(r.randrange(2)), variant=r.randrange(4))
    f_sm = get_font(r.randrange(22, 30), variant=r.randrange(4))
    y0 = r.randrange(240, 300)
    d.text((60, y0), "Payment Successful", font=get_font(32, True), fill=(20, 120, 50))
    box = (60, y0 + 80)
    d.text(box, f"Rs {amt}", font=f_big, fill=(10, 10, 10))
    d.text((60, y0 + 190), f"Paid to shop{r.randrange(99)}@okbank", font=f_sm, fill=(30, 30, 30))
    d.text((60, y0 + 250), f"{r.randrange(1,28)} Oct 2026, {r.randrange(1,12):02d}:{r.randrange(60):02d} PM", font=f_sm, fill=(30, 30, 30))
    d.text((60, y0 + 310), f"UPI Ref No: {utr}", font=f_sm, fill=(30, 30, 30))
    return img, box, f_big


def jpeg(img, q):
    b = io.BytesIO(); img.save(b, "JPEG", quality=q); return b.getvalue()


def forward(data: bytes, r: random.Random) -> bytes:
    """WhatsApp-like re-encode: downscale a bit + lower quality. This is a GENUINE path."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    s = r.uniform(0.65, 1.0)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    return jpeg(im, r.randrange(55, 80))


def edit_text(data, box, f_big, r, other_font):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    d = ImageDraw.Draw(im)
    x, y = box
    d.rectangle((x - 5, y - 5, x + 380, y + 80), fill=im.getpixel((x + 390, y)))
    font = get_font(r.randrange(44, 64), bold=bool(r.randrange(2)), variant=r.randrange(4)) if other_font else f_big
    d.text((x + r.randrange(-2, 3), y + r.randrange(-2, 3)), f"Rs {r.randrange(10, 20000)}", font=font, fill=(10, 10, 10))
    return im


def paste_region(data, other, r):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    o = Image.open(io.BytesIO(other)).convert("RGB").resize(im.size)
    x0, y0 = r.randrange(40, 120), r.randrange(300, 700)
    w, h = r.randrange(150, 350), r.randrange(40, 90)
    im.paste(o.crop((x0, y0, x0 + w, y0 + h)), (x0 + r.randrange(-5, 6), y0 + r.randrange(-5, 6)))
    return im


def launder(im: Image.Image, r) -> bytes:
    """Screenshot-of-screenshot: resample, blur a touch, add noise-like border, re-save."""
    s = r.uniform(0.8, 1.2)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.BICUBIC).filter(ImageFilter.GaussianBlur(r.uniform(0.3, 0.9)))
    return jpeg(im, r.randrange(60, 90))


def digit_clone(data, box, r):
    """Copy-move inside the amount line: duplicate digit shapes from the same image to change the number."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    x, y = box
    w = r.randrange(50, 110)
    sx = x + r.randrange(60, 160)
    crop = im.crop((sx, y, sx + w, y + 70))
    im.paste(crop, (x + r.randrange(120, 250) + r.randrange(1, 8), y + r.randrange(-2, 3)))
    return im


def blur_retype(data, box, f_big, r):
    """Smudge the amount away, then retype with soft edges and slightly off colour."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    x, y = box
    region = im.crop((x - 5, y - 5, x + 380, y + 80)).filter(ImageFilter.GaussianBlur(r.uniform(6, 12)))
    im.paste(region, (x - 5, y - 5))
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x, y), f"Rs {r.randrange(10, 20000)}", font=f_big, fill=(r.randrange(0, 40),) * 3 + (r.randrange(200, 256),))
    layer = layer.filter(ImageFilter.GaussianBlur(r.uniform(0.3, 0.8)))
    im.paste(layer, (0, 0), layer)
    return im


def main(n, out):
    r = random.Random(1234)
    rows = []

    os.makedirs("data/img", exist_ok=True)

    def add(data, label, group):
        path = f"data/img/{len(rows):05d}.jpg"
        open(path, "wb").write(data)
        rows.append(dict(p=path, y=label, g=group))

    for i in range(n):
        im, box, fb = screen(r); base = jpeg(im, r.randrange(80, 96))
        add(base, 0, "genuine_direct")
        im, box, fb = screen(r); base = jpeg(im, r.randrange(80, 96))
        add(forward(base, r), 0, "genuine_forwarded")
        for group, kind in (("edit_same_font", 0), ("edit_other_font", 1)):
            im, box, fb = screen(r); base = jpeg(im, r.randrange(80, 96))
            add(jpeg(edit_text(base, box, fb, r, bool(kind)), r.randrange(80, 96)), 1, group)
        im, box, fb = screen(r); base = jpeg(im, r.randrange(80, 96))
        im2, _, _ = screen(r)
        add(jpeg(paste_region(base, jpeg(im2, r.randrange(70, 95)), r), r.randrange(80, 96)), 1, "region_paste")
        im, box, fb = screen(r); base = jpeg(im, r.randrange(80, 96))
        add(launder(edit_text(base, box, fb, r, True), r), 1, "edit_then_screenshot")
        if (i + 1) % 50 == 0:
            print(i + 1, "/", n, flush=True)
    r2 = random.Random(777)             # separate stream: main data identical to before; these two families are NEVER trained on
    for i in range(n // 2):
        im, box, fb = screen(r2); base = jpeg(im, r2.randrange(80, 96))
        d = jpeg(digit_clone(base, box, r2), r2.randrange(80, 96))
        add(forward(d, r2) if i % 2 else d, 1, "novel_digit_clone")
        im, box, fb = screen(r2); base = jpeg(im, r2.randrange(80, 96))
        d = jpeg(blur_retype(base, box, fb, r2), r2.randrange(80, 96))
        add(forward(d, r2) if i % 2 else d, 1, "novel_blur_retype")
    json.dump(rows, open(out, "w"))
    print("rows:", len(rows))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
