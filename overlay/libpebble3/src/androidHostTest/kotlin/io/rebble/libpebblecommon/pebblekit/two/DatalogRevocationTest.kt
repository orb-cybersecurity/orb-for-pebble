package io.rebble.libpebblecommon.pebblekit.two

import io.rebble.libpebblecommon.datalogging.ThirdPartyDatalogEvent
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class DatalogRevocationTest {
    @Test fun revocationDropsQueuedBatchesFinishesAndRetries() = runTest {
        for (ack in listOf(true, false)) {
            var granted = true
            var sends = 0
            var closed = false
            val uuid = Uuid.random()
            val sender = object : DatalogSender {
                override suspend fun isAuthorized() = granted
                override suspend fun sendBatch(event: ThirdPartyDatalogEvent.Batch): Boolean {
                    sends++
                    granted = false
                    return ack
                }
                override suspend fun sendFinished(event: ThirdPartyDatalogEvent.Finished): Boolean {
                    error("Revoked finish delivered")
                }
                override fun close() { closed = true }
            }
            val delivery = DatalogDelivery(this, { sender })
            delivery.enqueue(ThirdPartyDatalogEvent.Batch(uuid, 1u, 1u, 4u, "serial", 1u, byteArrayOf(1)))
            delivery.enqueue(ThirdPartyDatalogEvent.Finished(uuid, 1u, 1u, 4u, "serial"))
            delivery.enqueue(ThirdPartyDatalogEvent.Batch(uuid, 1u, 1u, 4u, "serial", 0u, byteArrayOf(2)))
            advanceUntilIdle()
            assertEquals(1, sends)
            assertTrue(closed)
        }
    }
}
