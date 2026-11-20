package io.rebble.libpebblecommon.js

import java.util.concurrent.atomic.AtomicBoolean

/** Each startup document may restore storage and execute only its own script, once. */
internal class AppScriptRequest(private val jsPath: String) {
    private val requested = AtomicBoolean(false)
    fun rearm() { requested.set(false) }
    fun accept(path: String): Boolean = path == jsPath && requested.compareAndSet(false, true)
}
