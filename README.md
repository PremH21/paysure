---
title: PaySure
emoji: 🛡️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# PaySure - payment-proof verifier for small merchants

Principle: **a screenshot is a claim; only money in YOUR account is proof.** GREEN is fail-closed: it needs a trusted credit
(tier>=2) matching exact reference number, amount and time, unclaimed, paid to your UPI ID, status not pending/failed,
and (in orders mode) matching one open bill. Image forensics never creates green; it only separates yellow from red when
no credit exists.

## Evidence tiers
3 signed gateway webhook | 2 SMS read on your phone from your bank's header, or notification from an allow-listed app | 1 pasted text (never green)

## Attacks covered (59 tests in tests/)
| Attack | Defence | Outcome |
|---|---|---|
| Edited screenshot | exact-reference credit match | never green; red if credit differs |
| Fake payment app / fabricated reference | no credit with that reference | never green |
| "Pending"/"Failed"/"Reversed" shown as success | status classifier | never green |
| Old screenshot replay | one-credit-one-claim, seen references | red |
| Borrowing another customer's real credit | exact reference required | not green |
| One digit of reference off (OCR slip or forgery) | near-miss rule | yellow, compare by eye |
| Fake / spoofed SMS (wrong header, broken balance, pasted) | header allowlist, balance continuity, tiers | yellow |
| Fake notification app | notification package allowlist | yellow |
| Forged gateway webhook | HMAC-SHA256 | rejected |
| Paid someone else's UPI ID | payee check | red |
| Under / over / wrong-amount payment | orders mode: must match an open bill | yellow |
| Replay of a paid bill | order closed on payment | red |
| Swapped / pasted-over QR sticker | QR guard: payee in QR must be yours | alert |
| "Sent extra by mistake, refund me elsewhere" | refund guard: only to original payer, only if verified | blocked |
| Impossible reference number | self-calibrating RRN check (turns on only if YOUR trusted credits follow the pattern) | red |
| One shop poisons shared fake list | needs reports from >=2 shops; only salted hashes of references shared | no effect alone |

## Beyond screenshots - what makes it different
- Order binding + UPI link/QR per bill (optional unique paise) - payments must match one open bill.
- QR guard against sticker-swap fraud (the shop's own risk, not the customer's).
- Refund-scam guard. Self-calibrating reference check. Voice verdict in EN/HI/KN.
- Self-labelling retrain with champion-vs-challenger and drift alert (paysure/retrain.py).
- Works with the evidence you already have; stronger evidence unlocks green.

## Image forensics: what was tried and what is honestly achieved (synthetic data, NOT real-world numbers)
Policy: forensics alone can never make GREEN. A looser threshold (<=2% false alarms) only WARNS ("possible signs of editing");
a strict one (<=1%) may say RED. Thresholds come from out-of-fold predictions over ~400 genuine images (a single small validation
split gave unreliable thresholds: it promised 1% false alarms but showed 11% on held-out direct screenshots - found and fixed).

| group (held-out) | RED | WARN+RED |
|---|---|---|
| genuine direct / forwarded (want low) | 0.0% / 0.0% | 4.4% / 1.1% |
| edit, other font / same font | 34% / 36% | 54% / 59% |
| region paste | 32% | 59% |
| edit then screenshot | 68% | 87% |
| NEVER-TRAINED: digit clone / blur-retype | 20% / 16% | 31% / 27% |

Tried and rejected (no gain, kept in train/experiments/): JPEG grid-alignment features; per-word and per-tile consistency
features; a one-class anomaly detector trained on genuine images only. Why: the file's own JPEG quality is recoverable exactly,
but global recompression error mostly measures text contrast, not edits; and my synthetic edits are re-saved JPEGs, while real
forgeries usually start from PNG screenshots, so JPEG double-compression traces in this data probably OVERSTATE what real data gives.
What genuinely works against hidden edits is not more pixel statistics but (1) proof of money (credit match), (2) per-app
template/layout checks (needs real screenshots), (3) asking for the original share / live screen when an image looks re-photographed.
Latency: median ~0.35 s end to end on a 2-core sandbox.

## Residual risks (no software removes these)
1. Spoofed SMS with real header + consistent balance if you rely on SMS alone -> use gateway webhook or confirm large amounts in bank app.
2. Forensics is weak on laundered edits -> that is why it never decides green.
3. Reversals/chargebacks after green are invisible to a screenshot check.
4. Android companion source is in android/ but was NEVER compiled or run (no SDK in my environment). Without it green is unreachable by design.
5. The RRN structure hypothesis is unverified; the rule stays off unless your data supports it.
6. Real accuracy needs your own consented screenshots.

## Deployment note (bug fixed)
Cloud servers run in UTC; screenshots carry shop-local time. app.py now uses SHOP_TZ (default Asia/Kolkata). Without this every real
screenshot looked 5.5 hours in the future and went RED (regression test in tests/test_companion_contract.py).

## Start here
Open GUIDE.md: accounts, tokens, build, deploy, collecting real data and training, in order.

## Run
    pip install -r requirements.txt     # + system package tesseract-ocr
    for t in test_core test_extra test_retrain test_policy test_companion_contract test_security test_dataset_tools; do python tests/$t.py; done
    python train/gen_data.py 300 data/manifest.json && python train/build_features.py data/manifest.json data/feat.json && python train/train.py data/feat.json   # ~10 min on 2 cores
    MERCHANT_VPAS=shop@okbank BANK_HEADERS=HDFCBK TRUSTED_PACKAGES=com.google.android.apps.nbu.paisa.user DEVICE_KEY=x SHIELD_KEY=y uvicorn app:app --port 7860
(Verify notification package names on your own phone.)

## Deploy free: Hugging Face Space (Docker SDK); push this folder. Free tier sleeps; disk not persistent. Use a free Postgres for shared data later.

## Next
0. Build/run android/ (see android/README.md) and fix any build errors.
1. Real consented dataset per UPI app -> retrain -> report real precision/recall/F1/false-alarm per tamper type.
2. Android companion app. 3. Gateway dynamic-QR + webhook. 4. Layout template matching + Grad-CAM. 5. Shared Postgres + scheduled retraining.
