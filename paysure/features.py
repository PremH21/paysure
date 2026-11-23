"""Numeric forensic features for the classifier. All computed from pixels - nothing hard-coded."""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageChops

from .forensics import metadata_flags, run_ela


def _ela_arr(img: Image.Image, q: int) -> np.ndarray:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=q)
    b.seek(0)
    r = Image.open(b).convert("RGB")
    return np.asarray(ImageChops.difference(img, r), dtype=np.float32).sum(axis=2)


def _block_stats(a: np.ndarray, block=16):
    h, w = a.shape
    bh, bw = h // block, w // block
    m = a[: bh * block, : bw * block].reshape(bh, block, bw, block).mean(axis=(1, 3))
    return m


def _bag_features(g: np.ndarray, tile: int = 64):
    """JPEG block-grid alignment per tile. A pasted/shifted region carries a different 8x8 grid phase than the rest."""
    H, W = g.shape
    dh = np.abs(np.diff(g, axis=1))   # between columns c and c+1
    dv = np.abs(np.diff(g, axis=0))
    offs, strengths = [], []
    for y in range(0, H - tile + 1, tile):
        for x in range(0, W - tile + 1, tile):
            patch = g[y:y + tile, x:x + tile]
            if patch.std() < 6:       # flat tile: no grid evidence
                continue
            th = dh[y:y + tile, x:x + tile - 1]; tv = dv[y:y + tile - 1, x:x + tile]
            e = []
            for o in range(8):
                ch = th[:, [c for c in range(th.shape[1]) if (c + x + o) % 8 == 7]].mean()
                cv_ = tv[[r for r in range(tv.shape[0]) if (r + y + o) % 8 == 7], :].mean()
                e.append(ch + cv_)
            e = np.array(e)
            offs.append(int(e.argmax())); strengths.append(float(e.max() / (e.mean() + 1e-3)))
    if not offs:
        return dict(bag_mis_frac=0.0, bag_strength_mean=1.0, bag_strength_min=1.0, bag_dom_frac=1.0)
    offs = np.array(offs); dom = np.bincount(offs).argmax()
    return dict(bag_mis_frac=float((offs != dom).mean()), bag_strength_mean=float(np.mean(strengths)),
                bag_strength_min=float(np.min(strengths)), bag_dom_frac=float((offs == dom).mean()))


def extract_features(img: Image.Image, image_bytes: bytes, words=None):
    """words is accepted for the experimental consistency features (train/experiments); unused in the live path."""
    feats: dict[str, float] = {}
    ela_arrs = {}
    ela = run_ela(img)
    feats["ela_score"] = ela.score
    feats["ela_hot_ratio"] = ela.max_region_ratio
    for q in (70, 85, 95):
        a = _ela_arr(img, q)
        ela_arrs[q] = a
        m = _block_stats(a)
        med = float(np.median(m))
        feats[f"ela{q}_mean"] = float(a.mean())
        feats[f"ela{q}_p99"] = float(np.percentile(a, 99))
        feats[f"ela{q}_blockstd"] = float(m.std())
        feats[f"ela{q}_blockmax_over_med"] = float(m.max() / (med + 1.0))

    g = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    feats["lap_var"] = float(lap.var())
    nm = _block_stats(np.abs(lap), 32)           # local noise level per block
    feats["noise_block_std"] = float(nm.std())
    feats["noise_block_cv"] = float(nm.std() / (nm.mean() + 1e-3))
    edges = cv2.Canny(g.astype(np.uint8), 80, 160)
    feats["edge_density"] = float((edges > 0).mean())

    # JPEG 8x8 block-grid artefact strength vs. shifted grid (re-saves / pastes break alignment)
    def grid_energy(offset):
        d = np.abs(np.diff(g, axis=1))
        cols = np.arange(d.shape[1])
        return float(d[:, (cols + offset) % 8 == 7].mean())
    base = grid_energy(0)
    shifted = np.mean([grid_energy(o) for o in range(1, 8)])
    feats["grid_ratio"] = float(base / (shifted + 1e-3))

    # _bag_features (JPEG grid alignment) tested: no accuracy gain on held-out data, so not used in the live path
    meta = metadata_flags(image_bytes)
    feats["editor_tag"] = 1.0 if meta["editor_tag"] else 0.0
    feats["is_jpeg"] = 1.0 if meta["is_jpeg"] else 0.0
    feats["aspect"] = img.size[0] / img.size[1]
    return feats, ela


def fallback_risk(f: dict) -> float:
    """Used until a trained model exists. Transparent and conservative."""
    return float(min(1.0, 0.5 * f["ela_score"] + 0.9 * f["editor_tag"]))   # editing-software tag in metadata is strong
