package io.rebble.libpebblecommon.js

import io.ktor.http.URLBuilder
import io.ktor.http.Url
import io.ktor.http.encodeURLParameter
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ConfigCloseUrlTest {
    @Test fun legacySeparatorsAndEncodedPayloadsArePreserved() {
        val payload = """{"value":"a+b %25 & # /?"}"""
        for (separator in listOf("#", "?", "/?", "/", "/#")) {
            val url = "pebblejs://close$separator${payload.encodeURLParameter()}"
            assertEquals(ConfigCloseCallback(payload, null), parseConfigCloseUrl(url), separator)
            assertEquals(ConfigCloseCallback(payload, null), parseConfigCloseUrl(url.encodeURLParameter()), separator)
        }
        assertEquals(ConfigCloseCallback("a+b", null), parseConfigCloseUrl("pebblejs://close#a+b"))
        assertEquals(ConfigCloseCallback("%25", null), parseConfigCloseUrl("pebblejs://close#%2525"))
        assertEquals(ConfigCloseCallback("{\"enabled\":true}", null), parseConfigCloseUrl("pebblejs://close#{\"enabled\":true}"))
    }

    @Test fun stateAndPayloadAreSeparateAndStateIsSingleValued() {
        val callback = ConfigCloseCallback("{\"enabled\":true}", "bound-state")
        for (url in listOf(
            "pebblejs://close?orb_state=bound-state#%7B%22enabled%22%3Atrue%7D",
            "pebblejs://close/?orb_state=bound-state#%7B%22enabled%22%3Atrue%7D",
            "pebblejs://close?other=value&orb_state=bound%2Dstate#%7B%22enabled%22%3Atrue%7D",
        )) assertEquals(callback, parseConfigCloseUrl(url))
        assertNull(parseConfigCloseUrl("pebblejs://close?orb_state=state%7B%7D"))
        assertNull(parseConfigCloseUrl("pebblejs://close?orb_state=#payload"))
        assertNull(parseConfigCloseUrl("pebblejs://close?orb_state=a&orb_state=b#payload"))
    }

    @Test fun documentedReturnToConcatenationRoundTrips() {
        val request = ExternalConfigRequest()
        val state = request.begin()
        val page = URLBuilder("https://config.example.org").apply {
            parameters.append("return_to", "pebblejs://close?orb_state=$state#")
        }.buildString()
        val callback = parseConfigCloseUrl(Url(page).parameters["return_to"]!! + "%7B%22ok%22%3Atrue%7D")!!
        assertEquals("{\"ok\":true}", callback.data)
        assertFalse(request.consume("wrong"))
        assertTrue(request.consume(callback.state))
        assertFalse(request.consume(callback.state))
    }

    @Test fun lookalikeAuthoritiesCannotClose() {
        for (url in listOf("https://close#payload", "pebblejs://close.evil/#payload", "pebblejs://close@evil/#payload", "pebblejs://close:123/#payload")) {
            assertFalse(isConfigCloseUrl(url))
            assertNull(parseConfigCloseUrl(url))
        }
    }
}
