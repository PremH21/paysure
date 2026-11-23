"""Train the forensic classifier and report honestly.
Usage: python train/train.py data/feat.json [--out models/forgery.joblib]

Groups (folder names, see make_manifest.py):
  normal groups : split 70/30 into train/test (stratified per group); thresholds come from out-of-fold predictions
  novel_*       : never trained on, never used for thresholds -> shows how it copes with unseen attacks / unseen apps
  aux_*         : extra training data from another domain; used ONLY if it does not make the real test results worse
Policy: forensics alone may only say RED at a strict point (<=1% false alarms on genuine training images);
a looser point (<=2%) only raises a warning."""
import argparse, json, os, sys
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, train_test_split

ap = argparse.ArgumentParser()
ap.add_argument("feat"); ap.add_argument("--out", default="models/forgery.joblib")
args = ap.parse_args()

rows = json.load(open(args.feat))
keys = sorted(k for k in rows[0]["f"] if not k.startswith(("bag_", "line_", "tile_")))
X = np.array([[r["f"][k] for k in keys] for r in rows]); y = np.array([r["y"] for r in rows]); g = np.array([r["g"] for r in rows])
held = np.array([x.startswith("novel_") for x in g]); aux = np.array([x.startswith("aux_") for x in g])
main = np.where(~held & ~aux)[0]; aux_ix = np.where(aux)[0]
if len(set(y[main])) < 2:
    sys.exit("Need at least one genuine group and one fake group that are not novel_/aux_.")
small = sorted(grp for grp in set(g[main]) if (g[main] == grp).sum() < 10)
if small:
    sys.exit(f"These groups have fewer than 10 images, too few to split fairly: {small}. Add images or rename to novel_<name>.")
tr, te = train_test_split(main, test_size=0.3, random_state=1, stratify=g[main])


def thr(p, yv, far):
    for t in np.linspace(0.02, 0.99, 98):
        if (p[yv == 0] >= t).mean() <= far:
            return float(t)
    return 0.99


def mk():
    return GradientBoostingClassifier(random_state=0, n_estimators=200, max_depth=3)


def variant(use_aux):
    extra = aux_ix if use_aux else np.array([], dtype=int)
    oof = np.zeros(len(tr))
    for a_, b_ in StratifiedKFold(5, shuffle=True, random_state=7).split(tr, g[tr]):
        ix = np.concatenate([tr[a_], extra]).astype(int)
        oof[b_] = mk().fit(X[ix], y[ix]).predict_proba(X[tr[b_]])[:, 1]
    tf, trd = thr(oof, y[tr], 0.02), thr(oof, y[tr], 0.01)
    ix = np.concatenate([tr, extra]).astype(int)
    m = mk().fit(X[ix], y[ix])
    p = m.predict_proba(X[te])[:, 1]; fake = y[te] == 1
    s = dict(m=m, tf=tf, trd=trd, oof=oof, warn_recall=(p[fake] >= tf).mean(), red_recall=(p[fake] >= trd).mean(),
             warn_fa=(p[~fake] >= tf).mean(), red_fa=(p[~fake] >= trd).mean())
    return s


base = variant(False)
chosen, label = base, "main data only"
if len(aux_ix):
    with_aux = variant(True)
    print(f"aux data ({len(aux_ix)} images): test warn-recall {base['warn_recall']:.3f} -> {with_aux['warn_recall']:.3f}, "
          f"warn false-alarm {base['warn_fa']:.3f} -> {with_aux['warn_fa']:.3f}")
    if with_aux["warn_recall"] >= base["warn_recall"] and with_aux["warn_fa"] <= base["warn_fa"] + 0.005:
        chosen, label = with_aux, "main + aux data (aux did not hurt)"
    else:
        print("aux data did NOT help on your real test data, so it is not used.")
m, tf, trd, oof = chosen["m"], chosen["tf"], chosen["trd"], chosen["oof"]
n_gen = int((y[tr] == 0).sum()); n_fake = int((y[tr] == 1).sum())
if n_gen < 150 or n_fake < 150:
    print(f"\n*** CAUTION: only {n_gen} genuine and {n_fake} fake training images. Thresholds and the table below are NOT reliable "
          f"(aim for 150+ of each); do not quote these numbers in your report. ***")
print(f"\nmodel: {label}; features={len(keys)}  t_flag={tf:.2f} (<=2% FA)  t_red={trd:.2f} (<=1% FA)")
for grp in sorted(set(g[tr])):
    if y[tr][g[tr] == grp][0] == 0:
        mm = g[tr] == grp
        print(f"out-of-fold false alarm  {grp:28s} warn={(oof[mm] >= tf).mean():.3f}  red={(oof[mm] >= trd).mean():.3f}")
print(f"\n{'group':32s}{'n':>5s}{'RED':>8s}{'WARN+RED':>10s}")
for grp in sorted(set(g[~aux])):
    ix = np.where(g == grp)[0] if grp.startswith("novel_") else te[g[te] == grp]
    p = m.predict_proba(X[ix])[:, 1]
    kind = "genuine: want LOW" if y[ix][0] == 0 else "fake: want HIGH"
    kind += "   [NEVER TRAINED]" if grp.startswith("novel_") else ""
    print(f"{grp:32s}{len(ix):5d}{(p >= trd).mean():8.3f}{(p >= tf).mean():10.3f}   {kind}")
os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
import sklearn
joblib.dump(dict(model=m, keys=keys, t_flag=tf, t_red=trd, sklearn_version=sklearn.__version__), args.out)
print("\nsaved", args.out, f"(trained with scikit-learn {sklearn.__version__}; put the same version in requirements.txt before deploying)")
