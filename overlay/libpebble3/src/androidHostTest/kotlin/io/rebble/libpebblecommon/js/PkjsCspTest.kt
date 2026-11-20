package io.rebble.libpebblecommon.js

import java.io.File
import java.security.MessageDigest
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PkjsCspTest {
    @Test fun bundledScriptsAndLocalImagesHaveValidSourcesAndNetworkStaysProxied() {
        val html = File("src/androidMain/assets/webview_startup.html").readText()
        val csp = Regex("http-equiv=\"Content-Security-Policy\" content=\"([^\"]+)\"").find(html)!!.groupValues[1]
        val directives = csp.split(';').associate {
            val words = it.trim().split(Regex("\\s+"))
            words.first() to words.drop(1).toSet()
        }
        // This page needs only keyword, hash and scheme sources. A file:///path host-source
        // has an empty host and Chromium ignores it, blocking both startup scripts.
        directives.values.flatten().forEach { source ->
            assertTrue(source.matches(Regex("'[a-z-]+'|'sha256-[A-Za-z0-9+/=]+'|[a-z][a-z0-9+.-]*:")), source)
        }
        assertEquals(setOf("'none'"), directives["default-src"])
        assertEquals(setOf("data:", "blob:"), directives["connect-src"])
        for (directive in listOf("frame-src", "child-src", "worker-src", "object-src"))
            assertEquals(setOf("'none'"), directives[directive])
        assertEquals(setOf("'self'", "file:", "data:", "blob:"), directives["img-src"])
        val onload = Regex("onload=\"([^\"]+)\"").find(html)!!.groupValues[1]
        val hash = Base64.getEncoder().encodeToString(MessageDigest.getInstance("SHA-256").digest(onload.toByteArray()))
        assertEquals(setOf("file:", "'unsafe-eval'", "'unsafe-hashes'", "'sha256-$hash'"), directives["script-src"])
        for (asset in listOf("realm_guard.js", "startup.js"))
            assertTrue("src=\"file:///android_asset/$asset\"" in html)
    }
}
