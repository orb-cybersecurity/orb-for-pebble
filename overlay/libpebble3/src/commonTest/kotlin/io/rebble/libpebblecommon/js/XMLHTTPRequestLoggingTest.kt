package io.rebble.libpebblecommon.js

import co.touchlab.kermit.Logger
import co.touchlab.kermit.LogWriter
import co.touchlab.kermit.Severity
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.ByteChannel
import io.rebble.libpebblecommon.permissions.DataUsageRecorder
import io.rebble.libpebblecommon.permissions.NetworkAccess
import io.rebble.libpebblecommon.plugin.PluginNetworkVerdict
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import kotlinx.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class XMLHTTPRequestLoggingTest {
    private val url = "https://user:password@api.example.org/private?key=secret#payload"

    @Test fun sanitizerRetainsOnlyTheHostAndFixedCategory() {
        for (category in PkjsNetworkLogCategory.entries) {
            assertEquals("PKJS ${category.name} host=api.example.org", pkjsNetworkLog(category, url))
            val invalid = pkjsNetworkLog(category, "https://bad\nhost/?key=secret")
            assertFalse('\n' in invalid)
            assertFalse("secret" in invalid)
        }
    }

    @Test fun refusedRedirectedFailedAndTimedOutRequestsNeverLogSecretsOrThrowables() = runTest {
        val oldWriters = Logger.config.logWriterList
        val oldSeverity = Logger.config.minSeverity
        val messages = mutableListOf<String>()
        val throwables = mutableListOf<Throwable?>()
        Logger.setLogWriters(object : LogWriter() {
            override fun log(severity: Severity, message: String, tag: String, throwable: Throwable?) {
                if (tag == "XMLHTTPRequestManager") {
                    messages += message
                    throwables += throwable
                }
            }
        })
        Logger.setMinSeverity(Severity.Verbose)
        try {
            val recorder = DataUsageRecorder { _, _, _, _, _ -> }
            for ((mode, category) in listOf(
                "refuse" to PkjsNetworkLogCategory.REFUSED,
                "refuse-relative" to PkjsNetworkLogCategory.REFUSED,
                "redirect" to PkjsNetworkLogCategory.REDIRECT_REFUSED,
                "fail" to PkjsNetworkLogCategory.FAILED,
                "timeout" to PkjsNetworkLogCategory.TIMED_OUT,
                // Ktor buffers the response before returning it, so this fails during request().
                "body" to PkjsNetworkLogCategory.FAILED,
            )) {
                messages.clear()
                throwables.clear()
                val requestUrl = if (mode == "refuse-relative") "//api.example.org/private?key=secret" else url
                val access = NetworkAccess { target, _ ->
                    if (mode.startsWith("refuse") || target.contains("redirect.example.org")) PluginNetworkVerdict.Denied("Refused $target secret")
                    else PluginNetworkVerdict.Allowed
                }
                val client = HttpClient(MockEngine {
                    when (mode) {
                        "refuse", "refuse-relative" -> error("Refused requests must not reach the engine")
                        "redirect" -> respond("", HttpStatusCode.Found, headersOf("Location", "https://redirect.example.org/private?key=secret"))
                        "timeout" -> withTimeout(1) { delay(100); respond("unreachable") }
                        "body" -> respond(ByteChannel().apply { cancel(IOException("Body failed $url secret")) })
                        else -> throw IOException("Request failed $url secret")
                    }
                })
                val manager = XMLHTTPRequestManager(this, {}, HttpInterceptorManager(emptyList(), recorder),
                    Uuid.parse("00000000-0000-0000-0000-00000000b007"), client, access, recorder)
                try {
                    manager.dispatch("getXHRInstanceID", emptyList())
                    manager.dispatch("open", listOf(1.0, "GET", requestUrl, false, "", ""))
                    manager.dispatch("send", listOf(1.0, "", null, false))
                    assertTrue(pkjsNetworkLog(category, requestUrl) in messages, "$mode: $messages")
                    for (message in messages) {
                        for (secret in listOf("user", "password", "private", "key=", "secret", "payload")) {
                            assertFalse(secret in message, "$mode leaked $secret")
                        }
                    }
                    throwables.forEach { assertNull(it, "$mode retained a throwable") }
                } finally {
                    manager.close()
                    client.close()
                }
            }
        } finally {
            Logger.setLogWriters(oldWriters)
            Logger.setMinSeverity(oldSeverity)
        }
    }
}
