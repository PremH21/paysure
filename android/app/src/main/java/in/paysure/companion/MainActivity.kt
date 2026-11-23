package `in`.paysure.companion

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/** One screen: server address, device key, two permission buttons, queue status. No libraries needed. */
class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }
        fun lp() = LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = pad / 2 }

        root.addView(TextView(this).apply {
            text = "PaySure Companion\nForwards bank credit SMS and payment-app notifications to YOUR PaySure server."
            textSize = 16f
        }, lp())
        val server = EditText(this).apply {
            hint = "Server URL, e.g. https://you-paysure.hf.space"; setText(Prefs.serverUrl(this@MainActivity))
            inputType = InputType.TYPE_TEXT_VARIATION_URI
        }
        val key = EditText(this).apply { hint = "Device key (same as DEVICE_KEY on server)"; setText(Prefs.deviceKey(this@MainActivity)) }
        root.addView(server, lp()); root.addView(key, lp())

        root.addView(Button(this).apply {
            text = "Save"; setOnClickListener {
                Prefs.save(this@MainActivity, server.text.toString(), key.text.toString()); refresh(); Uploader.flushAsync(this@MainActivity) { runOnUiThread { refresh() } }
            }
        }, lp())
        root.addView(Button(this).apply {
            text = "1. Allow reading SMS"; setOnClickListener {
                requestPermissions(arrayOf(Manifest.permission.RECEIVE_SMS), 1)
            }
        }, lp())
        root.addView(Button(this).apply {
            text = "2. Allow notification access"; setOnClickListener {
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }
        }, lp())
        status = TextView(this).apply { textSize = 15f }
        root.addView(status, lp())
        setContentView(root)
    }

    override fun onResume() { super.onResume(); refresh(); Uploader.flushAsync(this) { runOnUiThread { refresh() } } }

    private fun refresh() {
        val sms = checkSelfPermission(Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED
        val notif = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")?.contains(packageName) == true
        status.text = "SMS permission: ${if (sms) "granted" else "NOT granted"}\n" +
            "Notification access: ${if (notif) "on" else "OFF"}\n" +
            "Server set: ${Prefs.serverUrl(this).isNotEmpty() && Prefs.deviceKey(this).isNotEmpty()}\n" +
            "Waiting to upload: ${Uploader.pending(this)}"
    }

    override fun onRequestPermissionsResult(r: Int, p: Array<out String>, g: IntArray) { refresh() }
}
