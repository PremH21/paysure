"""Verification pipeline. Fail-closed: GREEN only when a trusted credit (tier>=2) matches on amount AND exact
reference number AND time, is unclaimed, and the payee is yours. Image forensics only matters when no credit exists."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytesseract
from PIL import Image

from .evidence import ingest_sms
from .features import extract_features, fallback_risk
from . import rrn
from .parsing import parse_screenshot_text, validate_fields
from .store import Store

# How far apart the screenshot time and the bank-alert time may be. Measure YOUR value with train/analyze_times.py.
TIME_TOLERANCE = timedelta(minutes=float(os.environ.get("TIME_TOLERANCE_MIN", "10")))
RISK_FLAG, RISK_RED = 0.5, 0.8   # forensics alone: >=0.5 warn (yellow), >=0.8 red

MESSAGES = {
    "en": {
        "green": "Payment received. Safe to hand over goods.",
        "yellow": "Not confirmed yet. Check your bank app before giving goods.",
        "red": "Likely fake. Do not hand over goods. Check your bank app.",
    },
    "hi": {
        "green": "भुगतान मिल गया है। सामान दे सकते हैं।",
        "yellow": "अभी पुष्टि नहीं हुई। सामान देने से पहले बैंक ऐप जांचें।",
        "red": "संभवतः नकली। सामान न दें। अपना बैंक ऐप जांचें।",
    },
    "kn": {
        "green": "ಹಣ ಬಂದಿದೆ. ಸರಕು ನೀಡಬಹುದು.",
        "yellow": "ಇನ್ನೂ ದೃಢಪಟ್ಟಿಲ್ಲ. ಸರಕು ನೀಡುವ ಮೊದಲು ಬ್ಯಾಂಕ್ ಆ್ಯಪ್ ಪರಿಶೀಲಿಸಿ.",
        "red": "ನಕಲಿ ಇರಬಹುದು. ಸರಕು ನೀಡಬೇಡಿ. ಬ್ಯಾಂಕ್ ಆ್ಯಪ್ ಪರಿಶೀಲಿಸಿ.",
    },
}


@dataclass
class Verdict:
    color: str
    reason: str
    messages: dict
    risk: float
    credit_match: bool
    signals: dict = field(default_factory=dict)
    heatmap: Image.Image | None = None
    check_id: int | None = None


def ocr_text(img: Image.Image) -> str:
    return pytesseract.image_to_string(img.convert("RGB"), config="--psm 11")


def _digits_differ(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b)) if len(a) == len(b) else 99


def verify(image_bytes: bytes, store: Store, now: datetime | None = None, lang: str = "en",
           pasted_sms: str | None = None, merchant_vpas: set[str] | None = None,
           text_override: str | None = None, model=None, use_orders: bool | None = None) -> Verdict:
    now = now or datetime.now()
    use_orders = store.has_orders() if use_orders is None else use_orders
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = text_override if text_override is not None else ocr_text(img)
    shot = parse_screenshot_text(text)
    problems = validate_fields(shot, now)

    if pasted_sms:  # tier 1 evidence: lands in ledger but can never make GREEN
        ingest_sms(store, pasted_sms, None, now, "pasted")

    feats, ela = extract_features(img, image_bytes)
    risk = float(model.predict_proba([[feats[k] for k in (getattr(model, 'keys', None) or sorted(feats))]])[0][1]) if model else fallback_risk(feats)

    dup = store.utr_seen(shot.utr)
    rep_ref = store.reporters_for_ref(shot.utr)
    network_fake = rep_ref >= 2     # one reporter alone cannot poison the network
    single_report = rep_ref == 1

    payee_bad = payee_unknown = False
    if merchant_vpas:
        vp = {v.lower() for v in merchant_vpas}
        if shot.upi_id is None:
            payee_unknown = True
        elif shot.upi_id.lower() not in vp:
            payee_bad = True

    rrn_ok = rrn.check(store, shot.utr, shot.when)   # None unless calibrated on your own trusted credits

    # ---- find credit evidence ----
    same_ref = store.credits_with_utr(shot.utr) if shot.utr else []
    tampered_ref = any(shot.amount is not None and abs(c["amount"] - shot.amount) > 0.01 for c in same_ref)
    exact = [c for c in same_ref if shot.amount is not None and abs(c["amount"] - shot.amount) <= 0.01]
    nearby = store.credits_near(shot.amount, now - timedelta(hours=2), now + timedelta(minutes=5)) \
        if shot.amount is not None else []
    near_miss = [c for c in nearby if shot.utr and c["utr"] and c["utr"] != shot.utr
                 and _digits_differ(c["utr"], shot.utr) <= 1]

    def time_ok(c):
        return shot.when is None or abs(shot.when - c["received_at"]) <= TIME_TOLERANCE

    trusted = [c for c in exact if c["trust"] >= 2 and time_ok(c)]
    weak = [c for c in exact if c["trust"] < 2 and time_ok(c)]
    claimed_only = trusted and all(c["claimed"] for c in trusted)

    signals = {"rrn_ok": rrn_ok, "fields": shot, "problems": problems, "risk": round(risk, 3), "dup": dup,
               "reporters_ref": rep_ref, "tampered_ref": tampered_ref}
    reasons: list[str] = []
    matched = False

    if network_fake:
        color = "red"; reasons.append("this payment proof was reported as fake by other shops")
    elif tampered_ref:
        color = "red"; reasons.append("your bank credit with this reference number is for a different amount")
    elif payee_bad:
        color = "red"; reasons.append("payment was made to a different UPI ID, not yours")
    elif dup or claimed_only:
        color = "red"; reasons.append("this payment was already used for an earlier purchase")
    elif trusted and not payee_unknown and not problems:
        c = next(c for c in trusted if not c["claimed"])
        order = next((o for o in store.open_orders(now) if abs(o["expected"] - shot.amount) <= 0.01), None) \
            if use_orders else None
        if use_orders and order is None:
            color = "yellow"
            reasons.append("money arrived, but it matches no open order (wrong, partial or extra amount); settle the bill first")
        else:
            color = "green"; matched = True
            reasons.append("amount, reference number and time match a verified bank alert")
            store.claim_credit(c["id"]); store.mark_seen(shot.utr, shot.amount)
            if order:
                store.close_order(order["id"], c["id"]); reasons.append(f"order {order['id']} paid")
    elif trusted:  # trusted credit but screenshot fields are off or payee unreadable
        color = "yellow"
        reasons.append("bank alert found, but " + "; ".join(problems + (["payee UPI ID unreadable"] if payee_unknown else [])))
    elif weak:
        color = "yellow"
        reasons.append("matching alert is only pasted text, which cannot be proven genuine; confirm in your bank app")
    elif near_miss:
        color = "yellow"
        reasons.append("a bank alert matches except one digit of the reference number; compare it by eye")
    elif rrn_ok is False:
        color = "red"; reasons.append("reference number cannot be right for the time shown (does not follow the pattern of your real payments)")
    elif risk >= RISK_RED or any("future" in p for p in problems):
        color = "red"
        if ela.bbox and ela.score >= 0.5: reasons.append("part of the image looks edited")
        reasons += problems or ["image forensics found strong signs of editing"]
    else:
        color = "yellow"; reasons.append("no matching bank alert yet; wait for it or check your bank app")
        if risk >= RISK_FLAG:
            reasons.append("the image also shows possible signs of editing; do not hand over goods until your bank app confirms")
        if single_report: reasons.append("another shop reported something similar")

    flags_seen = sorted({f for c in (trusted + weak) for f in c["flags"]})
    if flags_seen and color != "green":
        reasons.append("alert notes: " + "; ".join(flags_seen))

    signals["ela_score"] = round(ela.score, 3)
    signals["suspicious"] = risk >= RISK_FLAG
    check_id = store.log_check(feats, color)
    return Verdict(color, "; ".join(reasons), MESSAGES.get(lang, MESSAGES["en"]), risk, matched, signals,
                   ela.heatmap, check_id)
