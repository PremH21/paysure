"""EXPERIMENT RECORD (result: consistency features + anomaly blend gave NO gain; see README). Honest comparison on identical splits.
 A  = old features (22)             B = old + consistency features (line_*, tile_*)
 Models: supervised GB, and 'blend' = supervised + one-class anomaly detector trained on GENUINE images only.
Novel families (novel_*) are never used in training or threshold selection.
Usage: python eval2.py feat.json [--save]"""
import json
import os
import sys

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

rows = json.load(open(sys.argv[1]))
SAVE = "--save" in sys.argv
allkeys = sorted(k for k in rows[0]["f"] if not k.startswith("bag_"))
NEW = [k for k in allkeys if k.startswith(("line_", "tile_"))]
OLD = [k for k in allkeys if k not in NEW]
y = np.array([r["y"] for r in rows]); g = np.array([r["g"] for r in rows])
novel = np.array([x.startswith("novel_") for x in g])
idx = np.where(~novel)[0]
tr, te = train_test_split(idx, test_size=0.3, random_state=1, stratify=g[idx])
tr, va = train_test_split(tr, test_size=0.25, random_state=2, stratify=g[tr])
groups = sorted(set(g))


def M(keys):
    return np.array([[r["f"][k] for k in keys] for r in rows])


def thr_for(p, yv, far=0.02):
    for t in np.linspace(0.02, 0.98, 97):
        if (p[yv == 0] >= t).mean() <= far:
            return float(t)
    return 0.98


def run(keys, blend, tag):
    X = M(keys)
    gb = GradientBoostingClassifier(random_state=0, n_estimators=200, max_depth=3).fit(X[tr], y[tr])
    sc = StandardScaler().fit(X[tr][y[tr] == 0])
    iso = IsolationForest(n_estimators=300, random_state=0, contamination="auto").fit(sc.transform(X[tr][y[tr] == 0]))

    def score(ix):
        p = gb.predict_proba(X[ix])[:, 1]
        if not blend:
            return p
        a = -iso.score_samples(sc.transform(X[ix]))                 # higher = more unlike genuine
        return np.maximum(p, np.clip((a - a_lo) / (a_hi - a_lo + 1e-9), 0, 1))
    if blend:
        a_tr = -iso.score_samples(sc.transform(X[va][y[va] == 0]))
        a_lo, a_hi = np.percentile(a_tr, 50), np.percentile(a_tr, 99.5)
    t = thr_for(score(va), y[va])
    out = {}
    pt = score(te) >= t
    out["all_seen"] = (pt[y[te] == 1].mean(), pt[y[te] == 0].mean())
    for grp in groups:
        if grp.startswith("novel_"):
            ix = np.where(g == grp)[0]; out[grp] = (np.mean(score(ix) >= t), None)
        else:
            ix = te[g[te] == grp]; out[grp] = (np.mean(score(ix) >= t), None)
    print(f"\n--- {tag} | {len(keys)} features | threshold {t:.2f} ---")
    print(f"  overall (seen attacks)  recall {out['all_seen'][0]:.3f}   false-alarm on genuine {out['all_seen'][1]:.3f}")
    for grp in groups:
        lab = "FALSE-ALARM" if y[g == grp][0] == 0 else "recall     "
        tagn = "  [NEVER TRAINED]" if grp.startswith("novel_") else ""
        print(f"  {grp:22s} {lab} {out[grp][0]:.3f}{tagn}")
    return gb, iso, sc, t, a_lo if blend else None, a_hi if blend else None


run(OLD, False, "A  old features, supervised only")
run(OLD + NEW, False, "B  + consistency features, supervised")
res = run(OLD + NEW, True, "C  + consistency + one-class anomaly blend")

if SAVE:
    gb, iso, sc, t, lo, hi = res
    os.makedirs("models", exist_ok=True)
    joblib.dump(dict(model=gb, keys=OLD + NEW, threshold=t, iso=iso, scaler=sc, a_lo=lo, a_hi=hi), "models/forgery.joblib")
    print("saved models/forgery.joblib")
