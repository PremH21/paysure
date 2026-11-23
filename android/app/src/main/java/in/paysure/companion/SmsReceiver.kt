package `in`.paysure.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony

/**
 * Reads incoming SMS on the merchant's OWN phone. The sender header (e.g. VM-HDFCBK-S) and the receive time come from
 * the phone, not from anything a customer can type - that is what lets the server treat this as trusted evidence.
 * Only messages that look like a credit are forwarded; everything else stays on the phone.
 */
class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent) ?: return
        // A long SMS arrives as several parts from the same sender: join them before parsing.
        val bySender = LinkedHashMap<String, StringBuilder>()
        var millis = System.currentTimeMillis()
        for (p in parts) {
            val sender = p.originatingAddress ?: continue
            bySender.getOrPut(sender) { StringBuilder() }.append(p.messageBody ?: "")
            millis = p.timestampMillis
        }
        for ((sender, text) in bySender) {
            val body = text.toString()
            if (!CreditFilter.looksLikeCredit(body)) continue
            Uploader.enqueue(context, "/credit/sms", mapOf(
                "sender" to sender, "text" to body, "received_at" to Uploader.isoLocal(millis)))
        }
    }
}

object CreditFilter {
    private val re = Regex("credited|received|credit of|deposited|cr\\.", RegexOption.IGNORE_CASE)
    fun looksLikeCredit(text: String) = re.containsMatchIn(text)
}
