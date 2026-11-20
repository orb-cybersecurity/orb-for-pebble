package coredevices.coreapp.ui.navigation

import com.eygraber.uri.Uri
import kotlin.test.Test
import kotlin.test.assertNull

// handle() itself isn't exercised here because its fallback path constructs a
// NavUri (android.net.Uri on Android), which isn't available in JVM unit tests.
class CoreDeepLinkHandlerTest {
    private val handler = CoreDeepLinkHandler()

    private fun routeFor(uri: String) = handler.routeFor(Uri.parse(uri))

    @Test
    fun removedSpeechModelDeepLinkDoesNotParse() {
        assertNull(routeFor("pebblecore://deep-link/speech-model"))
    }

    // Orb has no Index 01 ring; links to its screens open nothing.
    @Test
    fun indexDeepLinksDoNotParse() {
        assertNull(routeFor("pebblecore://deep-link/recording?id=123"))
        assertNull(routeFor("pebblecore://deep-link/object?id=firestore-doc-1"))
        assertNull(routeFor("pebblecore://deep-link/index-settings"))
        assertNull(routeFor("pebblecore://deep-link/timers-alarms"))
    }

    @Test
    fun wrongSchemeHostOrPathDoesNotParse() {
        assertNull(routeFor("pebble://deep-link/speech-model"))
        assertNull(routeFor("pebblecore://other/speech-model"))
        assertNull(routeFor("pebblecore://deep-link/unknown"))
        assertNull(routeFor("pebblecore://deep-link/view-bug-report?conversationId=1"))
    }
}
