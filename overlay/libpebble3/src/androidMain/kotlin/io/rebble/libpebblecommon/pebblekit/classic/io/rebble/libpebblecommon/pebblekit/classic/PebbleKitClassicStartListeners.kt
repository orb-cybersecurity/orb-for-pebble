package io.rebble.libpebblecommon.pebblekit.classic

import android.content.Context
import android.content.IntentFilter
import co.touchlab.kermit.Logger
import io.rebble.libpebblecommon.connection.LibPebble
import io.rebble.libpebblecommon.di.LibPebbleCoroutineScope
import io.rebble.libpebblecommon.util.asFlow
import kotlinx.coroutines.launch
import java.io.Serializable
import java.util.UUID
import kotlin.uuid.Uuid
import kotlin.uuid.toKotlinUuid

private val logger = Logger.withTag("PebbleKitClassicStartListeners")

class PebbleKitClassicStartListeners(
    private val context: Context,
    private val libPebble: LibPebble,
    private val coroutineScope: LibPebbleCoroutineScope
) {
    fun init() {
        val receiver = object : android.content.BroadcastReceiver() {
            override fun onReceive(context: Context, intent: android.content.Intent) {
                // Before Android 14 the platform supplies no authenticated broadcast sender.
                if (android.os.Build.VERSION.SDK_INT < 34) return
                val callers = context.packageManager.getPackagesForUid(sentFromUid).orEmpty().toList()
                if (callers.isEmpty()) return
                val uuid = runCatching { intent.getSerializableExtra(APP_UUID)?.asUuid() }.getOrNull() ?: return
                val action = intent.action
                coroutineScope.launch {
                    if (!io.rebble.libpebblecommon.pebblekit.PebbleKitAuthorization.allowed(callers, uuid)) return@launch
                    when (action) {
                        INTENT_APP_START -> libPebble.launchApp(uuid)
                        INTENT_APP_STOP -> libPebble.stopApp(uuid)
                    }
                }
            }
        }
        androidx.core.content.ContextCompat.registerReceiver(context, receiver,
            IntentFilter().apply { addAction(INTENT_APP_START); addAction(INTENT_APP_STOP) },
            androidx.core.content.ContextCompat.RECEIVER_EXPORTED)
    }
}

fun Serializable.asUuid(): Uuid? = (this as? UUID)?.toKotlinUuid() ?: (this as? String)?.let {
    try {
        Uuid.parse(it)
    } catch (e: IllegalArgumentException) {
        logger.w { "Invalid watchapp UUID" }
        null
    }
}

/**
 * Intent broadcast to pebble.apk responsible for launching a watch-app on the connected watch. This intent is
 * idempotent.
 */
private const val INTENT_APP_START = "com.getpebble.action.app.START"

/**
 * Intent broadcast to pebble.apk responsible for closing a running watch-app on the connected watch. This intent is
 * idempotent.
 */
private const val INTENT_APP_STOP = "com.getpebble.action.app.STOP"


/**
 * The bundle-key used to store a message's UUID.
 */
private const val APP_UUID = "uuid"
