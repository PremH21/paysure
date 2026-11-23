package `in`.paysure.companion

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Captures "money received" notifications from payment apps. The Android package name of the app that posted it is sent
 * along; the SERVER only trusts packages on the merchant's allowlist (TRUSTED_PACKAGES), so a "fake notification" app
 * cannot create trusted evidence. Enable in: Settings > Notifications > Device & app notifications (notification access).
 */
class PaymentNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName) return
        val ex = sbn.notification.extras
        val text = listOfNotNull(
            ex.getCharSequence(Notification.EXTRA_TITLE),
            ex.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: ex.getCharSequence(Notification.EXTRA_TEXT)
        ).joinToString(" ").trim()
        if (text.isEmpty() || !CreditFilter.looksLikeCredit(text)) return
        Uploader.enqueue(this, "/credit/notification", mapOf(
            "package" to sbn.packageName, "text" to text, "received_at" to Uploader.isoLocal(sbn.postTime)))
    }
}
