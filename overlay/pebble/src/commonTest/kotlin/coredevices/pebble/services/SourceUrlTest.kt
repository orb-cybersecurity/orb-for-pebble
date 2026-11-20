package coredevices.pebble.services

import com.eygraber.uri.Uri
import coredevices.pebble.RealPebbleDeepLinkHandler
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SourceUrlTest {
    private val rejectedNew = listOf("http://example.org/api", "HTTP://example.org/api", "file:///api",
        "https:///", "not a url", "https://example.org/api?key=value", "https://example.org/api#fragment",
        "https://user:password@example.org/api", "https://user@example.org/api", "https://例え.org/api",
        "https://bad host/api", "https://example.org/api?", "https://example.org/api#")

    @Test fun storedHttpsSourcesKeepTheirCompatibilityPolicy() {
        for (url in listOf("https://example.org/api", "https://example.org/api?key=value",
            "https://example.org/api#fragment", "https://user:password@example.org/api")) {
            assertTrue(validSourceUrl(url), url)
        }
        for (url in rejectedNew.take(5)) assertFalse(validSourceUrl(url), url)
    }

    @Test fun sourceDialogPolicyRejectsCleartextAndInvalidFeedUrls() {
        assertTrue(validNewSourceUrl("https://example.org/api"))
        assertTrue(validNewSourceUrl("https://example.org:8443/api"))
        for (url in rejectedNew) assertFalse(validNewSourceUrl(url), url)
    }

    @Test fun sourceDeepLinkRejectsInvalidFeedsBeforeOfferingAnAddDialog() {
        fun link(url: String) = Uri.parse("pebble://add-store-feed/Test/" + Uri.encode(url))
        for (url in rejectedNew) assertNull(RealPebbleDeepLinkHandler.parseAddStoreFeedFrom(link(url)), url)
        assertNotNull(RealPebbleDeepLinkHandler.parseAddStoreFeedFrom(link("https://example.org/api")))
    }
}
