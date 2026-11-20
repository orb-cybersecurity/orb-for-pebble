package coredevices.pebble.services

import com.eygraber.uri.Uri
import coredevices.pebble.RealPebbleDeepLinkHandler
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SourceUrlTest {
    @Test fun sourceDialogPolicyRejectsCleartextAndInvalidFeedUrls() {
        assertTrue(validSourceUrl("https://example.org/api"))
        for (url in listOf("http://example.org/api", "HTTP://example.org/api", "file:///api",
            "https://example.org/api?key=value", "https://example.org/api#fragment",
            "https://user:password@example.org/api", "not a url")) {
            assertFalse(validSourceUrl(url), url)
        }
    }

    @Test fun sourceDeepLinkRejectsHttpBeforeOfferingAnAddDialog() {
        fun link(url: String) = Uri.parse("pebble://add-store-feed/Test/" + Uri.encode(url))
        assertNull(RealPebbleDeepLinkHandler.parseAddStoreFeedFrom(link("http://example.org/api")))
        assertNotNull(RealPebbleDeepLinkHandler.parseAddStoreFeedFrom(link("https://example.org/api")))
    }
}
