import os, sys, unittest, hmac, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime
from paysure.evidence import ingest_webhook, verify_webhook
from paysure.store import Store


class Sec(unittest.TestCase):
    def test_empty_secret_never_validates(self):
        body = b"{}"
        forged = hmac.new(b"", body, hashlib.sha256).hexdigest()       # what an attacker would compute
        self.assertFalse(verify_webhook(body, forged, ""))
        self.assertIsNone(ingest_webhook(Store(":memory:"), body, forged, "", 500.0, "412345678901", datetime.now()))


if __name__ == "__main__":
    unittest.main()
