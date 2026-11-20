package coredevices.pebble.config

/** Pin the final URL of the first committed main document, including its initial redirects. */
internal class ConfigPageDocument(private val requestedUrl: String) {
    private var firstUrl: String? = null
    val expectedUrl: String get() = firstUrl ?: requestedUrl

    fun recordInitialLoad(url: String?) {
        if (firstUrl == null && url != null &&
            (configPageOrigin(url) != null || requestedUrl.startsWith("data:", true) && url.startsWith("data:", true))) firstUrl = url
    }
}

internal fun configPageMayNavigateClose(
    expectedUrl: String,
    currentUrl: String?,
    mainFrame: Boolean,
    redirect: Boolean,
    hasState: Boolean,
): Boolean = mainFrame && (hasState || (!redirect &&
    configPageMayComplete(expectedUrl, currentUrl, true, null) { false }))
