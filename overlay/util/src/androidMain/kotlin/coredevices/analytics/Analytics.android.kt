package coredevices.analytics

import PlatformContext

// Orb: no analytics backend.
fun createAndroidAnalytics(platformContext: PlatformContext): AnalyticsBackend = AndroidAnalyticsBackend()

class AndroidAnalyticsBackend : AnalyticsBackend {
    override fun logEvent(name: String, parameters: Map<String, Any>?) {}

    override fun addGlobalProperty(name: String, value: String?) {}

    override fun setEnabled(enabled: Boolean) {}
}
