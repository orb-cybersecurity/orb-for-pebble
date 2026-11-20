package coredevices.pebble.ui

import com.multiplatform.webview.request.WebRequest
import com.multiplatform.webview.request.WebRequestInterceptResult
import com.multiplatform.webview.web.WebViewNavigator
import coredevices.pebble.config.configPageMayComplete
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SettingsRequestInterceptorTest {
    @Test fun rejectedFramesOriginsAndStatesCannotCompleteOrCloseTheScreen() = runBlocking {
        val expected = "https://config.example.org/settings"
        var current = "https://other.example.org/settings"
        var pending: String? = "bound-state"
        var policyCalls = 0
        val completed = CompletableDeferred<String>()
        val errors = CompletableDeferred<Unit>()
        val interceptor = SettingsRequestInterceptor(
            mayClose = { callback ->
                policyCalls++
                configPageMayComplete(expected, current, true, callback.state) {
                    (pending == it).also { accepted -> if (accepted) pending = null }
                }
            },
            openStoreAppLink = { false },
            onSuccess = { completed.complete(it) },
            onError = { errors.complete(Unit) },
        )
        val navigator = WebViewNavigator(this)
        fun intercept(url: String, main: Boolean = true) = interceptor.onInterceptUrlRequest(
            WebRequest(url, mutableMapOf(), main, false, "GET"), navigator,
        )
        assertEquals(WebRequestInterceptResult.Reject, intercept("pebblejs://close?orb_state=bound-state#injected", false))
        assertEquals(0, policyCalls)
        assertEquals(WebRequestInterceptResult.Reject, intercept("pebblejs://close#wrong-origin"))
        assertEquals(WebRequestInterceptResult.Reject, intercept("pebblejs://close?orb_state=wrong#wrong-state"))
        assertEquals(WebRequestInterceptResult.Reject, intercept("pebblejs://close?orb_state=bound-state&orb_state=wrong#ambiguous"))
        assertFalse(completed.isCompleted)
        assertFalse(errors.isCompleted)
        assertEquals("bound-state", pending)
        assertEquals(WebRequestInterceptResult.Reject, intercept("pebblejs://close?orb_state=bound-state#%7B%22ok%22%3Atrue%7D"))
        assertEquals("{\"ok\":true}", withTimeout(2000) { completed.await() })
        assertEquals(null, pending)
        assertFalse(errors.isCompleted)
    }

    @Test fun legacyQueryPayloadsStillReachTheOwningPage() = runBlocking {
        val completed = CompletableDeferred<String>()
        val interceptor = SettingsRequestInterceptor(
            mayClose = { true }, openStoreAppLink = { false },
            onSuccess = { completed.complete(it) }, onError = { error("Valid legacy callback") },
        )
        interceptor.onInterceptUrlRequest(
            WebRequest("pebblejs://close?%7B%22ok%22%3Atrue%7D", mutableMapOf(), true, false, "GET"),
            WebViewNavigator(this),
        )
        assertTrue(withTimeout(2000) { completed.await() }.contains("\"ok\":true"))
    }
}
