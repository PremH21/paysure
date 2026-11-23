import os, sys, unittest
from datetime import datetime
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__))); sys.path.insert(0, os.path.dirname(__file__))
from make_samples import make_screen, to_jpeg
from paysure.engine import verify
from paysure.model import Calibrated
from paysure.store import Store

NOW = datetime(2026, 10, 26, 14, 40)


class Fixed:
    """Stub model returning a fixed risk (already on the 0.5=flag / 0.8=red scale)."""
    def __init__(self, r): self.r = r
    def predict_proba(self, X): return np.array([[1 - self.r, self.r]])


def run(risk):
    img = to_jpeg(make_screen("500", "999988887777", "26 Oct 2026, 02:38 PM"))
    return verify(img, Store(":memory:"), now=NOW, merchant_vpas={"shopkeeper@okbank"}, model=Fixed(risk))


class Policy(unittest.TestCase):
    def test_low_risk_plain_yellow(self):
        v = run(0.2); self.assertEqual(v.color, "yellow"); self.assertNotIn("editing", v.reason)

    def test_moderate_risk_warns_but_not_red(self):
        v = run(0.6); self.assertEqual(v.color, "yellow"); self.assertIn("signs of editing", v.reason)
        self.assertTrue(v.signals["suspicious"])

    def test_very_high_risk_red(self):
        self.assertEqual(run(0.9).color, "red")

    def test_forensics_never_green(self):
        self.assertNotEqual(run(0.0).color, "green")

    def test_calibration_maps_thresholds(self):
        class G:
            def predict_proba(self, X): return np.array([[0.5, 0.5], [0.03, 0.97], [0.01, 0.99]])
        c = Calibrated(dict(model=G(), keys=[], t_flag=0.8, t_red=0.95))
        q = c.predict_proba(None)[:, 1]
        self.assertAlmostEqual(q[0], 0.5 * 0.5 / 0.8, places=3)       # below flag
        self.assertGreaterEqual(q[1], 0.8); self.assertGreaterEqual(q[2], 0.8)


if __name__ == "__main__":
    unittest.main()
