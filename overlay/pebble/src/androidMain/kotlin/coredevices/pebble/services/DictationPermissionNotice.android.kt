package coredevices.pebble.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import androidx.core.app.NotificationCompat
import io.rebble.libpebblecommon.connection.AppContext
import coredevices.util.R

const val REQUEST_DICTATION_PERMISSION = "orb_request_dictation_permission"
private const val CHANNEL = "dictation_permission"

// Read at session time; PermissionRequester depends on LibPebble during startup.
internal actual fun hasDictationPermission(appContext: AppContext): Boolean =
    androidx.core.content.ContextCompat.checkSelfPermission(appContext.context,
        android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED

internal actual fun notifyDictationPermissionNeeded(appContext: AppContext) {
    val context = appContext.context
    val manager = context.getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel(CHANNEL, "Dictation permission", NotificationManager.IMPORTANCE_DEFAULT))
    val launch = context.packageManager.getLaunchIntentForPackage(context.packageName) ?: return
    launch.putExtra(REQUEST_DICTATION_PERMISSION, true)
    val tap = PendingIntent.getActivity(context, CHANNEL.hashCode(), launch, PendingIntent.FLAG_IMMUTABLE)
    val text = "Allow microphone access so Orb can pass watch dictation to your speech recognizer"
    manager.notify(CHANNEL.hashCode(), NotificationCompat.Builder(context, CHANNEL)
        .setSmallIcon(R.drawable.ic_notification)
        .setContentTitle("Watch dictation")
        .setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text))
        .setContentIntent(tap)
        .setAutoCancel(true)
        .setOnlyAlertOnce(true)
        .build())
}
