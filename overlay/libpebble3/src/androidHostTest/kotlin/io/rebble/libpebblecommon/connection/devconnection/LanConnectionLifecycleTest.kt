package io.rebble.libpebblecommon.connection.devconnection

import io.rebble.libpebblecommon.PacketPriority
import io.rebble.libpebblecommon.connection.LibPebble
import io.rebble.libpebblecommon.connection.PebbleIdentifier
import io.rebble.libpebblecommon.connection.PebbleProtocolHandler
import io.rebble.libpebblecommon.connection.PebbleSocketIdentifier
import io.rebble.libpebblecommon.connection.endpointmanager.CompanionAppLifecycleManager
import io.rebble.libpebblecommon.connection.endpointmanager.LastFirmwareUpdateStates
import io.rebble.libpebblecommon.di.ConnectionCoroutineScope
import io.rebble.libpebblecommon.plugin.PluginLogs
import io.rebble.libpebblecommon.protocolhelpers.PebblePacket
import java.lang.reflect.Proxy
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class LanConnectionLifecycleTest {
    private val identifier = PebbleSocketIdentifier("test-watch")
    private val protocol = object : PebbleProtocolHandler {
        override val inboundMessages = MutableSharedFlow<PebblePacket>()
        override val rawInboundMessages = emptyFlow<ByteArray>()
        override suspend fun send(message: PebblePacket, priority: PacketPriority) = Unit
        override suspend fun send(message: ByteArray, priority: PacketPriority) = Unit
    }

    // Only currentPKJSSession is read; no Android, Bluetooth or watch services are started.
    private fun lifecycle(): CompanionAppLifecycleManager {
        val unsafeField = sun.misc.Unsafe::class.java.getDeclaredField("theUnsafe").apply { isAccessible = true }
        val unsafe = unsafeField.get(null) as sun.misc.Unsafe
        val manager = unsafe.allocateInstance(CompanionAppLifecycleManager::class.java) as CompanionAppLifecycleManager
        CompanionAppLifecycleManager::class.java.getDeclaredField("currentPKJSSession").apply {
            isAccessible = true
            set(manager, MutableStateFlow(null))
        }
        return manager
    }

    private class RecordingTransport : DevConnectionTransport(
        Proxy.newProxyInstance(LibPebble::class.java.classLoader, arrayOf(LibPebble::class.java)) { _, method, _ ->
            error("Unexpected watch operation: ${method.name}")
        } as LibPebble,
        LastFirmwareUpdateStates(),
    ) {
        var starts = 0
        var stops = 0
        var listening = false
        override suspend fun start(identifier: PebbleIdentifier, inboundPKJSLogs: Flow<String>, inboundDeviceMessages: Flow<ByteArray>, outboundDeviceMessages: suspend (ByteArray) -> Unit) {
            starts++
            listening = true
            awaitCancellation()
        }
        override suspend fun stop() { stops++; listening = false }
    }

    @Test fun disablingLanStopsTheListenerAndDoesNotResumeWhenReenabled() = runTest {
        val server = RecordingTransport()
        val transport = MutableStateFlow<DevConnectionTransport?>(server)
        val resumer = DevConnectionResumer()
        val manager = DevConnectionManager(transport, identifier, protocol, lifecycle(), PluginLogs(), resumer,
            ConnectionCoroutineScope(backgroundScope.coroutineContext))
        manager.startDevConnection()
        runCurrent()
        assertTrue(server.listening)
        assertTrue(manager.devConnectionActive.value)
        transport.value = null
        runCurrent()
        assertFalse(server.listening)
        assertEquals(1, server.stops)
        assertFalse(manager.devConnectionActive.value)
        assertTrue(resumer.active.value.isEmpty())
        transport.value = server
        runCurrent()
        assertEquals(1, server.starts)
    }

    @Test fun startingWithLanDisabledNeverOpensTheListener() = runTest {
        val resumer = DevConnectionResumer()
        val manager = DevConnectionManager(MutableStateFlow(null), identifier, protocol, lifecycle(), PluginLogs(), resumer,
            ConnectionCoroutineScope(backgroundScope.coroutineContext))
        manager.startDevConnection()
        runCurrent()
        assertFalse(manager.devConnectionActive.value)
        assertTrue(resumer.active.value.isEmpty())
    }
}
