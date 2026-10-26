package org.ssas.board

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Settings

/**
 * After a restart or an app update. Android only gives the camera to a service started from a visible
 * screen, so this opens the invisible ArmActivity — possible when "display over other apps" is allowed.
 * (Normally the Hikvision "Auto-Launch" setting opens the app at power-on.)
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (Settings.canDrawOverlays(context)) {
            context.startActivity(Intent(context, ArmActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}
