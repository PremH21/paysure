"""Make an auxiliary manifest from the AIForge-Doc dataset (forged receipts/forms; NOT phone payment screens).

STATUS: tested only on a mock folder layout - I could not download the real (gated, 10 GB) dataset.
It looks for image files (png/jpg) anywhere under the folder, skips anything whose path contains 'mask', and uses
metadata.jsonl (if present) to name groups by the inpainting tool. Nothing is copied: the manifest points at your files.

Usage:
  python train/import_aiforge.py DATASET_DIR --forged-only [--max 600] [--out data/manifest_aiforge.json]
  python train/import_aiforge.py DATASET_DIR --authentic DIR_OF_REAL_DOCS [--max 600]
Forged images with NO authentic counterpart teach the model the shortcut 'receipt-looking = fake', so you must give
--authentic or explicitly accept the risk with --forged-only.
Then:  python train/make_manifest.py data/raw data/manifest.json --add data/manifest_aiforge.json
Groups are named aux_*: used for training only, never for thresholds or test numbers.
"""
import json
import os
import random
import sys

EXT = {".png", ".jpg", ".jpeg"}


def images_under(d):
    out = []
    for dp, _, files in os.walk(d):
        for fn in files:
            p = os.path.join(dp, fn)
            if os.path.splitext(fn)[1].lower() in EXT and "mask" not in p.lower():
                out.append(p)
    return sorted(out)


def load_meta(d):
    meta = {}
    for dp, _, files in os.walk(d):
        if "metadata.jsonl" in files:
            for line in open(os.path.join(dp, "metadata.jsonl"), encoding="utf-8"):
                line = line.strip()
                if line:
                    j = json.loads(line)
                    if j.get("new_id"):
                        meta[str(j["new_id"])] = j
    return meta


def build(dataset_dir, authentic_dir=None, forged_only=False, max_per_group=600, seed=0):
    if authentic_dir is None and not forged_only:
        raise SystemExit("Refusing: only-forged auxiliary data teaches a wrong shortcut. Pass --authentic DIR or --forged-only.")
    rnd = random.Random(seed)
    meta = load_meta(dataset_dir)
    groups = {}
    for p in images_under(dataset_dir):
        stem = os.path.splitext(os.path.basename(p))[0]
        tool = (meta.get(stem) or {}).get("assigned_tool", "forged")
        groups.setdefault(f"aux_aiforge_fake_{tool}".replace("-", "_"), []).append(p)
    rows = []
    for g, ps in groups.items():
        rnd.shuffle(ps)
        rows += [{"p": p.replace("\\", "/"), "y": 1, "g": g} for p in ps[:max_per_group]]
    if authentic_dir:
        ps = images_under(authentic_dir)
        rnd.shuffle(ps)
        rows += [{"p": p.replace("\\", "/"), "y": 0, "g": "aux_aiforge_genuine"} for p in ps[:max_per_group * max(1, len(groups))]]
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    def opt(name, default=None):
        return a[a.index(name) + 1] if name in a else default
    rows = build(a[0], opt("--authentic"), "--forged-only" in a, int(opt("--max", 600)))
    out = opt("--out", "data/manifest_aiforge.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(rows, open(out, "w"))
    print(f"wrote {out}: {len(rows)} images", {g: sum(1 for r in rows if r['g'] == g) for g in sorted({r['g'] for r in rows})})
