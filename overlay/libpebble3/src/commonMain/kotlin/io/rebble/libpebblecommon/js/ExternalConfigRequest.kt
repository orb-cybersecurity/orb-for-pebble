package io.rebble.libpebblecommon.js

import kotlinx.coroutines.flow.MutableStateFlow
import kotlin.time.TimeSource
import kotlin.uuid.Uuid

internal class ExternalConfigRequest(private val time: TimeSource = TimeSource.Monotonic) {
    private data class Request(val state: String, val started: kotlin.time.TimeMark)
    private val pending = MutableStateFlow<Request?>(null)
    fun begin(): String = Uuid.random().toString().also { pending.value = Request(it, time.markNow()) }
    fun clear() { pending.value = null }
    fun consume(state: String?, external: Boolean = true): Boolean {
        val request = pending.value ?: return false
        if (external && request.started.elapsedNow().inWholeMinutes >= 10) { pending.compareAndSet(request, null); return false }
        return state == request.state && pending.compareAndSet(request, null)
    }
}
