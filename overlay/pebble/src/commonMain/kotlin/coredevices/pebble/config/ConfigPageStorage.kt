package coredevices.pebble.config

import kotlinx.serialization.json.Json

/** Native localStorage.length is read-only; snapshot saves need no page-side length update. */
internal val configStorageLengthChanged: (String) -> Unit = { }

internal fun configPageMayRestoreStorage(expectedOrigin: String?, currentUrl: String?, mainFrame: Boolean): Boolean =
    mainFrame && expectedOrigin != null && configPageOrigin(currentUrl.orEmpty()) == expectedOrigin

internal fun configStorageRestoreScript(origin: String, saved: String): String = """
    (function() {
        if (window !== window.top || location.origin !== ${Json.encodeToString(origin)}) return;
        try { window.localStorage.clear(); } catch (e) { return; }
        const localStorageData = JSON.parse(${Json.encodeToString(saved)});
        for (const [key, value] of Object.entries(localStorageData)) {
            window.localStorage.setItem(key, value);
        }
    })();
""".trimIndent()
