package io.rebble.libpebblecommon.js

import io.ktor.http.Url

/** PKJS browser resources are bundled assets. Network traffic uses the native proxy. */
internal fun pkjsAssetUrlAllowed(raw: String?): Boolean = runCatching {
    val url = Url(raw ?: return false)
    url.protocol.name == "file" && url.host.isEmpty() && url.encodedPath.startsWith("/android_asset/") &&
        url.encodedPath.split('/').none { it == ".." || '%' in it || '\\' in it }
}.getOrDefault(false)

/** Some WebViews also intercept local image schemes. CSP keeps these out of script-src. */
internal fun pkjsResourceUrlAllowed(raw: String?): Boolean =
    raw?.startsWith("data:", ignoreCase = true) == true ||
        raw?.startsWith("blob:", ignoreCase = true) == true || pkjsAssetUrlAllowed(raw)
