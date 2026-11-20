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
}
