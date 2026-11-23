"""Compute features for every image in a manifest (parallel). Usage: python build_features.py manifest.json out.json"""
import io
import json
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402
from paysure.features import extract_features  # noqa: E402


def one(r):
    try:
        data = open(r["p"], "rb").read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        f, _ = extract_features(img, data)
        return dict(f=f, y=r["y"], g=r["g"], p=r["p"])
    except Exception as e:                      # one bad file must not kill a long run
        print("skipped", r["p"], e, flush=True)
        return None


if __name__ == "__main__":
    rows = json.load(open(sys.argv[1]))
    with Pool() as pool:
        out = [x for x in pool.imap(one, rows, chunksize=10) if x]
    json.dump(out, open(sys.argv[2], "w"))
    print("features for", len(out), "of", len(rows), "images")
