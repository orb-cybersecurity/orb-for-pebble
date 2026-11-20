package coredevices.pebble.config

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class ConfigPageStorageTest {
    @Test fun snapshotLengthUpdatesDoNotBlockOrDispatchBackToMain() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            var saved = false
            withContext(Dispatchers.Main) {
                configStorageLengthChanged("localStorage.length = 0")
                configStorageLengthChanged("localStorage.length = 1")
                saved = true
            }
            assertTrue(saved)
        } finally {
            Dispatchers.resetMain()
        }
    }

    @Test fun storageRestoresOnlyToTheExpectedMainFrameOrigin() {
        val origin = configPageOrigin("https://config.example.org:443/start")
        assertTrue(configPageMayRestoreStorage(origin, "https://config.example.org/next", true))
        assertFalse(configPageMayRestoreStorage(origin, "https://config.example.org/next", false))
        assertFalse(configPageMayRestoreStorage(origin, "https://other.example.org/", true))
        assertFalse(configPageMayRestoreStorage(origin, "http://config.example.org/", true))
        assertFalse(configPageMayRestoreStorage(origin, "https://config.example.org:444/", true))
        assertFalse(configPageMayRestoreStorage(origin, null, true))
        assertFalse(configPageMayRestoreStorage(null, "data:text/html,settings", true))
        assertFalse(configPageMayRestoreStorage(null, "https://other.example.org/", true))
    }

    @Test fun injectedScriptChecksTheDocumentBeforeAccessingSavedDataOrStorage() {
        val script = configStorageRestoreScript("https://config.example.org", "{\"token\":\"saved-secret\"}")
        val guard = script.indexOf("if (window !== window.top || location.origin !== \"https://config.example.org\") return;")
        assertTrue(guard >= 0)
        assertTrue(guard < script.indexOf("window.localStorage.clear()"))
        assertTrue(guard < script.indexOf("saved-secret"))
    }
}
