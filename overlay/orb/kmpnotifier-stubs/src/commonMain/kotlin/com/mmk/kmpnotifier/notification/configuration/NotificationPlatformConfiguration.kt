package com.mmk.kmpnotifier.notification.configuration

sealed interface NotificationPlatformConfiguration {
    class Android(
        val notificationIconResId: Int,
        val notificationIconColorResId: Int? = null,
        val notificationChannelData: NotificationChannelData = NotificationChannelData(),
        val showPushNotification: Boolean = true,
    ) : NotificationPlatformConfiguration {
        class NotificationChannelData(
            val id: String = "DEFAULT_NOTIFICATION_CHANNEL_ID",
            val name: String = "General",
            val description: String = "",
            val soundUri: String? = null,
        )
    }

    class Ios(
        val showPushNotification: Boolean = true,
        val askNotificationPermissionOnStart: Boolean = true,
    ) : NotificationPlatformConfiguration
}
