"""Creates demo screenshots in ./demo/ for trying the app by hand.
 demo/good.jpg  - a payment screenshot for Rs 500 dated NOW (shop time)
 demo/edited.jpg - same screenshot with the amount edited from 50 to 500 (re-saved JPEG)
Usage: python tests/make_demo.py"""
import os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(__file__))
from make_samples import make_screen, tamper_amount, to_jpeg

now = datetime.now(ZoneInfo(os.environ.get("SHOP_TZ", "Asia/Kolkata"))).replace(tzinfo=None)
when = now.strftime("%d %b %Y, %I:%M %p")
os.makedirs("demo", exist_ok=True)
open("demo/good.jpg", "wb").write(to_jpeg(make_screen("500", "412345678901", when)))
open("demo/edited.jpg", "wb").write(tamper_amount(to_jpeg(make_screen("50", "412345678901", when)), "500"))
print("Wrote demo/good.jpg and demo/edited.jpg  (time on them:", when + ")")
print("Matching bank SMS text to send in step 6:")
print("Rs 500.00 credited to A/c XX1234 by UPI Ref 412345678901. Avl Bal Rs 10500.00")
print("received_at value:", now.strftime("%Y-%m-%dT%H:%M:%S"))
