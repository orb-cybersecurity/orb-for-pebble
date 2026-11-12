package dev.gitlive.firebase.crashlytics

import dev.gitlive.firebase.Firebase

val Firebase.crashlytics: FirebaseCrashlytics get() = FirebaseCrashlytics

object FirebaseCrashlytics {
    fun log(message: String) {}

    fun recordException(exception: Throwable) {}

    fun setCrashlyticsCollectionEnabled(enabled: Boolean) {}

    fun setUserId(userId: String) {}

    fun setCustomKey(key: String, value: String) {}

    fun setCustomKey(key: String, value: Boolean) {}

    fun setCustomKey(key: String, value: Int) {}

    fun setCustomKey(key: String, value: Long) {}

    fun setCustomKey(key: String, value: Float) {}

    fun setCustomKey(key: String, value: Double) {}
}
