package io.rebble.libpebblecommon.js

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.rebble.libpebblecommon.permissions.NetworkAccess
import io.rebble.libpebblecommon.plugin.PluginNetworkVerdict
import kotlinx.coroutines.job
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class WebSocketRedirectPolicyTest {
    @Test fun anAllowedUpgradeCannotRedirectAroundTheHostCheck() = runTest {
        val dialled = mutableListOf<String>()
        val client = HttpClient(MockEngine { request ->
            dialled += request.url.host
            respond("", HttpStatusCode.Found, headersOf("Location", "wss://denied.example/socket"))
        }) { install(WebSockets) }
        val events = mutableListOf<String>()
        val access = NetworkAccess { url, _ ->
            if ("allowed.example" in url) PluginNetworkVerdict.Allowed else PluginNetworkVerdict.Denied("refused")
        }
        val manager = WebSocketManager(this, { events += it }, client, Uuid.random(), access, { _, _, _, _, _ -> })
        try {
            manager.dispatch("createInstance", listOf("wss://allowed.example/socket", ""))
            coroutineContext.job.children.toList().joinAll()
            assertEquals(listOf("allowed.example"), dialled)
            assertTrue(events.any { "_onClose(1006" in it })
        } finally { manager.close(); client.close() }
    }
}
