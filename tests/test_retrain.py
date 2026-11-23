import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from paysure.retrain import drift_alert, retrain
from paysure.store import Store

KEYS = ["a", "b"]
rng = np.random.RandomState(0)


def fill(st, n, shift=0.0):
    for _ in range(n):
        lab = int(rng.rand() > 0.5)
        f = {"a": float(rng.randn() + 2 * lab + shift), "b": float(rng.randn())}
        cid = st.log_check(f, "yellow"); st.set_label(cid, lab)


class Retrain(unittest.TestCase):
    def test_refuses_without_enough_labels(self):
        st = Store(":memory:"); fill(st, 10)
        r = retrain(st, np.zeros((4, 2)), np.array([0, 1, 0, 1]), KEYS)
        self.assertFalse(r["promoted"])

    def test_challenger_promoted_when_champion_is_useless(self):
        st = Store(":memory:"); fill(st, 300)
        X0 = rng.randn(40, 2); y0 = (rng.rand(40) > 0.5).astype(int)
        bad = GradientBoostingClassifier(random_state=0).fit(X0, y0)         # trained on noise
        r = retrain(st, X0, y0, KEYS, champion=bad)
        self.assertTrue(r["promoted"], r["reason"])

    def test_drift(self):
        self.assertFalse(drift_alert(1, 40))
        self.assertTrue(drift_alert(12, 40))
        self.assertFalse(drift_alert(5, 10))     # too few samples


if __name__ == "__main__":
    unittest.main()
