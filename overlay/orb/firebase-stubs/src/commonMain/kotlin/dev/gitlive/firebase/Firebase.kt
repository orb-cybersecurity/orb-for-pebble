package dev.gitlive.firebase

/**
 * Orb stand-in for the dev.gitlive Firebase KMP artifacts. The declarations in this module
 * share the real library's fully-qualified names, so Core's call sites compile unchanged while
 * no Firebase or Google Play services code is in the build. The approach follows Gravel
 * (github.com/david-cant-code/pebble-app-degoogled).
 *
 * Behaviour: the app is permanently signed out and every remote store is empty.
 */
object Firebase

interface EncodeSettings {
    interface Builder {
        var encodeDefaults: Boolean
    }
}
