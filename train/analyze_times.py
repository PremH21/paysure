"""Measure the real gap between the time printed on a screenshot and the time the bank alert arrived on your phone.
Make a CSV:  screenshot_time,alert_time      (both like 2026-11-24 14:05)   - one row per real payment
Usage: python train/analyze_times.py times.csv
Use the 99th percentile (rounded up, plus a margin) as TIME_TOLERANCE_MIN on the server."""
import csv
import math
import sys
from datetime import datetime


def gaps_minutes(path):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8")):
        a = datetime.fromisoformat(row["screenshot_time"].strip()); b = datetime.fromisoformat(row["alert_time"].strip())
        out.append(abs((a - b).total_seconds()) / 60)
    return sorted(out)


def pct(v, q):
    return v[min(len(v) - 1, math.ceil(q * len(v)) - 1)]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    v = gaps_minutes(sys.argv[1])
    if len(v) < 30:
        print(f"CAUTION: only {len(v)} rows; collect 100+ before trusting percentiles.")
    print(f"n={len(v)}  median={pct(v, .5):.1f} min  p90={pct(v, .9):.1f}  p99={pct(v, .99):.1f}  max={v[-1]:.1f}")
    print(f"suggested TIME_TOLERANCE_MIN = {math.ceil(pct(v, .99)) + 2}")
