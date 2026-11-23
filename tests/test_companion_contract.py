"""The Android app sends form fields exactly like these. This checks the SERVER LOGIC accepts that format end to end."""
import os, sys, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__))); sys.path.insert(0, os.path.dirname(__file__))
from make_samples import make_screen, to_jpeg
from paysure.engine import verify
from paysure.evidence import ingest_notification, ingest_sms
from paysure.store import Store

NOW = datetime(2026, 10, 27, 10, 40)
RECEIVED = (NOW - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")      # Uploader.isoLocal() format
SMS = "Rs 500.00 credited to A/c XX1234 by UPI Ref 412345678901. Avl Bal Rs 10500.00"


class Contract(unittest.TestCase):
    def test_sms_from_phone_makes_green(self):
        st = Store(":memory:")
        cid, flags = ingest_sms(st, SMS, "VM-HDFCBK-S", datetime.fromisoformat(RECEIVED), "device_sms", {"HDFCBK"})
        self.assertIsNotNone(cid)
        img = to_jpeg(make_screen("500", "412345678901", "27 Oct 2026, 10:38 AM"))
        self.assertEqual(verify(img, st, now=NOW, merchant_vpas={"shopkeeper@okbank"}).color, "green")

    def test_notification_from_phone(self):
        st = Store(":memory:")
        ingest_notification(st, "Received Rs 500.00 from rahul@okbank UPI Ref 412345678901",
                            "com.google.android.apps.nbu.paisa.user", datetime.fromisoformat(RECEIVED),
                            {"com.google.android.apps.nbu.paisa.user"})
        img = to_jpeg(make_screen("500", "412345678901", "27 Oct 2026, 10:38 AM"))
        self.assertEqual(verify(img, st, now=NOW, merchant_vpas={"shopkeeper@okbank"}).color, "green")

    def test_utc_server_would_have_broken_it(self):
        """Regression for the timezone bug: server clock 5.5h behind shop time must NOT be used."""
        st = Store(":memory:")
        img = to_jpeg(make_screen("500", "412345678901", "27 Oct 2026, 10:38 AM"))
        utc_now = NOW - timedelta(hours=5, minutes=30)
        self.assertEqual(verify(img, st, now=utc_now, merchant_vpas={"shopkeeper@okbank"}).color, "red")   # the bug
        self.assertEqual(verify(img, st, now=NOW, merchant_vpas={"shopkeeper@okbank"}).color, "yellow")     # app.py now_local()

    def test_non_credit_text_ignored(self):
        st = Store(":memory:")
        self.assertIsNone(ingest_sms(st, "Your OTP is 123456", "VM-HDFCBK-S", datetime.fromisoformat(RECEIVED), "device_sms", {"HDFCBK"})[0])


if __name__ == "__main__":
    unittest.main()
