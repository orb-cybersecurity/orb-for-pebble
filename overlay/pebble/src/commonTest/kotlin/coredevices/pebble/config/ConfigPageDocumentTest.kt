package coredevices.pebble.config

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ConfigPageDocumentTest {
    @Test fun earlyOpaqueMessagesPinTheFirstDataDocumentBeforeCommitVisible() {
        val raw = "data:text/html,<p>Réglages</p>\n"
        val canonical = "data:text/html,%3Cp%3ER%C3%A9glages%3C/p%3E%0A"
        val document = ConfigPageDocument(raw)
        assertFalse(document.accepts("null", false, canonical))
        assertEquals(raw, document.expectedUrl)
        assertTrue(document.accepts("null", true, canonical))
        assertEquals(canonical, document.expectedUrl)
        assertFalse(document.accepts("null", true, "data:text/html,other"))
        assertEquals(canonical, document.expectedUrl)
        assertFalse(document.accepts("https://other.example", true, canonical))
    }

    @Test fun opaqueDataMessagesCannotTakeOverAnHttpDocument() {
        val page = "https://config.example/settings"
        val document = ConfigPageDocument(page)
        assertFalse(document.accepts("null", true, "data:text/html,other"))
        assertEquals(page, document.expectedUrl)
        assertTrue(document.accepts("https://config.example", true, page))
        assertFalse(document.accepts("null", true, page))
        assertFalse(document.accepts("https://other.example", true, "https://other.example/"))
    }

    @Test fun firstCommittedDataUrlPinsTheCanonicalFormAndCannotBeReplaced() {
        val raw = "data:text/html,<p>café</p>"
        val canonical = "data:text/html,%3Cp%3Ecaf%C3%A9%3C/p%3E"
        val document = ConfigPageDocument(raw)
        document.recordInitialLoad("about:blank")
        document.recordInitialLoad(canonical)
        document.recordInitialLoad("data:text/html,foreign")
        assertEquals(canonical, document.expectedUrl)
        assertTrue(configPageMayComplete(document.expectedUrl, canonical, true, null) { false })
        assertFalse(configPageMayComplete(document.expectedUrl, raw, true, null) { false })
        assertFalse(configPageMayComplete(document.expectedUrl, "data:text/html,foreign", true, null) { false })
        val https = ConfigPageDocument("https://example.org")
        https.recordInitialLoad(canonical)
        assertEquals("https://example.org", https.expectedUrl)
    }

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
