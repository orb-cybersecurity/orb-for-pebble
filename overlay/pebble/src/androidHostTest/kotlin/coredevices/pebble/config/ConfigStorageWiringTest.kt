package coredevices.pebble.config

import java.io.File
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ConfigStorageWiringTest {
    @Test fun configAndPkjsUseTheNonBlockingStorageCallbacks() {
        val screen = File("src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt").readText()
        assertTrue("AppContext(context), coredevices.pebble.config.configStorageLengthChanged" in screen)
        val runner = File("../libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt").readText()
        for (source in listOf(screen, runner)) {
            assertFalse(Regex("runBlocking\\s*\\(Dispatchers\\.Main").containsMatchIn(source))
        }
        assertTrue("coredevices.pebble.config.configPageMayRestoreStorage(origin, webView.url, true)" in screen)
        assertTrue("coredevices.pebble.config.configStorageRestoreScript(origin!!, storage.restoreState())" in screen)
    }
}
