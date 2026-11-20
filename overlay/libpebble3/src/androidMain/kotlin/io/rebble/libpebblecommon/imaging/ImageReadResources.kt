package io.rebble.libpebblecommon.imaging

import java.io.Closeable
import java.io.IOException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/** Own descriptors even when cancellation races a provider returning from open(). */
internal class ImageReadResources : Closeable {
    private val resources = mutableListOf<Closeable>()
    private var closed = false

    @Synchronized fun <T : Closeable> track(resource: T): T {
        if (closed) {
            resource.close()
            throw IOException("Image read cancelled")
        }
        resources.add(resource)
        return resource
    }

    override fun close() {
        val toClose = synchronized(this) {
            if (closed) return
            closed = true
            resources.asReversed().toList().also { resources.clear() }
        }
        toClose.forEach { runCatching { it.close() } }
    }
}

// One shared, elastic IO view: uncooperative providers can pin at most two workers,
// without consuming the general IO dispatcher's parallelism budget.
private val imageReads = Dispatchers.IO.limitedParallelism(2)

/** A blocking provider must not hold up the serial consumer after its deadline. */
internal suspend fun <T> readImageWithTimeout(
    timeoutMs: Long = 2_000,
    read: (ImageReadResources) -> T?,
): T? = withTimeoutOrNull(timeoutMs) {
    suspendCancellableCoroutine { continuation ->
        val resources = ImageReadResources()
        // Deliberately independent of the caller's Job: a provider may ignore cancellation
        // during open(). Any descriptor it eventually returns is closed by track().
        val job = CoroutineScope(imageReads).launch {
            val result = try { read(resources) } catch (_: Exception) { null }
            finally { resources.close() }
            continuation.resume(result)
        }
        continuation.invokeOnCancellation {
            job.cancel() // Discard reads still queued behind a hung provider.
            resources.close()
        }
    }
}
