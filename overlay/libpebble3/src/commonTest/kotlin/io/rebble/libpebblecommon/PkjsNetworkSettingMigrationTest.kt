package io.rebble.libpebblecommon

import com.russhwolf.settings.MapSettings
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PkjsNetworkSettingMigrationTest {
    @Test fun bothOldToggleValuesAreRemovedImmediatelyWithoutLosingPreferences() {
        for (old in listOf(false, true)) {
            val settings = MapSettings()
            settings.putString("libpebble.settings", """{
                "watchConfig":{"pkjsRequestsThroughApp":$old,"calendarPins":false,"pkjsInspectable":true},
                "notificationConfig":{}
            }""")
            // Strict decoding proves migration doesn't rely on ignoreUnknownKeys.
            val holder = LibPebbleConfigHolder(LibPebbleConfig(), settings, Json)
            assertFalse(holder.config.value.watchConfig.calendarPins)
            assertTrue(holder.config.value.watchConfig.pkjsInspectable)
            assertFalse("pkjsRequestsThroughApp" in settings.getString("libpebble.settings", ""))
            assertEquals(holder.config.value, LibPebbleConfigHolder(LibPebbleConfig(), settings, Json).config.value)
        }
    }

    @Test fun retiredCompanionSettingIsRemovedWithStrictAndLenientDecoders() {
        for (decoder in listOf(Json, Json { ignoreUnknownKeys = true })) {
            for (old in listOf(false, true)) {
                val settings = MapSettings()
                settings.putString("libpebble.settings", """{
                    "watchConfig":{"enableLegacyPebbleKit":$old,"calendarPins":false,"pkjsInspectable":true},
                    "notificationConfig":{"sendNotifications":false},
                    "bleConfig":{"autoConnectAfterFailure":false}
                }""")
                val holder = LibPebbleConfigHolder(LibPebbleConfig(), settings, decoder)
                assertFalse(holder.config.value.watchConfig.calendarPins)
                assertTrue(holder.config.value.watchConfig.pkjsInspectable)
                assertFalse(holder.config.value.notificationConfig.sendNotifications)
                assertFalse(holder.config.value.bleConfig.autoConnectAfterFailure)
                assertFalse("enableLegacyPebbleKit" in settings.getString("libpebble.settings", ""))
                assertEquals(holder.config.value, LibPebbleConfigHolder(LibPebbleConfig(), settings, Json).config.value)
            }
        }
    }
}
