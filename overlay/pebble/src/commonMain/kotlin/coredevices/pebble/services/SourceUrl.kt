package coredevices.pebble.services

import io.ktor.http.URLProtocol
import io.ktor.http.parseUrl

internal fun validSourceUrl(value: String): Boolean {
    val url = parseUrl(value) ?: return false
    return url.protocolOrNull == URLProtocol.HTTPS && url.host.isNotBlank()
}
