package io.rebble.libpebblecommon.js

import io.rebble.libpebblecommon.util.safeLogHost

internal enum class PkjsNetworkLogCategory {
    REFUSED, REDIRECT_REFUSED, TIMED_OUT, FAILED, HEADERS_FAILED, CHARSET_INVALID,
    RESPONSE_TYPE_INVALID, BODY_FAILED, PAGE_FAILED,
}

/** No URL-bearing reason, response text, exception message or throwable enters these logs. */
internal fun pkjsNetworkLog(category: PkjsNetworkLogCategory, url: String): String =
    "PKJS ${category.name} host=${safeLogHost(url)}"
