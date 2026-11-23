"""Loads the trained forgery model. Probability is rescaled piecewise so that
   0.5 == 'flag' operating point (<=2% false alarms on genuine validation images)
   0.8 == 'red'  operating point (<=1% false alarms)."""
import os

import numpy as np


class Calibrated:
    def __init__(self, bundle):
        self.m, self.keys = bundle["model"], bundle["keys"]
        import sklearn
        v = bundle.get("sklearn_version")
        if v and v != sklearn.__version__:
            print(f"WARNING: model was trained with scikit-learn {v} but {sklearn.__version__} is installed; "
                  "pin the same version in requirements.txt or retrain.")
        self.t_flag, self.t_red = bundle["t_flag"], max(bundle["t_red"], bundle["t_flag"] + 1e-3)

    def predict_proba(self, X):
        p = self.m.predict_proba(X)[:, 1]
        tf, tr = self.t_flag, self.t_red
        q = np.interp(p, [0.0, tf, tr, 1.0], [0.0, 0.5, 0.8, 1.0])
        return np.stack([1 - q, q], axis=1)


def load(path=None):
    try:
        import joblib
        path = path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "forgery.joblib")
        return Calibrated(joblib.load(path))
    except Exception:
        return None
