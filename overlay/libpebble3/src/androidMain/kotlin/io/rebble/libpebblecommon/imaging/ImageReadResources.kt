package io.rebble.libpebblecommon.imaging

import java.io.Closeable
import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

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

private const val MAX_IMAGE_READS = 2
internal val readsInFlight = AtomicInteger()
// Never cancelled, so every started read reaches its finally and returns its slot.
private val imageReads = CoroutineScope(SupervisorJob() + Dispatchers.IO)

/**
 * A blocking provider must not hold up the serial consumer after its deadline. Hung providers
 * can hold at most [MAX_IMAGE_READS] threads; further reads give up at once instead of queueing,
 * and a read in progress keeps only its own resources, never the caller.
 */
internal suspend fun <T> readImageWithTimeout(
    timeoutMs: Long = 2_000,
    read: (ImageReadResources) -> T?,
): T? {
    if (readsInFlight.incrementAndGet() > MAX_IMAGE_READS) {
        readsInFlight.decrementAndGet()
        return null
    }
    val resources = ImageReadResources()
    val result = CompletableDeferred<T?>()
    imageReads.launch {
        try { result.complete(read(resources)) }
        catch (_: Exception) { result.complete(null) }
        finally {
            resources.close()
            readsInFlight.decrementAndGet()
        }
    }
    try {
        return withTimeoutOrNull(timeoutMs) { result.await() }
    } finally {
        // Unblocks a provider read in progress; a descriptor it returns later is closed by track().
        if (!result.isCompleted) resources.close()
    }
}
