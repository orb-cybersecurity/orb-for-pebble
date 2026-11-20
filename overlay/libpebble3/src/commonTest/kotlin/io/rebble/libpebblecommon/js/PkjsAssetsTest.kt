package io.rebble.libpebblecommon.js

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PkjsAssetsTest {
    @Test fun onlyOwnBundledAssetsReachTheBrowserLoader() {
        for (file in listOf("webview_startup.html", "startup.js", "realm_guard.js"))
            assertTrue(pkjsAssetUrlAllowed("file:///android_asset/$file"))
        for (url in listOf(null, "https://allowed.example/redirect", "http://192.168.1.1/", "file:///private/token",
            "file://remote/android_asset/startup.js", "content://provider/token", "data:text/javascript,code",
            "file:///android_asset/../private/token", "file:///android_asset/%2e%2e/token", "file:///android_asset_other/startup.js"))
            assertFalse(pkjsAssetUrlAllowed(url), "$url")
    }
}
