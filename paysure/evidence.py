"""Credit evidence: how much do we trust the thing that says 'money arrived'?

Trust tiers (only tier >= 2 can ever produce GREEN):
  3  signed gateway webhook (HMAC verified)         - cryptographic proof
  2  SMS/notification read ON THE DEVICE by the app  - real sender header + OS receive time, not typed by anyone
  1  pasted text                                     - could be a spoofed SMS or typed; YELLOW at most
"""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime

from .parsing import parse_credit_sms
from .store import Store

HEADER_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{3,8}(-[A-Z])?$")  # Indian DLT style e.g. VM-HDFCBK-S
BAL_RE = re.compile(r"(?:avl\.?\s*bal(?:ance)?|available\s*bal(?:ance)?|bal)[^\d]{0,12}([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)


def verify_webhook(body: bytes, signature_hex: str, secret: str) -> bool:
    """Razorpay-style: signature = HMAC_SHA256(secret, raw_body). Constant-time compare."""
    if not secret:            # an unset secret would let anyone sign with an empty key
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_hex or "")


def _balance_flags(store: Store, text: str, amount: float, trust: int, flags: list[str]):
    m = BAL_RE.search(text)
    balance = float(m.group(1).replace(",", "")) if m else None
    if balance is not None:
        if balance + 0.01 < amount:
            flags.append("available balance is lower than the credited amount (impossible)")
            trust = min(trust, 1)
        last = store.last_balance()
        if last is not None and abs((last + amount) - balance) > 0.01:
            flags.append("balance does not continue from the previous alert")
            trust = min(trust, 1)
        if trust >= 2 or last is None:
            store.set_last_balance(balance)
    else:
        flags.append("alert shows no balance to cross-check")
    return balance, trust


def _finish(store, f, text, trust, flags, source, received_at):
    if not f.utr:
        flags.append("alert has no reference number")
    balance, trust = _balance_flags(store, text, f.amount, trust, flags)
    cid = store.add_credit(f.amount, f.utr, received_at, source, trust, flags, balance, f.payer)
    from .rrn import recalibrate
    recalibrate(store)
    return cid, flags


def ingest_sms(store: Store, text: str, sender: str | None, received_at: datetime,
               source: str, allowed_senders: set[str] | None = None):
    """Parse a bank credit SMS into the ledger with a trust level and authenticity flags.
    source: 'device_sms' | 'pasted'. allowed_senders: your bank's header codes, e.g. {'HDFCBK'}."""
    f = parse_credit_sms(text, received_at)
    if f.amount is None:
        return None, ["not a credit message"]
    flags: list[str] = []
    trust = 2 if source == "device_sms" else 1
    if source == "device_sms":
        if not sender or not HEADER_RE.match(sender.strip().upper()):
            flags.append("sender header has unusual format"); trust = 1
        elif allowed_senders is not None:
            if sender.strip().upper().split("-")[1] not in {s.upper() for s in allowed_senders}:
                flags.append("sender is not one of your bank's headers"); trust = 1
        else:
            flags.append("no bank headers configured, so sender is unverified"); trust = 1
    else:
        flags.append("pasted text cannot be proven to come from your bank")
    return _finish(store, f, text, trust, flags, source, received_at)


def ingest_notification(store: Store, text: str, package: str | None, received_at: datetime,
                        allowed_packages: set[str] | None):
    """Notification captured by the companion app. A forged notification comes from a different app package
    (e.g. a 'fake notification' app), so the package name must be on YOUR allowlist. Verify the names on your phone."""
    f = parse_credit_sms(text, received_at)
    if f.amount is None:
        return None, ["not a credit message"]
    flags: list[str] = []
    trust = 2
    if not allowed_packages:
        flags.append("no trusted app packages configured, so notification is unverified"); trust = 1
    elif package not in allowed_packages:
        flags.append(f"notification came from app '{package}', which is not on your trusted list"); trust = 1
    return _finish(store, f, text, trust, flags, "notification", received_at)


def ingest_webhook(store: Store, body: bytes, signature: str, secret: str, amount: float, utr: str,
                   received_at: datetime):
    """Signed gateway event: the highest trust tier."""
    if not verify_webhook(body, signature, secret):
        return None
    return store.add_credit(amount, utr, received_at, "gateway_webhook", 3, [], None)
