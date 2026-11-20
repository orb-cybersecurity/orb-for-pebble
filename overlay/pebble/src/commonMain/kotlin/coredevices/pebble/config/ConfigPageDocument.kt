package coredevices.pebble.config

/** Pin the final URL of the first committed main document, including its initial redirects. */
internal class ConfigPageDocument(private val requestedUrl: String) {
    private var firstUrl: String? = null
    val expectedUrl: String get() = firstUrl ?: requestedUrl

    fun accepts(sourceOrigin: String, mainFrame: Boolean, currentUrl: String?): Boolean {
        // Document-start messages may precede commit-visible, including canonicalized data URLs.
        if (mainFrame && (sourceOrigin == "null" && currentUrl?.startsWith("data:", true) == true ||
            configPageOrigin(currentUrl.orEmpty()) == configPageOrigin(sourceOrigin))) recordInitialLoad(currentUrl)
        return configPageMayUseBridge(expectedUrl, sourceOrigin, mainFrame, currentUrl)
    }

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
