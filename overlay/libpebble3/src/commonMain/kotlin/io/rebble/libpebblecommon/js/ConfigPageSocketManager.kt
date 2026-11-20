package io.rebble.libpebblecommon.js

import io.rebble.libpebblecommon.di.LibPebbleKoinComponent
import io.rebble.libpebblecommon.permissions.NetworkGate
import kotlinx.coroutines.CoroutineScope
import kotlin.uuid.Uuid

/** Config pages use the same native socket transport and per-app gate as PKJS. */
fun configPageSocketManager(scope: CoroutineScope, uuid: Uuid, eval: (String) -> Unit): WebSocketManager {
    val koin = object : LibPebbleKoinComponent {}.getKoin()
    return WebSocketManager(scope, eval, koin.get(), uuid,
        NetworkGate(koin.get(), "Watchapp settings", uuid), koin.get())
}
