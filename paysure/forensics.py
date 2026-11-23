"""Image forensics: Error Level Analysis (ELA) + heatmap + simple signals.

Real computation only - no hard-coded verdicts.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops


@dataclass
class ELAResult:
    score: float            # 0..1 overall suspiciousness
    max_region_ratio: float  # fraction of image in the hottest connected block
    heatmap: Image.Image    # RGB overlay image
    bbox: tuple | None      # (x0, y0, x1, y1) of the hottest region, or None


def _ela_map(img: Image.Image, quality: int = 90) -> np.ndarray:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(img.convert("RGB"), resaved)
    arr = np.asarray(diff, dtype=np.float32).sum(axis=2)
    return arr


def run_ela(img: Image.Image, quality: int = 90, block: int = 16) -> ELAResult:
    """Block-wise ELA. Edited regions recompress differently from the rest.

    Score = how much the hottest blocks stand out from the image median
    (robust z-score), squashed to 0..1.
    """
    arr = _ela_map(img, quality)
    h, w = arr.shape
    bh, bw = max(1, h // block), max(1, w // block)
    arr = arr[: bh * block, : bw * block]
    blocks = arr.reshape(bh, block, bw, block).mean(axis=(1, 3))

    med = float(np.median(blocks))
    mad = max(float(np.median(np.abs(blocks - med))), 1.0)  # floor: flat UI has ~0 MAD
    z = (blocks - med) / (1.4826 * mad)
    hot = (z > 6.0) & (blocks > 6.0)  # must stand out AND be absolutely strong

    # Score: share of hot blocks and strength, bounded
    hot_ratio = float(hot.mean())
    strength = float(np.clip(z.max() / 40.0, 0, 1)) if z.size else 0.0
    score = float(np.clip(0.6 * strength + 0.4 * min(hot_ratio * 20, 1.0), 0, 1))

    bbox = None
    if hot.any():
        ys, xs = np.where(hot)
        bbox = (
            int(xs.min() * block), int(ys.min() * block),
            int((xs.max() + 1) * block), int((ys.max() + 1) * block),
        )

    # Heatmap overlay
    norm = np.clip(z, 0, 12) / 12.0
    heat = np.zeros((bh, bw, 3), dtype=np.uint8)
    heat[..., 0] = (norm * 255).astype(np.uint8)
    heat[..., 1] = ((1 - norm) * 60).astype(np.uint8)
    heat_img = Image.fromarray(heat).resize(img.size, Image.NEAREST)
    overlay = Image.blend(img.convert("RGB"), heat_img, 0.45)
    if bbox:
        from PIL import ImageDraw
        ImageDraw.Draw(overlay).rectangle(bbox, outline=(255, 0, 0), width=3)

    return ELAResult(score, hot_ratio, overlay, bbox)


def metadata_flags(path_or_bytes) -> dict:
    """Cheap metadata signals. Screenshots from phones are normally PNG with no
    EXIF; editor software tags in EXIF/info are a red flag."""
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
    img = Image.open(io.BytesIO(data))
    info = {str(k).lower(): str(v).lower() for k, v in (img.info or {}).items() if k != "icc_profile"}
    try:
        exif = img.getexif()
        software = str(exif.get(305, "")).lower()
    except Exception:
        software = ""
    editors = ("photoshop", "gimp", "canva", "snapseed", "picsart", "lightroom", "pixlr", "photopea")
    edited_by = next((e for e in editors if e in software or any(e in v for v in info.values())), None)
    return {
        "format": img.format,
        "size": img.size,
        "editor_tag": edited_by,
        "is_jpeg": img.format == "JPEG",
    }
