package `in`.paysure.companion

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Settings saved by the user on the main screen. */
object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("paysure", Context.MODE_PRIVATE)
    fun serverUrl(c: Context) = sp(c).getString("server", "")!!.trim().trimEnd('/')
    fun deviceKey(c: Context) = sp(c).getString("key", "")!!.trim()
    fun save(c: Context, server: String, key: String) =
        sp(c).edit().putString("server", server).putString("key", key).apply()
}

/**
 * Sends credit events to the PaySure server. Events are written to a small on-device queue FIRST and removed only after the
 * server answers 2xx, so a dead zone or a sleeping free-tier server loses nothing; the queue is retried on every new event
 * and whenever the app is opened.
 */
object Uploader {
    private const val QUEUE = "queue"
    private val lock = Any()

    /** Local time without zone, e.g. 2026-10-27T10:35:00 - the server compares it with times printed on screenshots. */
    fun isoLocal(millis: Long): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).format(Date(millis))

    fun enqueue(c: Context, path: String, fields: Map<String, String>) {
        synchronized(lock) {
            val sp = c.getSharedPreferences("paysure", Context.MODE_PRIVATE)
            val arr = JSONArray(sp.getString(QUEUE, "[]"))
            arr.put(JSONObject().put("path", path).put("fields", JSONObject(fields)))
            sp.edit().putString(QUEUE, arr.toString()).apply()
        }
        flushAsync(c)
    }

    fun pending(c: Context): Int = synchronized(lock) {
        JSONArray(c.getSharedPreferences("paysure", Context.MODE_PRIVATE).getString(QUEUE, "[]")).length()
    }

    fun flushAsync(c: Context, done: (() -> Unit)? = null) {
        val app = c.applicationContext
        Thread {
            try { flush(app) } finally { done?.invoke() }
        }.start()
    }

    private fun flush(c: Context) {
        val server = Prefs.serverUrl(c); val key = Prefs.deviceKey(c)
        if (server.isEmpty() || key.isEmpty()) return
        while (true) {
            val item = synchronized(lock) {
                val arr = JSONArray(c.getSharedPreferences("paysure", Context.MODE_PRIVATE).getString(QUEUE, "[]"))
                if (arr.length() == 0) null else arr.getJSONObject(0)
            } ?: return
            val ok = post(server + item.getString("path"), key, item.getJSONObject("fields"))
            if (!ok) return                      // keep it queued, try again later
            synchronized(lock) {
                val sp = c.getSharedPreferences("paysure", Context.MODE_PRIVATE)
                val arr = JSONArray(sp.getString(QUEUE, "[]"))
                val rest = JSONArray()
                for (i in 1 until arr.length()) rest.put(arr.get(i))
                sp.edit().putString(QUEUE, rest.toString()).apply()
            }
        }
    }

    private fun post(url: String, key: String, fields: JSONObject): Boolean = try {
        val body = fields.keys().asSequence().joinToString("&") {
            URLEncoder.encode(it, "UTF-8") + "=" + URLEncoder.encode(fields.getString(it), "UTF-8")
        }
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"; conn.connectTimeout = 15000; conn.readTimeout = 30000   // free servers wake slowly
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        conn.setRequestProperty("X-Device-Key", key)
        conn.outputStream.use { it.write(body.toByteArray()) }
        val code = conn.responseCode
        conn.disconnect()
        code in 200..299
    } catch (e: Exception) { false }
}
