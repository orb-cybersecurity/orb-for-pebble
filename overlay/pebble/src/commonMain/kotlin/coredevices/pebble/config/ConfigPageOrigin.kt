package coredevices.pebble.config

import io.ktor.http.Url

internal fun configPageOrigin(raw: String): String? = runCatching {
    val url = Url(raw)
    if (url.protocol.name !in setOf("https", "http")) return null
    val port = if (url.port == url.protocol.defaultPort) "" else ":${url.port}"
    "${url.protocol.name}://${url.host.lowercase()}$port"
}.getOrNull()

internal fun configPageMayUseBridge(expectedUrl: String, sourceOrigin: String, mainFrame: Boolean, currentUrl: String?): Boolean {
    if (!mainFrame) return false
    val expected = configPageOrigin(expectedUrl)
    return if (expected != null) expected == configPageOrigin(sourceOrigin)
    else expectedUrl.startsWith("data:") && sourceOrigin == "null" && currentUrl == expectedUrl
}
