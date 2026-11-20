package coredevices.pebble.config

/** A bound callback may return from an authentication redirect; legacy closes stay on-origin. */
internal fun configPageMayComplete(
    expectedUrl: String,
    currentUrl: String?,
    mainFrame: Boolean,
    state: String?,
    consumeState: (String) -> Boolean,
): Boolean {
    if (!mainFrame) return false
    if (state != null) return consumeState(state)
    val origin = configPageOrigin(expectedUrl)
    return if (origin != null) configPageOrigin(currentUrl.orEmpty()) == origin
    else expectedUrl.startsWith("data:") && currentUrl == expectedUrl
}
