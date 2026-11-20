package coredevices.pebble.config

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.plugins.websocket.WebSockets
import io.rebble.libpebblecommon.permissions.NetworkAccess
import io.rebble.libpebblecommon.plugin.PluginNetworkVerdict
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.job
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class ConfigPageSocketsTest {
    private fun create(document: String, id: Int) = Json.parseToJsonElement(
        """{"document":"$document","method":"createInstance","args":["wss://api.example/socket","chat","",$id]}""",
    )

    @Test fun bridgeSocketsUseTheLiveGateAndCancelOnRevocation() = runTest {
        var allowed = true
        val changes = MutableSharedFlow<Unit>()
        val access = object : NetworkAccess {
            override suspend fun check(url: String, wait: Boolean) =
                if (allowed) PluginNetworkVerdict.Allowed else PluginNetworkVerdict.Denied("revoked")
            override fun changes() = changes
        }
        var dialled = 0
        val started = CompletableDeferred<Unit>()
        val client = HttpClient(MockEngine { dialled++; started.complete(Unit); awaitCancellation() }) { install(WebSockets) }
        val events = mutableListOf<String>()
        val sockets = ConfigPageSockets(this, Uuid.random(), { events += it }, client, access, { _, _, _, _, _ -> })
        try {
            sockets.dispatch(create("first", 7))
            runCurrent()
            started.await()
            allowed = false
            changes.emit(Unit)
            coroutineContext.job.children.toList().joinAll()
            assertTrue(events.any { "get(7)._onClose(1006" in it && "=== \"first\"" in it })
            sockets.dispatch(create("first", 9))
            coroutineContext.job.children.toList().joinAll()
            assertEquals(1, dialled)
            assertTrue(events.any { "get(9)._onError()" in it })
            // A new document may restart its JS IDs; old events carry only the old document token.
            sockets.dispatch(create("next", 7))
            coroutineContext.job.children.toList().joinAll()
            assertTrue(events.any { "get(7)._onError()" in it && "=== \"next\"" in it })
        } finally { sockets.close(); client.close() }
    }
}
