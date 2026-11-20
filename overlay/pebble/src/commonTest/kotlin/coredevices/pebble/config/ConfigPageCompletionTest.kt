package coredevices.pebble.config

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ConfigPageCompletionTest {
    private val page = "https://config.example.org:443/settings?secret=x"

    @Test fun legacyCompletionNeedsTheExpectedMainDocument() {
        fun allowed(current: String?, main: Boolean = true) =
            configPageMayComplete(page, current, main, null) { error("No state to consume") }
        assertTrue(allowed("https://config.example.org/finished"))
        assertFalse(allowed(page, false))
        assertFalse(allowed("https://other.example.org/finished"))
        assertFalse(allowed("http://config.example.org/finished"))
        assertFalse(allowed("https://config.example.org:444/finished"))
        assertFalse(allowed(null))
    }

    @Test fun redirectCompletionRequiresAnOutstandingStateAndNeverAcceptsSubframes() {
        var pending: String? = "bound-state"
        fun allowed(state: String, main: Boolean = true) =
            configPageMayComplete(page, "https://login.example.org/finished", main, state) {
                (pending == it).also { accepted -> if (accepted) pending = null }
            }
        assertFalse(allowed("wrong-state"))
        assertFalse(allowed("bound-state", false))
        assertTrue(allowed("bound-state"))
        assertFalse(allowed("bound-state"))
    }

    @Test fun bundledPagesMustRemainTheExactDocument() {
        val data = "data:text/html,settings"
        assertTrue(configPageMayComplete(data, data, true, null) { false })
        assertFalse(configPageMayComplete(data, "data:text/html,other", true, null) { false })
        assertFalse(configPageMayComplete(data, data, false, null) { false })
        assertFalse(configPageMayComplete("file:///private", "file:///private", true, null) { false })
    }
}
