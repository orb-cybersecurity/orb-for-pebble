package io.rebble.libpebblecommon.imaging

import java.io.Closeable
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ImageReadResourcesTest {
    @Test fun hungProvidersCannotOccupyMoreThanTwoWorkersAndQueuedReadsExpire() = runBlocking {
        awaitIdleImageReads()
        val release = CountDownLatch(1)
        val started = CountDownLatch(2)
        val finished = CountDownLatch(2)
        val active = AtomicInteger()
        val peak = AtomicInteger()
        val calls = AtomicInteger()
        try {
            val reads = List(12) {
                async {
                    readImageWithTimeout(1_000) {
                        calls.incrementAndGet()
                        peak.accumulateAndGet(active.incrementAndGet(), ::maxOf)
                        started.countDown()
                        try { release.await(); "late" }
                        finally { active.decrementAndGet(); finished.countDown() }
                    }
                }
            }
            assertTrue(withContext(Dispatchers.Default) { started.await(5, TimeUnit.SECONDS) })
            assertTrue(reads.awaitAll().all { it == null })
            assertEquals(2, peak.get())
            assertEquals(2, calls.get())
        } finally {
            release.countDown()
            assertTrue(finished.await(5, TimeUnit.SECONDS))
        }
        // Finished reads return their slots.
        awaitIdleImageReads()
        assertEquals("ok", readImageWithTimeout(1_000) { "ok" })
    }

    private fun awaitIdleImageReads() {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (readsInFlight.get() != 0 && System.nanoTime() < deadline) Thread.sleep(10)
        assertEquals(0, readsInFlight.get())
    }

    @Test fun readsBeyondTheLimitGiveUpWithoutWaiting() = runBlocking<Unit> {
        awaitIdleImageReads()
        val release = CountDownLatch(1)
        val started = CountDownLatch(2)
        val finished = CountDownLatch(2)
        try {
            val pinned = List(2) {
                async {
                    readImageWithTimeout(5_000) {
                        started.countDown()
                        try { release.await(); "late" } finally { finished.countDown() }
                    }
                }
            }
            assertTrue(withContext(Dispatchers.Default) { started.await(5, TimeUnit.SECONDS) })
            val before = System.nanoTime()
            assertNull(readImageWithTimeout(5_000) { "never runs" })
            assertTrue(System.nanoTime() - before < TimeUnit.SECONDS.toNanos(1))
            release.countDown()
            pinned.awaitAll()
        } finally {
            release.countDown()
            assertTrue(finished.await(5, TimeUnit.SECONDS))
        }
    }

    @Test fun timeoutClosesABlockedReadAndReleasesTheCaller() = runBlocking {
        awaitIdleImageReads()
        val closed = CountDownLatch(1)
        val finished = CountDownLatch(1)
        val result = readImageWithTimeout(500) { resources ->
            resources.track(Closeable { closed.countDown() })
            try { closed.await(5, TimeUnit.SECONDS); "late" } finally { finished.countDown() }
        }
        assertNull(result)
        assertTrue(closed.await(1, TimeUnit.SECONDS))
        assertTrue(finished.await(1, TimeUnit.SECONDS))
    }

    @Test fun descriptorsReturnedAfterCancellationAreImmediatelyClosed() {
        val resources = ImageReadResources()
        resources.close()
        var closed = false
        assertFailsWith<IOException> { resources.track(Closeable { closed = true }) }
        assertTrue(closed)
    }
}
