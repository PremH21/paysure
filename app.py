"""FastAPI app. Run: uvicorn app:app --host 0.0.0.0 --port 7860
(Written for FastAPI's standard API; the engine behind it is covered by tests/test_core.py.
 Run tests/test_api.py after `pip install -r requirements.txt` to cover this file.)

Environment variables:
  PAYSURE_DB        sqlite path (default paysure.db)
  MERCHANT_VPAS     comma list of YOUR UPI IDs, e.g. shop@okbank
  BANK_HEADERS      comma list of your bank's SMS header codes, e.g. HDFCBK,SBIINB
  WEBHOOK_SECRET    gateway webhook secret (enables the strongest evidence tier)
  DEVICE_KEY        shared key your Android companion app sends in X-Device-Key
  SHIELD_KEY        shared key for shop-to-shop sync
  APP_KEY           password for the web page / merchant endpoints (REQUIRED on a public host)
  SHOP_ID           name this shop reports under
  SHOP_TZ           shop timezone (default Asia/Kolkata)
  TRUSTED_PACKAGES  comma list of app package names allowed to raise credit notifications
"""
import base64
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from paysure.engine import verify
from paysure.evidence import ingest_notification, ingest_sms, ingest_webhook
from paysure.orders import create_order, qr_guard, qr_png, refund_check
from paysure.store import Store

SHOP_TZ = ZoneInfo(os.environ.get("SHOP_TZ", "Asia/Kolkata"))


def now_local() -> datetime:
    """Shop-local naive time. Screenshots and SMS carry the shop's local time; a cloud server runs in UTC,
    which would make every real screenshot look 5.5 hours in the future."""
    return datetime.now(SHOP_TZ).replace(tzinfo=None)


app = FastAPI(title="PaySure")
store = Store(os.environ.get("PAYSURE_DB", "paysure.db"))
VPAS = {v.strip() for v in os.environ.get("MERCHANT_VPAS", "").split(",") if v.strip()} or None
BANKS = {v.strip() for v in os.environ.get("BANK_HEADERS", "").split(",") if v.strip()} or None
SHOP = os.environ.get("SHOP_ID", "shop-1")
stats = {"checked": 0, "red": 0, "rupees_saved": 0.0}

from paysure.model import load as load_model
MODEL_WRAPPED = load_model()
if MODEL_WRAPPED is None:
    print("WARNING: models/forgery.joblib could not be loaded (scikit-learn version mismatch?). Using the simple fallback; "
          "retrain with train/train.py to restore the classifier.")
if not os.environ.get("APP_KEY"):
    print("WARNING: APP_KEY is not set - fine on your own laptop, NOT fine on a public host.")


def _app(x_app_key: str):
    """Merchant-facing endpoints. If APP_KEY is set (do this on any public host) the header must match."""
    k = os.environ.get("APP_KEY")
    if k and x_app_key != k:
        raise HTTPException(401, "bad or missing app key")


def _need(key_env, provided):
    k = os.environ.get(key_env)
    if not k or provided != k:
        raise HTTPException(401, "bad or missing key")


@app.post("/verify")
async def verify_endpoint(image: UploadFile = File(...), pasted_sms: str = Form(""), lang: str = Form("en"),
                          x_app_key: str = Header("")):
    _app(x_app_key)
    data = await image.read()
    v = verify(data, store, now=now_local(), lang=lang, pasted_sms=pasted_sms or None, merchant_vpas=VPAS, model=MODEL_WRAPPED)
    stats["checked"] += 1
    f = v.signals["fields"]
    if v.color == "red":
        stats["red"] += 1
        stats["rupees_saved"] += f.amount or 0
    buf = io.BytesIO(); v.heatmap.save(buf, "PNG")
    return {
        "check_id": v.check_id, "verdict": v.color, "reason": v.reason, "message": v.messages[v.color],
        "risk": round(v.risk, 3),
        "fields": {"amount": f.amount, "utr": f.utr, "upi_id": f.upi_id, "time": f.when.isoformat() if f.when else None},
        "heatmap_png_base64": base64.b64encode(buf.getvalue()).decode(),
    }


@app.post("/credit/sms")
async def credit_sms(sender: str = Form(...), text: str = Form(...), received_at: str = Form(...),
                     source: str = Form("device_sms"), x_device_key: str = Header("")):
    """Called by the Android companion (reads SMS / notification on the merchant's own phone)."""
    _need("DEVICE_KEY", x_device_key)
    cid, flags = ingest_sms(store, text, sender, datetime.fromisoformat(received_at), "device_sms", BANKS)
    return {"credit_id": cid, "flags": flags}


@app.post("/credit/notification")
async def credit_notification(package: str = Form(...), text: str = Form(...), received_at: str = Form(...),
                              x_device_key: str = Header("")):
    _need("DEVICE_KEY", x_device_key)
    pk = {v.strip() for v in os.environ.get("TRUSTED_PACKAGES", "").split(",") if v.strip()} or None
    cid, flags = ingest_notification(store, text, package, datetime.fromisoformat(received_at), pk)
    return {"credit_id": cid, "flags": flags}


@app.post("/orders")
def new_order(amount: float = Form(...), unique_paise: int = Form(0), x_app_key: str = Header("")):
    _app(x_app_key)
    """Create a bill with a UPI link + QR bound to it. Only a payment matching an open order can turn green."""
    vpa = sorted(VPAS)[0] if VPAS else None
    if not vpa:
        raise HTTPException(400, "set MERCHANT_VPAS first")
    o = create_order(store, amount, vpa, os.environ.get("SHOP_NAME", "Shop"), now_local(), bool(unique_paise))
    o["qr_png_base64"] = base64.b64encode(qr_png(o["link"])).decode()
    return o


@app.post("/qr/check")
async def qr_check(image: UploadFile = File(...), x_app_key: str = Header("")):
    _app(x_app_key)
    """Photograph your displayed QR sticker: detects a swapped/pasted-over QR that pays someone else."""
    return qr_guard(await image.read(), VPAS or set())


@app.post("/refund/check")
def refund(credit_id: int = Form(...), requested_vpa: str = Form(...), x_app_key: str = Header("")):
    _app(x_app_key)
    ok, reason = refund_check(store, credit_id, requested_vpa)
    return {"ok": ok, "reason": reason}


@app.post("/credit/webhook")
async def credit_webhook(request: Request, x_signature: str = Header("")):
    """Payment-gateway webhook (e.g. Razorpay-style). Body JSON: {"amount": 500.0, "utr": "..."}; HMAC-SHA256 signed."""
    import json
    body = await request.body()
    j = json.loads(body)
    cid = ingest_webhook(store, body, x_signature, os.environ.get("WEBHOOK_SECRET", ""), float(j["amount"]),
                         str(j["utr"]), now_local())
    if cid is None:
        raise HTTPException(401, "bad signature")
    return {"credit_id": cid}


@app.post("/feedback")
def feedback(check_id: int = Form(...), is_fake: int = Form(...), utr: str = Form(""), x_app_key: str = Header("")):
    _app(x_app_key)
    """Merchant confirms the outcome (checked bank app). Becomes a training label; confirmed fakes feed the shield."""
    store.set_label(check_id, int(is_fake))
    if is_fake and utr:
        store.report_fake(utr, reporter=SHOP)
    return {"ok": True}


@app.get("/shield/pull")
def shield_pull(since: float = 0.0, x_shield_key: str = Header("")):
    _need("SHIELD_KEY", x_shield_key)
    return store.export_fakes(since)


@app.post("/shield/push")
async def shield_push(request: Request, x_shield_key: str = Header("")):
    _need("SHIELD_KEY", x_shield_key)
    store.import_fakes(await request.json())
    return {"ok": True}


@app.get("/stats")
def get_stats(x_app_key: str = Header("")):
    _app(x_app_key)
    return stats


@app.get("/", response_class=HTMLResponse)
def home():
    return open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8").read()
