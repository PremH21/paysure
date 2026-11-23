"""How accurate is the OCR + field parser on YOUR screenshots?
Make a CSV with the correct answers:  file,amount,utr,upi_id   (leave a cell empty to skip that field)
Usage: python train/check_ocr.py IMAGE_FOLDER answers.csv
Prints per-field accuracy and every miss, so you know which apps/themes the reader struggles with."""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402
from paysure.engine import ocr_text  # noqa: E402
from paysure.parsing import parse_screenshot_text  # noqa: E402


def compare(parsed, truth):
    res = {}
    if truth.get("amount"):
        res["amount"] = parsed.amount is not None and abs(parsed.amount - float(truth["amount"])) < 0.01
    if truth.get("utr"):
        res["utr"] = parsed.utr == truth["utr"].strip()
    if truth.get("upi_id"):
        res["upi_id"] = (parsed.upi_id or "") == truth["upi_id"].strip().lower()
    return res


def main(folder, csv_path):
    tot, ok = {}, {}
    for row in csv.DictReader(open(csv_path, encoding="utf-8")):
        path = os.path.join(folder, row["file"])
        parsed = parse_screenshot_text(ocr_text(Image.open(path).convert("RGB")))
        for field, good in compare(parsed, row).items():
            tot[field] = tot.get(field, 0) + 1; ok[field] = ok.get(field, 0) + int(good)
            if not good:
                print(f"MISS {row['file']:30s} {field}: expected {row[field]!r}, read {getattr(parsed, field)!r}")
    print()
    for f in tot:
        print(f"{f:8s} {ok[f]}/{tot[f]} = {ok[f] / tot[f]:.1%}")
    return ok, tot


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
