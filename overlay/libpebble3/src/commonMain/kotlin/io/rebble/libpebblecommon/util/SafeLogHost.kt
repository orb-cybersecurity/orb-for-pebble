package io.rebble.libpebblecommon.util

import io.ktor.http.Url

/** Log only an ASCII host, never credentials, paths, queries, fragments or control characters. */
fun safeLogHost(raw: String): String = runCatching {
    Url(raw).host.takeIf { Regex("[A-Za-z0-9.-]{1,253}").matches(it) }.orEmpty()
}.getOrDefault("")
