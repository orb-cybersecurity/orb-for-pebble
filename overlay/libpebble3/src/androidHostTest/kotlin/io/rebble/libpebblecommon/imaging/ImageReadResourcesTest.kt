package io.rebble.libpebblecommon.imaging

import java.io.Closeable
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ImageReadResourcesTest {
    @Test fun timeoutClosesABlockedReadAndReleasesTheCaller() = runBlocking {
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
