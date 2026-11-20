package io.rebble.libpebblecommon.web

import io.ktor.http.Url

const val MAX_FIRMWARE_BYTES = 32L * 1024 * 1024
private val assetHosts = setOf("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
fun firmwareDownloadUrlAllowed(raw: String, github: Boolean): Boolean = runCatching {
    val url = Url(raw)
    url.protocol.name == "https" && url.user.isNullOrEmpty() && url.password.isNullOrEmpty() &&
        (!github || url.host.lowercase() in assetHosts)
}.getOrDefault(false)
