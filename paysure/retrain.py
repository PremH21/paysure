"""Self-labelling loop: merchant-confirmed outcomes (store.labels) -> challenger model -> promote only if better.

Champion-vs-challenger: both are scored on the SAME held-out confirmed labels; the challenger replaces the champion only if
it has at least as high F1 with no more false alarms. Needs a minimum number of confirmed labels of each class."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

MIN_PER_CLASS = 30


def retrain(store, base_X, base_y, keys, champion=None, seed=0):
    lab = store.labelled()
    ys = np.array([l for _, l in lab])
    if len(ys) < 2 * MIN_PER_CLASS or min(ys.sum(), len(ys) - ys.sum()) < MIN_PER_CLASS:
        return {"promoted": False, "reason": f"need >= {MIN_PER_CLASS} confirmed genuine and fake each", "model": champion}
    X = np.array([[f[k] for k in keys] for f, _ in lab])
    Xtr, Xte, ytr, yte = train_test_split(X, ys, test_size=0.4, random_state=seed, stratify=ys)
    chal = GradientBoostingClassifier(random_state=seed).fit(np.vstack([base_X, Xtr]), np.concatenate([base_y, ytr]))
    def score(m):
        pred = (m.predict_proba(Xte)[:, 1] >= 0.5).astype(int)
        return f1_score(yte, pred), float(((pred == 1) & (yte == 0)).sum())
    if champion is None:
        return {"promoted": True, "reason": "no champion yet", "model": chal}
    (f1_c, fa_c), (f1_n, fa_n) = score(champion), score(chal)
    ok = f1_n >= f1_c and fa_n <= fa_c
    return {"promoted": ok, "reason": f"champion F1={f1_c:.3f} FA={fa_c:.0f}; challenger F1={f1_n:.3f} FA={fa_n:.0f}",
            "model": chal if ok else champion}


def drift_alert(recent_genuine_flagged: int, recent_genuine_total: int, baseline_rate=0.05, min_n=30) -> bool:
    """Layouts changed when confirmed-genuine screenshots start being flagged far more than the baseline false-alarm rate."""
    return recent_genuine_total >= min_n and recent_genuine_flagged / recent_genuine_total > 2 * baseline_rate
