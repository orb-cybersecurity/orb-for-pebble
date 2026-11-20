package io.rebble.libpebblecommon.connection.endpointmanager

import io.rebble.libpebblecommon.connection.CompanionApp
import io.rebble.libpebblecommon.services.appmessage.AppMessageData
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class CompanionAppMessagesTest {
    @Test fun noCompanionCancelsScopeWithoutOpeningOrCollectingMessages() = runTest {
        val job = Job()
        val scope = CoroutineScope(coroutineContext + job)
        val messages = MutableSharedFlow<AppMessageData>()
        var opened = false
        scope.startCompanionApps(emptyList()) {
            opened = true
            messages
        }
        runCurrent()
        assertTrue(job.isCancelled)
        assertTrue(job.children.none())
        assertFalse(opened)
        assertEquals(0, messages.subscriptionCount.value)
        messages.emit(AppMessageData(1u, Uuid.random(), emptyMap()))
        runCurrent()
        assertFalse(opened)
        assertEquals(0, messages.subscriptionCount.value)
    }

    @Test fun liveCompanionsShareOneCollectorAndReceiveMessagesUntilStopped() = runTest {
        val scope = CoroutineScope(coroutineContext + Job())
        val messages = MutableSharedFlow<AppMessageData>()
        val received = List(2) { mutableListOf<AppMessageData>() }
        val apps = received.map { sink ->
            object : CompanionApp {
                override suspend fun start(incomingAppMessages: Flow<AppMessageData>) {
                    incomingAppMessages.onEach { sink += it }.launchIn(scope)
                }
                override suspend fun stop() {}
            }
        }
        try {
            scope.startCompanionApps(apps) { messages }
            runCurrent()
            assertEquals(1, messages.subscriptionCount.value)
            val message = AppMessageData(1u, Uuid.random(), emptyMap())
            messages.emit(message)
            runCurrent()
            received.forEach { assertEquals(listOf(message), it) }
        } finally {
            scope.cancel()
        }
        runCurrent()
        assertEquals(0, messages.subscriptionCount.value)
    }
}
