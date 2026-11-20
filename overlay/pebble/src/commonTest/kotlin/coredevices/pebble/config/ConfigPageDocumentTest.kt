package coredevices.pebble.config

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ConfigPageDocumentTest {
    @Test fun firstFinalOriginOwnsLegacyCloseStorageAndBridgeAndIsNeverRepinned() {
        val document = ConfigPageDocument("https://initial.example/settings")
        document.recordInitialLoad(null)
        document.recordInitialLoad("about:blank")
        document.recordInitialLoad("https://final.example/settings")
        document.recordInitialLoad("https://other.example/settings")
        assertEquals("https://final.example/settings", document.expectedUrl)
        assertTrue(configPageMayComplete(document.expectedUrl, "https://final.example/save", true, null) { false })
        assertTrue(configPageMayUseBridge(document.expectedUrl, "https://final.example", true, "https://final.example/save"))
        assertTrue(configPageMayRestoreStorage(configPageOrigin(document.expectedUrl), "https://final.example/save", true))
        assertFalse(configPageMayComplete(document.expectedUrl, "https://initial.example/settings", true, null) { false })
    }
    @Test fun legacySaveAllowsTopFrameNavigationButRejectsRedirectsAndForeignDocuments() {
        val page = "https://final.example/settings"
        assertTrue(configPageMayNavigateClose(page, page, true, false, false))
        assertFalse(configPageMayNavigateClose(page, page, false, false, false))
        assertFalse(configPageMayNavigateClose(page, page, true, true, false))
        assertFalse(configPageMayNavigateClose(page, "https://iframe.example", true, false, false))
        assertTrue(configPageMayNavigateClose(page, "https://login.example", true, false, true))
        assertFalse(configPageMayNavigateClose(page, page, false, false, true))
        val data = "data:text/html,Save"
        assertTrue(configPageMayNavigateClose(data, data, true, false, false))
        assertTrue("frame-src 'none'" in configPageCsp(null, page))
    }
}
