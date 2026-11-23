# PaySure - complete guide, from nothing to deployed, then training on real data

**Honest status before you start**
- Verified in my environment: the engine, trained-model loading, dataset tools, and 59 tests (all pass).
- NOT verified (I had no access to install FastAPI or the Android SDK): the web server `app.py` has never been *run*, and the
  Android app has never been *compiled*. Part 4 is where you find out if the server works. If anything errors, paste the
  error text to me and I will fix it.
- The model shipped in `models/forgery.joblib` was trained on SYNTHETIC images. Part 9-10 replace it with one trained on real data.
- Only ever create fake payment screenshots from YOUR OWN test payments, for testing the detector. Never use a forged proof on a real merchant.

Menu names on websites change slightly over time; if a button is not where I say, look for the closest name.

---------------------------------------------------------------------------------------------------
## PART 1 - Accounts and tools you need (all free)

| What | Website | Why | Needed when |
|---|---|---|---|
| GitHub account | https://github.com/signup | keep your code, submit your project | Part 6 |
| Hugging Face account | https://huggingface.co/join | free hosting for the server (a "Space") + optional datasets | Part 7 |
| Python 3.11+ | https://www.python.org/downloads/ (Windows: tick "Add python.exe to PATH") | run everything | Part 2 |
| Tesseract OCR | Windows: https://github.com/UB-Mannheim/tesseract/wiki  / Linux: `sudo apt install tesseract-ocr` / Mac: `brew install tesseract` | reads text from screenshots | Part 2 |
| Git | https://git-scm.com/downloads | upload code | Part 6 |
| Android Studio | https://developer.android.com/studio | build the phone companion app | Part 8 |

You do NOT need: a Razorpay account, Kaggle, any paid service. (The server has a signed-webhook route for payment gateways, but it
expects a simple JSON body; it is NOT yet an adapter for Razorpay's real payload format. Skip it for now.)

---------------------------------------------------------------------------------------------------
## PART 2 - Get the code and run the tests on your laptop
**MacBook (Apple Silicon) quick path, all in Terminal** (verified to work up to the pip install on a real MacBook):
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"   # only if `brew --version` fails
brew install python@3.12 tesseract git gh
cd ~/paysure && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```
No Tesseract path setting is needed on a Mac. To unzip a download whose name you are unsure of: type `unzip -o ` then drag the zip
from Finder into the Terminal window, then type ` -d ~/` and press Enter. A prompt that starts with `(.venv)` means the project's
environment is active; `deactivate` leaves it.
(Windows steps follow.)


1. Unzip `paysure.zip`. Open a terminal INSIDE the `paysure` folder (Windows: right-click the folder > "Open in Terminal").
2. Create an isolated Python environment and install:
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
   Linux/Mac: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
   - PowerShell says scripts are disabled? Run `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.
   - `scikit-learn==1.9.1` cannot be installed? Run `pip install scikit-learn joblib`, then retrain later (Part 10) because the shipped
     model was saved with 1.9.1.
3. Windows only, if you later see "tesseract is not installed or it's not in your PATH":
```
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```
4. Run all tests (each must end with `OK`):
```
python tests/test_core.py
python tests/test_extra.py
python tests/test_policy.py
python tests/test_companion_contract.py
python tests/test_security.py
python tests/test_retrain.py
python tests/test_dataset_tools.py
```
   If a test fails, copy the whole output and send it to me.

---------------------------------------------------------------------------------------------------
## PART 3 - Create your secret keys (do this once; keep them private)

The server uses long random passwords. Generate three (run the command three times, save each output in a notes file):
```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
- `APP_KEY`    : password for the web page / merchant actions
- `DEVICE_KEY`: password the Android app uses to send bank alerts
- `SHIELD_KEY`: only if you later connect several shops

Never paste them in code, in GitHub, or in chat.

---------------------------------------------------------------------------------------------------
## PART 4 - Run the server locally and see GREEN / YELLOW / RED

1. Set the settings (Windows PowerShell; Linux/Mac use `export NAME="value"`):
```
$env:MERCHANT_VPAS="shopkeeper@okbank"
$env:BANK_HEADERS="HDFCBK"
$env:DEVICE_KEY="test-device-key-123"
$env:APP_KEY="test-app-key-123"
uvicorn app:app --port 7860
```
   (Use the simple test keys while testing locally; use the real generated ones online.)
   `MERCHANT_VPAS` = your UPI ID(s), comma-separated. `BANK_HEADERS` = the code in your bank's SMS sender, e.g. a sender
   `VM-HDFCBK-S` -> `HDFCBK`.
2. Open http://localhost:7860 .  Second terminal, same folder, venv active:
```
python tests/make_demo.py
```
   It creates `demo/good.jpg`, `demo/edited.jpg` and prints a bank SMS text plus a `received_at` value.
3. YELLOW: in the page type the app key `test-app-key-123`, pick `demo/good.jpg`, press Check -> yellow (no bank alert yet).
4. GREEN: simulate the phone sending the bank SMS (Windows: use `curl.exe`, not `curl`):
```
curl.exe -X POST http://localhost:7860/credit/sms -H "X-Device-Key: test-device-key-123" --data-urlencode "sender=VM-HDFCBK-S" --data-urlencode "text=Rs 500.00 credited to A/c XX1234 by UPI Ref 412345678901. Avl Bal Rs 10500.00" --data-urlencode "received_at=PASTE_received_at_FROM_make_demo"
```
   Check `demo/good.jpg` again -> GREEN. A third time -> RED ("already used").
5. RED for an edit: stop the server (Ctrl+C), delete `paysure.db`, start again, send the SMS for **Rs 50** with the SAME reference number
   (`text=Rs 50.00 credited to A/c XX1234 by UPI Ref 412345678901. Avl Bal Rs 10050.00`), then check `demo/edited.jpg` -> RED.

If the server will not start or a page errors, paste the red error text to me.

---------------------------------------------------------------------------------------------------
## PART 5 - Understand the three evidence rules (for your viva)
- A screenshot is only a claim. GREEN needs trusted proof of money: a bank alert read from the shop's own phone (sender header must be
  your bank's), matching exact reference number + amount + time, not already used, paid to your UPI ID, status "success".
- Image analysis can only WARN or say RED; it can never say GREEN.
- Pasted SMS text can never give GREEN (anyone can type it).

---------------------------------------------------------------------------------------------------
## PART 6 - Put the code on GitHub (your project submission)
1. https://github.com/new -> repository name `paysure` -> Private (you can make it public later) -> Create repository. Do NOT tick "Add a README".
2. In the paysure folder terminal (the `.gitignore` already blocks your private data, virtual-env and database):
```
git init
git add .
git commit -m "PaySure first version"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/paysure.git
git push -u origin main
```
3. A browser window (Git Credential Manager) asks you to sign in to GitHub: approve it. If it asks for a password instead, GitHub no longer
   accepts your account password; create a token: GitHub -> your profile picture -> Settings -> Developer settings -> Personal access tokens
   -> Tokens (classic) -> Generate new token -> tick `repo` -> Generate -> copy it (shown once) and paste it as the password.
4. Check `git status` and the GitHub page: the folders `data/raw` and files `.db` must NOT appear.

---------------------------------------------------------------------------------------------------
## PART 7 - Deploy the server free on Hugging Face Spaces
1. Sign up at https://huggingface.co/join and verify your email.
2. **Create an access token** (needed to upload code): click your profile picture -> Settings -> Access Tokens -> Create new token ->
   type **Write** -> name it `paysure-upload` -> Create -> copy it now (shown once).
3. **Create the Space**: https://huggingface.co/new-space -> Space name `paysure` -> SDK **Docker** -> template **Blank** -> hardware
   **CPU basic (free)** -> visibility **Public** -> Create Space.
   Public is required: the phone app has to reach it. Your data stays safe because every action needs `APP_KEY` / `DEVICE_KEY`
   and the code never contains secrets. Do not put real customer data or keys in the files you upload.
4. **Add settings**: in the Space -> Settings -> "Variables and secrets":
   - New **secret**: `APP_KEY` (your generated value), `DEVICE_KEY` (your generated value). Optional: `SHIELD_KEY`.
   - New **variable**: `MERCHANT_VPAS` (e.g. `shop@okbank`), `BANK_HEADERS` (e.g. `HDFCBK`), `SHOP_TZ` = `Asia/Kolkata`,
     `SHOP_NAME`, and optional `TRUSTED_PACKAGES` (payment-app package names for notifications), `TIME_TOLERANCE_MIN` (Part 12).
5. **Upload the code** (from your paysure folder terminal):
```
git remote add space https://huggingface.co/spaces/YOUR_HF_USERNAME/paysure
git push space main
```
   Username = your Hugging Face username; password = the **Write token** from step 2. (If git complains the remote has a different history,
   use `git push space main --force` - only for this first upload of an empty Space.)
   No git? In the Space page -> Files -> Add file -> Upload files: drag in the CONTENTS of the paysure folder (not the zip, and not `.venv` or `data`).
6. The Space shows "Building" (5-10 min) then "Running". Open `https://YOUR_HF_USERNAME-paysure.hf.space`. If it fails, open the **Logs** tab
   and send me the last 30 lines.
7. Behaviour of the free tier: it sleeps when idle (first request can take ~30 s) and its disk is erased on restart, so the bank-alert
   ledger and used-reference list reset. That is fine for a demo and viva; real shops need a free Postgres (Neon/Supabase) next.

---------------------------------------------------------------------------------------------------
## PART 8 - Android companion app (makes GREEN work with a real phone)
Read `android/README.md` too. It was written without being compiled, so expect to fix a small build error (paste it to me).
1. Install Android Studio (https://developer.android.com/studio). File -> Open -> choose the `android` folder -> let it download the SDK
   and sync (10-20 min first time). Accept "upgrade Gradle/plugin" suggestions.
2. Phone: Settings -> About phone -> tap "Build number" 7 times -> Settings -> Developer options -> turn on USB debugging. Connect by USB, allow the prompt.
3. Press the green Run button in Android Studio; the app installs on the phone.
4. In the app: Server URL = `https://YOUR_HF_USERNAME-paysure.hf.space`, Device key = your `DEVICE_KEY` -> Save -> "Allow reading SMS" ->
   "Allow notification access".
5. On newer Android versions, apps installed outside the Play Store are "restricted": if the SMS/notification switch is greyed out, open
   Settings -> Apps -> PaySure Companion -> top-right menu (three dots) -> "Allow restricted settings", then try again.
6. Send yourself a test bank credit (or use your bank's real credit SMS). The app should show "Waiting to upload: 0".

---------------------------------------------------------------------------------------------------
## PART 9 - Collect REAL data (the most valuable thing you can do)
Rules: use your own accounts or people who agree; send tiny amounts (Rs 1-10) between your own test accounts. Your own test payments
contain nothing sensitive, so you do NOT need to edit or hide anything. Do NOT crop, blur or mask training images: editing pixels
destroys the very signal the detector learns. (Mask details only on copies you show in your report.)

Create these folders under `data/raw/` and put images in them (any file names; sub-folders are fine):

| Folder (the NAME sets the label) | What goes in | Target |
|---|---|---|
| `genuine_gpay_original` | the success screen of a real payment: Android screenshot (PNG) | 150+ |
| `genuine_gpay_whatsapp` | the same kind of screenshot after sending it to yourself on WhatsApp and saving the received copy | 150+ |
| `genuine_phonepe_original`, `genuine_phonepe_whatsapp`, `genuine_paytm_...` | same for each app you want to support; mix light/dark theme, phones, font sizes | 100+ each |
| `fake_photopea_amount` | take a genuine screenshot, open it free in https://www.photopea.com, change the amount/time/name with the text tool, export as JPG (try qualities 70-95) and PNG | 150+ |
| `fake_paste_region` | paste a region (amount, status) from a different screenshot | 100+ |
| `fake_clone_digits` | copy digits from elsewhere in the same image | 100+ |
| `fake_phone_editor` | edit with a phone photo-editor app | 100+ |
| `novel_fake_screenshot_of_edit` | show an edited image on another screen and take a screenshot/photo of it | 50+ |
| `novel_genuine_<an app or phone you hold out>` and `novel_fake_...` for it | one whole app or phone kept out of training, to test on something unseen | 50+ |

Naming rules the tool enforces: the folder name must contain `genuine`, or `fake`/`tamper`/`forged`. Prefix `novel_` = never trained on
(honest test of new attacks/apps). Prefix `aux_` = extra other-domain data (Part 10b). Every normal folder needs at least 10 images.

Tips that make your results honest:
- Ask a friend to make some of the fakes without telling you how, so your detector is not tested only on your own style.
- Keep a sheet of the true values for each screenshot (amount, reference number, UPI ID) - used in Part 12.

---------------------------------------------------------------------------------------------------
## PART 10 - Train on your real data and replace the model
```
python train/make_manifest.py data/raw data/manifest.json
python train/build_features.py data/manifest.json data/feat.json
python train/train.py data/feat.json
```
(`make_manifest` checks names, drops duplicates, and stops if the same image is labelled both genuine and fake. `build_features` takes a few
minutes for hundreds of images. `train` prints the results table.)

How to read the table: rows marked "genuine: want LOW" must have small RED/WARN numbers (false alarms); rows marked "fake: want HIGH" are
detection rates; `[NEVER TRAINED]` rows are your honest test on unseen attacks/apps. If it prints `*** CAUTION ***` you have too few images:
do not quote those numbers.

Use the new model: it is saved as `models/forgery.joblib`. Put your scikit-learn version in the requirements before deploying:
```
pip show scikit-learn
```
edit `requirements.txt` so the line reads `scikit-learn==<the version shown>`, then:
```
git add models/forgery.joblib requirements.txt
git commit -m "Model trained on real data"
git push origin main
git push space main
```
### 10b - Optional: extra public data (AIForge-Doc: forged receipts/forms, NOT phone screens)
1. On https://huggingface.co/datasets/Scam-AI/AIForge-Doc-v1 (logged in) fill the short access form - access is granted automatically. It is ~10 GB.
2. Create a Read token (Settings -> Access Tokens -> Create new token -> Read), then:
```
pip install -U huggingface_hub
hf auth login
hf download Scam-AI/AIForge-Doc-v1 --repo-type dataset --local-dir data/aiforge
python train/import_aiforge.py data/aiforge --forged-only --max 600
python train/make_manifest.py data/raw data/manifest.json --add data/manifest_aiforge.json
```
   `hf auth login` asks you to paste the token. I could not test the importer on the real files (gated, large), only on a mock layout.
   `train.py` compares results with and without this data and DROPS it if it does not help on your real test images.
   Check the dataset's licence on its page before using it (the info file you sent says CC BY 4.0; the page text I read said CC BY-NC-SA 4.0).
   The CORD zip you sent contains only the README and one sample image, not data; you do not need it.

---------------------------------------------------------------------------------------------------
## PART 11 - Check the bank-SMS reader on your own banks
Collect 10-20 real credit SMS per bank (and some OTP/debit/promo SMS as negatives). Try them one by one:
```
python -c "from paysure.parsing import parse_credit_sms; print(parse_credit_sms('PASTE THE SMS TEXT HERE'))"
```
It must show the right `amount` and `utr` (12-digit reference), and the sender header must match `BANK_HEADERS`. If a bank's format is not read, send me
three examples (with account numbers replaced by XXXX) and I will extend the parser.

---------------------------------------------------------------------------------------------------
## PART 12 - Measure your real numbers (logs and payments)
**OCR accuracy.** Put your screenshots in a folder and make `answers.csv`:
```
file,amount,utr,upi_id
a1.png,500,412345678901,shop@okbank
```
```
python train/check_ocr.py PATH_TO_FOLDER answers.csv
```
It prints accuracy per field and lists each miss (which app or theme fails).
**Time window.** For each real payment write `screenshot_time,alert_time` (like `2026-11-24 14:00,2026-11-24 14:01`) in `times.csv`, then:
```
python train/analyze_times.py times.csv
```
Use the suggested value as the server variable `TIME_TOLERANCE_MIN` (local: `$env:TIME_TOLERANCE_MIN="6"`; Space: add as a variable).
Need 100+ rows to trust it.

---------------------------------------------------------------------------------------------------
## PART 13 - What to put in your report
1. Problem and the principle: "a screenshot is a claim; only trusted evidence of money is proof".
2. The attack table in README.md (what each defence stops).
3. Your numbers from Part 10 and 12: false alarms on genuine, detection per attack type, never-trained results, OCR accuracy, time-gap percentiles.
4. Limitations (README "Residual risks") - saying them honestly is a strength.

## Troubleshooting
- `tesseract is not installed` -> Part 2 step 3.
- `ModuleNotFoundError` -> the virtual environment is not active; run the activate command again.
- Everything RED -> time zone: set `SHOP_TZ` (default `Asia/Kolkata`).
- Never GREEN -> check `BANK_HEADERS` matches the SMS sender; amount, reference and time (within the window) match the screenshot; `MERCHANT_VPAS` equals the UPI ID on the screenshot.
- `401 bad or missing app key` -> type the same `APP_KEY` into the page's key box.
- Warning "scikit-learn version" at server start -> make `requirements.txt` match the version you trained with, or retrain.
- git push to Hugging Face asks for a password -> paste the Write token, not your account password.
