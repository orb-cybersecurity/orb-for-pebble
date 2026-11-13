package coredevices.pebble.services

import io.rebble.libpebblecommon.services.WatchInfo

/**
 * Orb: Core's Memfault client without its chunk upload, which Orb removes along with the rest
 * of Core's telemetry. Only the serial helper is left, because the firmware update check still
 * identifies the watch with it.
 */
class Memfault private constructor() {
    companion object {
        private fun WatchInfo.partialMacAddress(): String = btAddress
            .split(":")
            // Backwards compatibility to before we fixed the mac address value
            .reversed()
            .joinToString("").take(8)

        fun WatchInfo.serialForMemfault(): String = when (serial) {
            // Hack for prototype watches which all have the same serial: use BT MAC to disambiguate
            "XXXXXXXXXXXX" -> "XXXX${partialMacAddress()}"
            else -> serial
        }
    }
}
