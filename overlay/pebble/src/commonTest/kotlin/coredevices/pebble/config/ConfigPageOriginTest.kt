package coredevices.pebble.config

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ConfigPageOriginTest {
    @Test fun onlyTheExpectedMainFrameCanCallTheBridge() {
        val page = "https://config.example.org:443/settings?secret=x"
        assertTrue(configPageMayUseBridge(page, "https://config.example.org", true, page))
        assertFalse(configPageMayUseBridge(page, "https://config.example.org", false, page))
        assertFalse(configPageMayUseBridge(page, "https://other.example.org", true, page))
        assertFalse(configPageMayUseBridge(page, "http://config.example.org", true, page))
        assertFalse(configPageMayUseBridge(page, "https://config.example.org:444", true, page))
        assertFalse(configPageMayUseBridge(page, "null", true, page))
    }

    @Test fun opaquePagesMustBeTheExactRequestedDocument() {
        val page = "data:text/html,settings"
        assertTrue(configPageMayUseBridge(page, "null", true, page))
        assertFalse(configPageMayUseBridge(page, "null", false, page))
        assertFalse(configPageMayUseBridge(page, "null", true, "data:text/html,other"))
        assertFalse(configPageMayUseBridge("file:///private/file", "null", true, "file:///private/file"))
    }
}
