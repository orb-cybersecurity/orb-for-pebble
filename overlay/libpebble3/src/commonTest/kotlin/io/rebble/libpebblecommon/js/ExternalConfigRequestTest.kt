package io.rebble.libpebblecommon.js

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNotEquals

class ExternalConfigRequestTest {
    @Test fun oldCallbacksExpire() {
        val time = kotlin.time.TestTimeSource()
        val request = ExternalConfigRequest(time)
        val state = request.begin()
        time += kotlin.time.Duration.parse("10m")
        assertFalse(request.consume(state))
    }

    @Test fun callbacksMustBelongToAnOutstandingSessionAndAreSingleUse() {
        val first = ExternalConfigRequest()
        val second = ExternalConfigRequest()
        assertFalse(first.consume("unsolicited"))
        val state = first.begin()
        assertFalse(first.consume(null))
        assertFalse(second.consume(state))
        assertTrue(first.consume(state))
        assertFalse(first.consume(state))
        val next = first.begin()
        assertNotEquals(state, next)
        assertFalse(first.consume(state))
        first.clear()
        assertFalse(first.consume(next))
    }
}
