"""Self-calibrating reference-number (RRN) structure check.

HYPOTHESIS (not assumed true): a 12-digit UPI reference is  Y DDD HH NNNNNN
(last digit of year, day-of-year, hour, 6-digit serial). Banks/apps may differ, so the rule is OFF until the
merchant's own TRUSTED credits show >=90% of >=20 references following it. If they do, a screenshot whose
reference cannot be reconciled with its own claimed time is flagged. If they don't, the rule stays off - safe.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .store import Store

MIN_SAMPLES, MIN_RATE = 20, 0.90


def decode(utr: str, around: datetime):
    """Return the datetime (hour precision) the reference claims, choosing the year nearest to `around`."""
    if not (utr and len(utr) == 12 and utr.isdigit()):
        return None
    y, doy, hh = int(utr[0]), int(utr[1:4]), int(utr[4:6])
    if not (1 <= doy <= 366 and 0 <= hh <= 23):
        return None
    best = None
    for yr in range(around.year - 5, around.year + 2):
        if yr % 10 != y:
            continue
        try:
            d = datetime(yr, 1, 1) + timedelta(days=doy - 1, hours=hh)
        except ValueError:
            continue
        if best is None or abs(d - around) < abs(best - around):
            best = d
    return best


def consistent(utr: str, when: datetime, tol=timedelta(minutes=100)) -> bool:
    d = decode(utr, when)
    return d is not None and abs((d + timedelta(minutes=30)) - when) <= tol


def recalibrate(store: Store):
    rows = store.trusted_credits(2)
    if len(rows) < MIN_SAMPLES:
        store.kv_set("rrn_rule", "off"); return
    ok = sum(consistent(u, t) for u, t in rows)
    store.kv_set("rrn_rule", "on" if ok / len(rows) >= MIN_RATE else "off")


def check(store: Store, utr: str | None, when: datetime | None):
    """True/False when the rule is calibrated ON; None when not applicable."""
    if not utr or not when or store.kv_get("rrn_rule") != "on":
        return None
    return consistent(utr, when)
