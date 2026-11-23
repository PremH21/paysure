# PaySure Companion (Android) - STATUS: written but NOT compiled or run

I had no Android SDK in my environment, so this source has never been built or run on a phone. Expect to fix small
build errors. The data format it sends WAS tested against the server code (tests/test_companion_contract.py).

## Build (free)
1. Install Android Studio (free). Open the `android/` folder; let it download the SDK and sync Gradle.
2. If Studio complains about plugin versions, accept its suggested upgrade.
3. Run on your phone (USB debugging) or Build > Build APK and install the APK.

## Use
1. On the server set: DEVICE_KEY=<long random secret>, BANK_HEADERS=<your bank's header code(s)>,
   TRUSTED_PACKAGES=<package name of your payment app>.
   Find your bank's header: open one real credit SMS - the sender looks like `VM-HDFCBK-S`; the code is `HDFCBK`.
   Find a payment app's package name: Settings > Apps > (app) > App info, or the Play Store URL `?id=...`.
2. In the app: enter the server URL + same key, press Save, grant SMS permission, enable notification access.
3. Credit SMS and "money received" notifications now flow to the server as trusted evidence.

## Honest notes
- Reading SMS is restricted on Google Play. This is meant for your own phone (sideloaded APK), not a Play Store release.
- Only messages containing words like "credited/received" are forwarded; other SMS never leave the phone.
- Events are queued on the phone and retried, so a sleeping free server or no signal loses nothing.
- Notification text is only as trustworthy as the package allowlist on the server; with no allowlist the server marks it unverified.
- Phone time zone must be the shop's local time (the server compares it to times printed on screenshots).
