"""Turn folders of labelled screenshots into the training manifest.

Layout (you create it):   data/raw/<group>/<any images, subfolders allowed>
Group name rules (the folder name decides the label):
    contains 'genuine'                      -> label 0 (real payment screenshot)
    contains 'fake', 'tamper' or 'forged'   -> label 1 (edited / fabricated)
    prefix 'novel_'  -> NEVER trained on; used only to test unseen attack types or unseen apps
    prefix 'aux_'    -> extra training data from another domain (e.g. receipts); never used to pick thresholds or test
Examples: genuine_gpay_original, genuine_phonepe_whatsapp, fake_photopea_amount, fake_paste_region,
          novel_fake_screenshot_of_edit, novel_genuine_paytm   (hold out a whole app: name all its folders novel_*)

Usage: python train/make_manifest.py [data/raw] [data/manifest.json] [--add other_manifest.json ...]
"""
import hashlib
import json
import os
import sys

from PIL import Image

EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
FAKE_WORDS = ("fake", "tamper", "forged")


def label_for(group: str):
    core = group.lower()
    for pre in ("novel_", "aux_"):
        if core.startswith(pre):
            core = core[len(pre):]
    if "genuine" in core:
        return 0
    if any(w in core for w in FAKE_WORDS):
        return 1
    return None


def build(root: str, extra=()):
    """Returns (rows, errors, warnings)."""
    rows, errors, warnings, seen = [], [], [], {}
    if not os.path.isdir(root):
        return [], [f"folder not found: {root}"], []
    for group in sorted(os.listdir(root)):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir):
            continue
        y = label_for(group)
        if y is None:
            errors.append(f"folder '{group}': name must contain 'genuine' or 'fake'/'tamper'/'forged' (after optional novel_/aux_ prefix)")
            continue
        for dp, _, files in os.walk(gdir):
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in EXT:
                    continue
                p = os.path.join(dp, fn)
                try:
                    with Image.open(p) as im:
                        im.verify()
                except Exception:
                    warnings.append(f"skipped unreadable image: {p}")
                    continue
                h = hashlib.sha1(open(p, "rb").read()).hexdigest()
                if h in seen:
                    other = seen[h]
                    if other[1] != y:
                        errors.append(f"SAME image labelled both genuine and fake: {p} and {other[0]}")
                    else:
                        warnings.append(f"duplicate skipped: {p} (same as {other[0]})")
                    continue
                seen[h] = (p, y)
                rows.append({"p": p.replace("\\", "/"), "y": y, "g": group})
    for path in extra:
        for r in json.load(open(path)):
            rows.append(r)
    return rows, errors, warnings


def summarize(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["g"], [r["y"], 0])[1] += 1
    return groups


def main(argv):
    extra, args, i = [], [], 0
    while i < len(argv):
        if argv[i] == "--add":
            extra.append(argv[i + 1]); i += 2
        else:
            args.append(argv[i]); i += 1
    root = args[0] if args else "data/raw"
    out = args[1] if len(args) > 1 else "data/manifest.json"
    rows, errors, warnings = build(root, extra)
    for w in warnings[:20]:
        print("warning:", w)
    if len(warnings) > 20:
        print(f"... {len(warnings) - 20} more warnings")
    if errors:
        print("\nERRORS (fix these, nothing written):")
        for e in errors:
            print(" -", e)
        return 1
    groups = summarize(rows)
    print(f"\n{'group':36s}{'label':>7s}{'images':>8s}")
    for g, (y, n) in sorted(groups.items()):
        flag = "   <- needs >=10 to be usable" if n < 10 and not g.startswith(("novel_", "aux_")) else ""
        print(f"{g:36s}{'fake' if y else 'real':>7s}{n:8d}{flag}")
    main_rows = [r for r in rows if not r["g"].startswith(("novel_", "aux_"))]
    if not any(r["y"] == 0 for r in main_rows) or not any(r["y"] == 1 for r in main_rows):
        print("\nERROR: need at least one genuine_* group AND one fake_* group (not novel_/aux_).")
        return 1
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(rows, open(out, "w"))
    print(f"\nwrote {out} with {len(rows)} images")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
