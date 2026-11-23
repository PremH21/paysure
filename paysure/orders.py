"""Order binding + UPI QR generation + QR guard + refund guard.

Why: if every payment must match ONE open order (exact expected amount, short time window), then
reusing screenshots, borrowing another customer's credit, under/over-payment and replay all fail structurally.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from urllib.parse import parse_qs, quote, urlparse

import cv2
import numpy as np

from .store import Store


def upi_link(vpa: str, name: str, amount: float, order_id: str) -> str:
    return (f"upi://pay?pa={quote(vpa)}&pn={quote(name)}&am={amount:.2f}&cu=INR&tn={quote(order_id)}"
            f"&tr={quote(order_id)}")


def create_order(store: Store, billed: float, vpa: str, name: str, now: datetime, unique_paise: bool = False,
                 ttl_min: int = 15):
    """unique_paise=True adds 1..99 paise so no two OPEN orders share an amount (optional; shopkeeper's choice)."""
    expected = round(billed, 2)
    if unique_paise:
        taken = {round(o["expected"], 2) for o in store.open_orders(now)}
        for tag in secrets.SystemRandom().sample(range(1, 100), 99):
            if round(billed + tag / 100, 2) not in taken:
                expected = round(billed + tag / 100, 2)
                break
        else:
            raise RuntimeError("no free paise tag")
    oid = "ORD" + secrets.token_hex(3).upper()
    store.add_order(oid, billed, expected, now, ttl_min)
    return {"order_id": oid, "expected": expected, "link": upi_link(vpa, name, expected, oid)}


def qr_png(link: str, scale: int = 8) -> bytes:
    qr = cv2.QRCodeEncoder.create().encode(link)
    big = cv2.resize(qr, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    big = cv2.copyMakeBorder(big, 4 * scale, 4 * scale, 4 * scale, 4 * scale, cv2.BORDER_CONSTANT, value=255)
    return cv2.imencode(".png", big)[1].tobytes()


def scan_qr(image_bytes: bytes) -> list[str]:
    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    det = cv2.QRCodeDetector()
    try:
        ok, vals, _, _ = det.detectAndDecodeMulti(arr)
        out = [v for v in (vals or []) if v] if ok else []
    except cv2.error:
        out = []
    if not out:
        v, _, _ = det.detectAndDecode(arr)
        out = [v] if v else []
    return out


def qr_guard(image_bytes: bytes, merchant_vpas: set[str]) -> dict:
    """Detects a swapped/pasted-over QR sticker: the QR's payee must be one of YOUR UPI IDs."""
    vp = {v.lower() for v in merchant_vpas}
    codes = scan_qr(image_bytes)
    if not codes:
        return {"found": False, "ok": False, "reason": "no QR code could be read; retake the photo closer"}
    for c in codes:
        u = urlparse(c)
        if u.scheme.lower() != "upi":
            return {"found": True, "ok": False, "reason": "QR is not a UPI payment code"}
        pa = (parse_qs(u.query).get("pa") or [""])[0].lower()
        if pa not in vp:
            return {"found": True, "ok": False, "vpa": pa, "reason": f"QR pays {pa or 'unknown'}, not your UPI ID - possible swapped sticker"}
    return {"found": True, "ok": True, "reason": "QR pays your UPI ID"}


def refund_check(store: Store, credit_id: int, requested_vpa: str) -> tuple[bool, str]:
    """Refund-scam guard ('I sent extra by mistake, please send back to this number/UPI')."""
    c = store.get_credit(credit_id)
    if not c:
        return False, "no such credit"
    if c["trust"] < 2:
        return False, "this credit is not verified from a trusted source; confirm in your bank app before refunding"
    if not c["payer"]:
        return False, "your bank alert does not show who paid; use your UPI app's own refund/return option"
    if c["payer"].lower() != requested_vpa.lower():
        return False, f"requested UPI ID differs from the payer ({c['payer']}); refund only to the original payer"
    return True, "refund target matches the original payer"
