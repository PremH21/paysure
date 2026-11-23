import hashlib
import hmac
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image  # noqa: E402
import io  # noqa: E402
from make_samples import make_screen, tamper_amount, to_jpeg  # noqa: E402
from paysure.engine import verify  # noqa: E402
from paysure.evidence import ingest_sms, ingest_webhook, verify_webhook  # noqa: E402
from paysure.parsing import parse_credit_sms, parse_screenshot_text  # noqa: E402
from paysure.store import Store  # noqa: E402

NOW = datetime(2026, 10, 26, 14, 40)
WHEN = "26 Oct 2026, 02:38 PM"
VPAS = {"shopkeeper@okbank"}
BANKS = {"HDFCBK"}
RECV = NOW - timedelta(minutes=1)


def sms(amount="500.00", utr="412345678901", bal="10500.00"):
    return f"Rs {amount} credited to A/c XX1234 on 26-10-26 by UPI Ref {utr}. Avl Bal Rs {bal}"


def shot(amount="500", utr="412345678901", when=WHEN, upi="shopkeeper@okbank"):
    return to_jpeg(make_screen(amount, utr, when, upi=upi))


def run(img, st, **kw):
    return verify(img, st, now=NOW, merchant_vpas=VPAS, **kw)


class Parsing(unittest.TestCase):
    def test_sms_parser(self):
        f = parse_credit_sms(sms(), NOW)
        self.assertEqual((f.amount, f.utr), (500.0, "412345678901"))

    def test_ocr_text_parser(self):
        f = parse_screenshot_text("Rs 1,250.50\n26 Oct 2026, 02:38 PM\nUPI Ref No: 412345678901\nPayment Successful")
        self.assertEqual((f.amount, f.utr, f.status_ok), (1250.5, "412345678901", True))


class Attacks(unittest.TestCase):
    def setUp(self):
        self.st = Store(":memory:")

    def device_credit(self, **kw):
        return ingest_sms(self.st, sms(**kw), "VM-HDFCBK-S", RECV, "device_sms", BANKS)

    def test_green_with_trusted_device_sms(self):
        self.device_credit()
        v = run(shot(), self.st)
        self.assertEqual(v.color, "green", v.reason)

    def test_pasted_sms_never_green(self):
        v = run(shot(), self.st, pasted_sms=sms())
        self.assertEqual(v.color, "yellow", v.reason)

    def test_spoofed_sms_unknown_header_not_green(self):
        ingest_sms(self.st, sms(), "VM-FAKEBK-S", RECV, "device_sms", BANKS)
        self.assertEqual(run(shot(), self.st).color, "yellow")

    def test_spoofed_sms_with_real_header_but_broken_balance_not_green(self):
        self.device_credit(utr="111111111111", amount="100.00", bal="5100.00")   # real one sets baseline 5100
        ingest_sms(self.st, sms(), "VM-HDFCBK-S", RECV, "device_sms", BANKS)      # claims bal 10500 (should be 5600)
        self.assertEqual(run(shot(), self.st).color, "yellow")

    def test_borrowing_someone_elses_real_credit_not_green(self):
        self.device_credit(utr="412345678901")          # customer A really paid 500
        v = run(shot(utr="999988887777"), self.st)       # customer B shows a 500 screenshot with another reference
        self.assertNotEqual(v.color, "green", v.reason)

    def test_one_digit_off_reference_is_yellow_not_green(self):
        self.device_credit(utr="412345678901")
        v = run(shot(utr="412345678902"), self.st)
        self.assertEqual(v.color, "yellow", v.reason)

    def test_edited_amount_same_reference_is_red(self):
        self.device_credit(amount="50.00", utr="412345678901", bal="10050.00")
        img = tamper_amount(to_jpeg(make_screen("50", "412345678901", WHEN)), "500")
        self.assertEqual(run(img, self.st).color, "red")

    def test_one_credit_cannot_back_two_screenshots(self):
        self.device_credit()
        self.assertEqual(run(shot(), self.st).color, "green")
        self.assertEqual(run(shot(), self.st).color, "red")

    def test_paid_to_other_upi_id_is_red(self):
        self.device_credit()
        self.assertEqual(run(shot(upi="someoneelse@okbank"), self.st).color, "red")

    def test_future_timestamp_is_red(self):
        self.assertEqual(run(shot(when="26 Oct 2026, 11:59 PM"), self.st).color, "red")

    def test_stale_credit_time_mismatch_not_green(self):
        ingest_sms(self.st, sms(), "VM-HDFCBK-S", NOW - timedelta(hours=1), "device_sms", BANKS)
        self.assertNotEqual(run(shot(), self.st).color, "green")

    def test_no_credit_clean_image_is_yellow(self):
        self.assertEqual(run(shot(), self.st).color, "yellow")


class Webhook(unittest.TestCase):
    def test_signature(self):
        body, secret = b'{"amount":500}', "s3cret"
        good = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook(body, good, secret))
        self.assertFalse(verify_webhook(body, "00" * 32, secret))
        self.assertFalse(verify_webhook(body + b" ", good, secret))

    def test_webhook_credit_gives_green(self):
        st, body, secret = Store(":memory:"), b"evt", "k"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertIsNotNone(ingest_webhook(st, body, sig, secret, 500.0, "412345678901", RECV))
        self.assertEqual(run(shot(), st).color, "green")
        self.assertIsNone(ingest_webhook(st, body, "bad", secret, 500.0, "412345678901", RECV))


class Shield(unittest.TestCase):
    def test_single_reporter_cannot_poison_but_two_can(self):
        st = Store(":memory:")
        img = shot(utr="555566667777")
        st.report_fake(utr="555566667777", reporter="shopA")
        self.assertNotEqual(run(img, st).color, "red")           # one report only: not enough
        st.report_fake(utr="555566667777", reporter="shopB")
        self.assertEqual(run(img, st).color, "red")              # two independent shops

    def test_same_shop_twice_counts_once(self):
        st = Store(":memory:")
        st.report_fake(utr="555566667777", reporter="shopA"); st.report_fake(utr="555566667777", reporter="shopA")
        self.assertEqual(st.reporters_for_ref("555566667777"), 1)

    def test_export_import_between_shops(self):
        a, b = Store(":memory:"), Store(":memory:")
        a.report_fake(utr="555566667777", reporter="shopA")
        b.import_fakes(a.export_fakes())
        self.assertEqual(b.reporters_for_ref("555566667777"), 1)

    def test_no_raw_reference_or_image_leaves_shop(self):
        a = Store(":memory:"); a.report_fake(utr="555566667777", reporter="x")
        blob = str(a.export_fakes())
        self.assertNotIn("555566667777", blob)

    def test_other_genuine_payment_unaffected_by_reports(self):
        st = Store(":memory:")
        for shop in ("shopA", "shopB"):
            st.report_fake(utr="111122223333", reporter=shop)
        ingest_sms(st, sms(utr="444455556666"), "VM-HDFCBK-S", RECV, "device_sms", BANKS)
        self.assertEqual(run(shot(utr="444455556666"), st).color, "green")


if __name__ == "__main__":
    unittest.main()
