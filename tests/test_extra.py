import io
import os
import random
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from make_samples import make_screen, to_jpeg  # noqa: E402
from paysure.engine import verify  # noqa: E402
from paysure.evidence import ingest_notification, ingest_sms  # noqa: E402
from paysure.orders import create_order, qr_guard, qr_png, refund_check, upi_link  # noqa: E402
from paysure.store import Store  # noqa: E402

NOW = datetime(2026, 10, 26, 14, 40)
WHEN = "26 Oct 2026, 02:38 PM"
RECV = NOW - timedelta(minutes=1)
VPAS = {"shopkeeper@okbank"}
BANKS = {"HDFCBK"}


def sms(amount="500.00", utr="412345678901", payer=None):
    frm = f" from {payer}" if payer else ""
    return f"Rs {amount} credited to A/c XX1234{frm} by UPI Ref {utr}."


def run(img, st, **kw):
    return verify(img, st, now=NOW, merchant_vpas=VPAS, **kw)


class Orders(unittest.TestCase):
    def test_unique_paise_gives_distinct_amounts(self):
        st = Store(":memory:")
        a = create_order(st, 500, "shopkeeper@okbank", "Shop", NOW, unique_paise=True)
        b = create_order(st, 500, "shopkeeper@okbank", "Shop", NOW, unique_paise=True)
        self.assertNotEqual(a["expected"], b["expected"])
        self.assertIn("am=%.2f" % a["expected"], a["link"])

    def test_order_paid_once_then_replay_is_red(self):
        st = Store(":memory:")
        o = create_order(st, 500, "shopkeeper@okbank", "Shop", NOW, unique_paise=True)
        amt = f"{o['expected']:.2f}"
        ingest_sms(st, sms(amount=amt), "VM-HDFCBK-S", RECV, "device_sms", BANKS)
        img = to_jpeg(make_screen(amt, "412345678901", WHEN))
        v = run(img, st)
        self.assertEqual(v.color, "green", v.reason)
        self.assertIn(o["order_id"], v.reason)
        self.assertEqual(run(img, st).color, "red")

    def test_money_without_open_order_is_yellow(self):
        st = Store(":memory:")
        create_order(st, 500, "shopkeeper@okbank", "Shop", NOW)
        ingest_sms(st, sms(amount="300.00"), "VM-HDFCBK-S", RECV, "device_sms", BANKS)
        v = run(to_jpeg(make_screen("300", "412345678901", WHEN)), st)   # customer paid 300 for a 500 bill
        self.assertEqual(v.color, "yellow", v.reason)

    def test_expired_order_is_not_payable(self):
        st = Store(":memory:")
        create_order(st, 500, "shopkeeper@okbank", "Shop", NOW - timedelta(minutes=40), ttl_min=15)
        ingest_sms(st, sms(), "VM-HDFCBK-S", RECV, "device_sms", BANKS)
        self.assertEqual(run(to_jpeg(make_screen("500", "412345678901", WHEN)), st).color, "yellow")


class QR(unittest.TestCase):
    def test_own_qr_ok(self):
        png = qr_png(upi_link("shopkeeper@okbank", "Shop", 100, "ORD1"))
        self.assertTrue(qr_guard(png, VPAS)["ok"])

    def test_swapped_sticker_detected(self):
        png = qr_png(upi_link("scammer@okbank", "Shop", 100, "ORD1"))
        r = qr_guard(png, VPAS)
        self.assertFalse(r["ok"]); self.assertEqual(r["vpa"], "scammer@okbank")

    def test_non_upi_qr_rejected(self):
        png = qr_png("https://evil.example/pay")
        self.assertFalse(qr_guard(png, VPAS)["ok"])

    def test_no_qr(self):
        b = io.BytesIO(); Image.new("RGB", (300, 300), (200, 200, 200)).save(b, "PNG")
        self.assertFalse(qr_guard(b.getvalue(), VPAS)["found"])

    def test_degraded_photo_of_qr_still_reads(self):
        arr = cv2.imdecode(np.frombuffer(qr_png(upi_link("shopkeeper@okbank", "Shop", 100, "ORD1")), np.uint8), 1)
        arr = cv2.GaussianBlur(cv2.resize(arr, None, fx=0.6, fy=0.6), (3, 3), 0)
        ok, enc = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, 50])
        self.assertTrue(qr_guard(enc.tobytes(), VPAS)["ok"])


class Status(unittest.TestCase):
    def test_pending_shown_is_not_green_even_with_credit(self):
        st = Store(":memory:")
        ingest_sms(st, sms(), "VM-HDFCBK-S", RECV, "device_sms", BANKS)
        img = to_jpeg(make_screen("500", "412345678901", WHEN, status="Payment Pending"))
        self.assertEqual(run(img, st).color, "yellow")

    def test_failed_shown_never_green(self):
        st = Store(":memory:")
        img = to_jpeg(make_screen("500", "412345678901", WHEN, status="Payment Failed"))
        self.assertNotEqual(run(img, st).color, "green")


class Notification(unittest.TestCase):
    PK = {"com.google.android.apps.nbu.paisa.user"}

    def test_trusted_package_green(self):
        st = Store(":memory:")
        ingest_notification(st, sms(), "com.google.android.apps.nbu.paisa.user", RECV, self.PK)
        self.assertEqual(run(to_jpeg(make_screen("500", "412345678901", WHEN)), st).color, "green")

    def test_forged_notification_app_not_green(self):
        st = Store(":memory:")
        ingest_notification(st, sms(), "com.fake.notifier", RECV, self.PK)
        self.assertEqual(run(to_jpeg(make_screen("500", "412345678901", WHEN)), st).color, "yellow")

    def test_no_allowlist_means_unverified(self):
        st = Store(":memory:")
        ingest_notification(st, sms(), "anything", RECV, None)
        self.assertEqual(run(to_jpeg(make_screen("500", "412345678901", WHEN)), st).color, "yellow")


def make_rrn(dt, rnd):
    doy = dt.timetuple().tm_yday
    return f"{dt.year % 10}{doy:03d}{dt.hour:02d}{rnd.randrange(10**6):06d}"


class RRN(unittest.TestCase):
    def seed(self, st, structured):
        rnd = random.Random(5)
        for i in range(30):
            t = datetime(2026, 9, 1, 9) + timedelta(hours=7 * i + rnd.randrange(3), minutes=rnd.randrange(60))
            utr = make_rrn(t, rnd) if structured else "".join(rnd.choice("0123456789") for _ in range(12))
            ingest_sms(st, sms(utr=utr), "VM-HDFCBK-S", t, "device_sms", BANKS)

    def test_rule_turns_on_only_when_your_data_supports_it(self):
        a, b = Store(":memory:"), Store(":memory:")
        self.seed(a, True); self.seed(b, False)
        self.assertEqual(a.kv_get("rrn_rule"), "on")
        self.assertEqual(b.kv_get("rrn_rule"), "off")

    def test_impossible_reference_is_red_when_rule_on(self):
        st = Store(":memory:"); self.seed(st, True)
        img = to_jpeg(make_screen("500", "412345678901", WHEN))      # year digit 4 / day 123 / hour 45: impossible
        self.assertEqual(run(img, st).color, "red")

    def test_consistent_reference_not_red_when_rule_on(self):
        st = Store(":memory:"); self.seed(st, True)
        utr = make_rrn(datetime(2026, 10, 26, 14, 10), random.Random(1))
        self.assertEqual(run(to_jpeg(make_screen("500", utr, WHEN)), st).color, "yellow")

    def test_rule_off_does_not_flag(self):
        st = Store(":memory:"); self.seed(st, False)
        self.assertEqual(run(to_jpeg(make_screen("500", "412345678901", WHEN)), st).color, "yellow")


class Refund(unittest.TestCase):
    def test_refund_only_to_original_payer(self):
        st = Store(":memory:")
        cid, _ = ingest_sms(st, sms(payer="rahul@okbank"), "VM-HDFCBK-S", RECV, "device_sms", BANKS)
        self.assertTrue(refund_check(st, cid, "rahul@okbank")[0])
        self.assertFalse(refund_check(st, cid, "other@paytm")[0])

    def test_refund_blocked_for_unverified_credit(self):
        st = Store(":memory:")
        cid, _ = ingest_sms(st, sms(payer="rahul@okbank"), None, RECV, "pasted", None)
        self.assertFalse(refund_check(st, cid, "rahul@okbank")[0])


if __name__ == "__main__":
    unittest.main()
