package coredevices.pebble.services

import io.ktor.http.URLProtocol
import io.ktor.http.parseUrl

internal fun validSourceUrl(value: String): Boolean {
    val url = parseUrl(value) ?: return false
    return url.protocolOrNull == URLProtocol.HTTPS && url.host.isNotBlank()
}

/** New feeds have paths appended to them; credentials and query/fragment suffixes are refused. */
internal fun validNewSourceUrl(value: String): Boolean {
    val url = parseUrl(value) ?: return false
    return validSourceUrl(value) && url.host.all { it.code in 33..126 } &&
        url.user.isNullOrEmpty() && url.password.isNullOrEmpty() &&
        url.encodedQuery.isEmpty() && url.fragment.isEmpty() && '?' !in value && '#' !in value
}
