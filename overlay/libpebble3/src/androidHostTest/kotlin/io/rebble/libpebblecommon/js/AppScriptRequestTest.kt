package io.rebble.libpebblecommon.js

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AppScriptRequestTest {
    @Test fun foreignPathsCannotConsumeTheRequestAndTheOwnPathLoadsOnlyOnce() {
        val request = AppScriptRequest("/cache/pkjs/own.js")
        assertFalse(request.accept("/cache/pkjs/other.js"))
        assertTrue(request.accept("/cache/pkjs/own.js"))
        assertFalse(request.accept("/cache/pkjs/own.js"))
        assertFalse(request.accept("/cache/pkjs/other.js"))
        assertTrue(AppScriptRequest("/cache/pkjs/own.js").accept("/cache/pkjs/own.js"))
    }
}
