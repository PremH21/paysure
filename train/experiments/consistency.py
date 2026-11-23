"""Within-image consistency forensics.

Idea: in a genuine screenshot every piece of text shares the same compression/rendering history. An edited number
(or pasted block) behaves differently from its neighbours. We measure each OCR word box and each image tile, then ask
'how much does the most unusual one stand out from the rest of THIS image?' - no knowledge of the attack type needed.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytesseract
from PIL import Image


def ocr_words(img: Image.Image):
    """One OCR pass -> (text, words). words: list of (x, y, w, h, conf, str). Text keeps line structure."""
    d = pytesseract.image_to_data(img.convert("RGB"), config="--psm 11", output_type=pytesseract.Output.DICT)
    words, lines = [], {}
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if not t:
            continue
        conf = float(d["conf"][i])
        box = (d["left"][i], d["top"][i], d["width"][i], d["height"][i])
        words.append((*box, conf, t))
        lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append((box[0], box[1], t))
    ordered = sorted(lines.values(), key=lambda ws: (min(w[1] for w in ws), min(w[0] for w in ws)))
    text = "\n".join(" ".join(w[2] for w in sorted(ws)) for ws in ordered)
    return text, words


def _rz(v: np.ndarray, floor: float) -> np.ndarray:
    med = np.median(v)
    mad = max(float(np.median(np.abs(v - med))), floor)
    return (v - med) / (1.4826 * mad)


def _stats_for_box(ela: np.ndarray, lap_abs: np.ndarray, resid: np.ndarray, box):
    x, y, w, h = box
    sl = (slice(max(y, 0), y + h), slice(max(x, 0), x + w))
    e, l, r = ela[sl], lap_abs[sl], resid[sl]
    if e.size < 30:
        return None
    edge = float(l.mean()) + 1.0
    top = np.sort(l.ravel())[-max(3, l.size // 10):].mean()          # edge sharpness of the strongest 10% pixels
    return float(e.mean()) / edge, float(r.mean()) / edge, float(top)


def word_features(img: Image.Image, ela90: np.ndarray, words) -> dict:
    out = dict(line_ela_max=0.0, line_noise_max=0.0, line_sharp_max=0.0, line_frac_out=0.0, line_n=0.0)
    g = np.asarray(img.convert("L"), dtype=np.float32)
    lap_abs = np.abs(cv2.Laplacian(g, cv2.CV_32F))
    resid = np.abs(g - cv2.medianBlur(g.astype(np.uint8), 3).astype(np.float32))
    rows = []
    for x, y, w, h, conf, t in words:
        if conf < 40 or len(t) < 2:
            continue
        s = _stats_for_box(ela90, lap_abs, resid, (x, y, w, h))
        if s:
            rows.append(s)
    if len(rows) < 4:
        return out
    a = np.array(rows)
    z = np.stack([_rz(a[:, 0], 0.05), _rz(a[:, 1], 0.05), _rz(np.log1p(a[:, 2]), 0.05)], axis=1)
    out.update(line_ela_max=float(np.abs(z[:, 0]).max()), line_noise_max=float(np.abs(z[:, 1]).max()),
               line_sharp_max=float(np.abs(z[:, 2]).max()), line_frac_out=float((np.abs(z).max(axis=1) > 3.5).mean()),
               line_n=float(len(rows)))
    return out


def tile_features(ela_arrs: dict, g: np.ndarray, tile: int = 32) -> dict:
    """Per-tile outlier score within the image (local, so a small edit is not diluted by the whole page)."""
    H, W = g.shape
    lap = np.abs(cv2.Laplacian(g, cv2.CV_32F))
    metrics = []
    for q, a in sorted(ela_arrs.items()):
        metrics.append(a)
    metrics.append(lap)
    cols = []
    for y in range(0, H - tile + 1, tile):
        for x in range(0, W - tile + 1, tile):
            if g[y:y + tile, x:x + tile].std() < 4:
                continue
            cols.append([float(m[y:y + tile, x:x + tile].mean()) for m in metrics])
    if len(cols) < 8:
        return dict(tile_max=0.0, tile_top3=0.0, tile_frac=0.0)
    c = np.array(cols)
    z = np.stack([_rz(c[:, j], 0.1 * (c[:, j].mean() + 1e-3)) for j in range(c.shape[1])], axis=1)
    s = np.abs(z).max(axis=1)
    return dict(tile_max=float(s.max()), tile_top3=float(np.sort(s)[-3:].mean()), tile_frac=float((s > 4).mean()))
