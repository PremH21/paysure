"""Extract fields from OCR text and from bank credit SMS text; validate them."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
UTR_RE = re.compile(r"\b(\d{12})\b")
UPI_ID_RE = re.compile(r"\b([a-z0-9._-]{2,}@[a-z]{2,})\b", re.I)
SUCCESS_WORDS = ("successful", "success", "paid", "completed", "sent")
FAILED_WORDS = ("failed", "declined", "unsuccessful", "rejected", "cancelled", "canceled", "reversed", "refunded")
PENDING_WORDS = ("pending", "processing", "in progress", "awaiting", "scheduled")
PAYER_RE = re.compile(r"(?:from|by)\s+(?:vpa\s+)?([a-z0-9._-]{2,}@[a-z]{2,})", re.I)

DATE_FORMATS = [
    "%d %b %Y, %I:%M %p", "%d %b %Y %I:%M %p", "%d %B %Y, %I:%M %p",
    "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%y %H:%M", "%d-%b-%y %H:%M",
    "%d %b %Y, %H:%M", "%d %b %Y %H:%M",
]
DATE_FINDERS = [
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4},?\s+\d{1,2}:\d{2}\s*[AaPp][Mm]"),
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4},?\s+\d{1,2}:\d{2}"),
    re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+\d{1,2}:\d{2}"),
    re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}\s+\d{1,2}:\d{2}"),
]


def _to_amount(s: str) -> float:
    return float(s.replace(",", ""))


def _parse_dt(text: str):
    for finder in DATE_FINDERS:
        m = finder.search(text)
        if not m:
            continue
        raw = re.sub(r"\s+", " ", m.group(0)).strip()
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
    return None


@dataclass
class Fields:
    amount: float | None = None
    utr: str | None = None
    upi_id: str | None = None
    when: datetime | None = None
    status_ok: bool = False
    status_state: str = "unknown"   # success | pending | failed | unknown
    payer: str | None = None


def parse_screenshot_text(text: str) -> Fields:
    f = Fields()
    amounts = [_to_amount(a) for a in AMOUNT_RE.findall(text)]
    if amounts:
        f.amount = amounts[0]
    m = UTR_RE.search(text)
    if m:
        f.utr = m.group(1)
    m = UPI_ID_RE.search(text)
    if m:
        f.upi_id = m.group(1).lower()
    f.when = _parse_dt(text)
    low = text.lower()
    if any(w in low for w in FAILED_WORDS):
        f.status_state = "failed"
    elif any(w in low for w in PENDING_WORDS):
        f.status_state = "pending"
    elif any(w in low for w in SUCCESS_WORDS):
        f.status_state = "success"
    f.status_ok = f.status_state == "success"
    return f


def parse_credit_sms(text: str, now: datetime | None = None) -> Fields:
    """Handles common bank formats: 'Rs 500.00 credited ... UPI Ref 123456789012'.
    Many SMS carry no time; then the time is the moment the merchant pastes it."""
    f = Fields()
    low = text.lower()
    if not any(w in low for w in ("credited", "received", "credit", "cr.")):
        return f
    m = AMOUNT_RE.search(text)
    if m:
        f.amount = _to_amount(m.group(1))
    m = re.search(r"(?:ref(?:erence)?(?:\s*no)?\.?|rrn|utr|upi)[^\d]{0,15}(\d{12})", text, re.I) or UTR_RE.search(text)
    if m:
        f.utr = m.group(1)
    f.when = _parse_dt(text) or now
    f.status_ok = True
    f.status_state = "success"
    m = PAYER_RE.search(text)
    if m:
        f.payer = m.group(1).lower()
    return f


def validate_fields(f: Fields, now: datetime | None = None) -> list[str]:
    """Plausibility checks. Returns a list of human-readable problems."""
    now = now or datetime.now()
    problems = []
    if f.amount is None:
        problems.append("amount missing")
    elif f.amount <= 0 or f.amount > 1_00_000:  # UPI per-txn cap is 1 lakh for most
        problems.append("amount outside UPI limits")
    if f.utr is None:
        problems.append("12-digit UPI reference missing or malformed")
    if f.when is None:
        problems.append("date/time missing")
    elif f.when > now + timedelta(minutes=5):
        problems.append("timestamp is in the future")
    elif now - f.when > timedelta(days=1):
        problems.append("screenshot is more than a day old (possible reuse)")
    if f.status_state == "pending":
        problems.append("payment is shown as pending, not successful")
    elif f.status_state == "failed":
        problems.append("payment is shown as failed or reversed")
    elif not f.status_ok:
        problems.append("no success status text")
    return problems
