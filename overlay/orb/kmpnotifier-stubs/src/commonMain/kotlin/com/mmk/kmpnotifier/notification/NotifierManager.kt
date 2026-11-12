package com.mmk.kmpnotifier.notification

import com.mmk.kmpnotifier.notification.configuration.NotificationPlatformConfiguration

/**
 * Orb stand-in for io.github.mirzemehdi:kmpnotifier, which wraps Firebase Cloud Messaging.
 * Push never registers and never delivers; listeners are accepted and never called.
 */
typealias PayloadData = Map<String, *>

object NotifierManager {
    interface Listener {
        fun onNewToken(token: String) {}
        fun onPushNotification(title: String?, body: String?) {}
        fun onPushNotificationWithPayloadData(title: String?, body: String?, data: PayloadData) {}
        fun onPayloadData(data: PayloadData) {}
        fun onNotificationClicked(data: PayloadData) {}
    }

    fun initialize(configuration: NotificationPlatformConfiguration) {}

    fun addListener(listener: Listener) {}

    fun setLogger(logger: (String) -> Unit) {}

    fun getLocalNotifier(): Notifier = InertNotifier

    fun getPushNotifier(): PushNotifier = InertPushNotifier
}

interface Notifier {
    fun notify(title: String, body: String, payloadData: Map<String, String> = emptyMap()): Int
    fun notify(id: Int, title: String, body: String, payloadData: Map<String, String> = emptyMap())
    fun notify(block: NotifierBuilder.() -> Unit)
    fun remove(id: Int)
    fun removeAll()
}

class NotifierBuilder {
    var id: Int = 0
    var title: String = ""
    var body: String = ""
    var payloadData: Map<String, String> = emptyMap()
}

interface PushNotifier {
    suspend fun getToken(): String?
    suspend fun deleteMyToken()
    suspend fun subscribeToTopic(topic: String)
    suspend fun unSubscribeFromTopic(topic: String)
}

private object InertNotifier : Notifier {
    override fun notify(title: String, body: String, payloadData: Map<String, String>): Int = 0
    override fun notify(id: Int, title: String, body: String, payloadData: Map<String, String>) {}
    override fun notify(block: NotifierBuilder.() -> Unit) {}
    override fun remove(id: Int) {}
    override fun removeAll() {}
}

private object InertPushNotifier : PushNotifier {
    override suspend fun getToken(): String? = null
    override suspend fun deleteMyToken() {}
    override suspend fun subscribeToTopic(topic: String) {}
    override suspend fun unSubscribeFromTopic(topic: String) {}
}
