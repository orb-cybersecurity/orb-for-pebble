package io.rebble.libpebblecommon.js

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNotEquals

class ExternalConfigRequestTest {
    @Test fun inAppStateDoesNotExpireButRemainsSingleUseAndSessionBound() {
        val time = kotlin.time.TestTimeSource()
        val request = ExternalConfigRequest(time)
        val state = request.begin()
        time += kotlin.time.Duration.parse("30m")
        assertTrue(request.consume(state, external = false))
        assertFalse(request.consume(state, external = false))
        val old = request.begin()
        val next = request.begin()
        assertFalse(request.consume(old, external = false))
        request.clear()
        assertFalse(request.consume(next, external = false))
    }

    @Test fun oldCallbacksExpire() {
        val time = kotlin.time.TestTimeSource()
        val request = ExternalConfigRequest(time)
        val state = request.begin()
        time += kotlin.time.Duration.parse("10m")
        assertFalse(request.consume(state))
    }

    @Test fun expiredExternalCallbacksLeaveTheInAppRequestUsable() {
        val time = kotlin.time.TestTimeSource()
        val request = ExternalConfigRequest(time)
        val state = request.begin()
        time += kotlin.time.Duration.parse("12m")
        assertFalse(request.consume("stale-or-unrelated"))
        assertFalse(request.consume(state))
        assertFalse(request.consume(state))
        assertTrue(request.consume(state, external = false))
        assertFalse(request.consume(state, external = false))
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
