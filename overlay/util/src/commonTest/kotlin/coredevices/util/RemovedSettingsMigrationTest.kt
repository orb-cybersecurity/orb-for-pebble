package coredevices.util

import com.russhwolf.settings.MapSettings
import coredevices.util.models.CactusSTTMode
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

class RemovedSettingsMigrationTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test fun removedFieldsDoNotResetSavedPreferencesOrSpeechModes() {
        for (mode in CactusSTTMode.entries) {
            val settings = MapSettings()
            settings.putString("coreapp.config", """{
                "fetchWeather":false,"showAppUpdatedBadge":false,"preferHealthTab":false,
                "sttConfig":{"mode":"$mode","modelName":"old-model","spokenLanguage":"es"}
            }""")
            val holder = CoreConfigHolder(CoreConfig(), settings, json)
            val config = holder.config.value
            assertFalse(config.fetchWeather)
            assertFalse(config.preferHealthTab)
            assertEquals(mode, config.sttConfig.mode)
            assertEquals("es", config.sttConfig.spokenLanguage)
            holder.update(config)
            val saved = settings.getString("coreapp.config", "")
            assertFalse("showAppUpdatedBadge" in saved)
            assertFalse("modelName" in saved)
        }
    }

    @Test fun oldNumericSpeechModeStillMigratesWithoutTheObsoleteModel() {
        val settings = MapSettings()
        settings.putString("coreapp.config", """{"fetchWeather":false}""")
        settings.putInt("cactus_mode", CactusSTTMode.RebbleFallback.id)
        settings.putString("cactus_stt_model", "old-model")
        val config = CoreConfigHolder(CoreConfig(), settings, json).config.value
        assertEquals(CactusSTTMode.RebbleFallback, config.sttConfig.mode)
        assertFalse(config.fetchWeather)
        assertFalse(settings.hasKey("cactus_mode"))
        assertFalse(settings.hasKey("cactus_stt_model"))
    }
}
