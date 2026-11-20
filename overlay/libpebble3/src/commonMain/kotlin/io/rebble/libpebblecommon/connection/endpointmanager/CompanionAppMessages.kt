package io.rebble.libpebblecommon.connection.endpointmanager

import io.rebble.libpebblecommon.connection.CompanionApp
import io.rebble.libpebblecommon.services.appmessage.AppMessageData
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

internal suspend fun CoroutineScope.startCompanionApps(
    apps: List<CompanionApp>,
    inbound: () -> Flow<AppMessageData>,
) {
    if (apps.isEmpty()) {
        cancel()
        return
    }
    val channels = apps.map { Channel<AppMessageData>(Channel.BUFFERED) }
    apps.zip(channels).forEach { (app, channel) -> app.start(channel.receiveAsFlow()) }
    launch {
        inbound().collect { message ->
            for (channel in channels) channel.trySend(message)
        }
    }
}
