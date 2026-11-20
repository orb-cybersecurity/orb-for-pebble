package io.rebble.libpebblecommon.web

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FirmwareDownloadPolicyTest {
    @Test fun githubAssetsRequireHttpsAndAnExactAllowedHost() {
        for (host in listOf("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")) {
            assertTrue(firmwareDownloadUrlAllowed("https://$host/release.pbz", true))
        }
        for (url in listOf("http://github.com/a.pbz", "https://github.com.evil.example/a.pbz",
            "https://github.com@evil.example/a.pbz", "https://evil.example/a.pbz", "file:///a.pbz")) {
            assertFalse(firmwareDownloadUrlAllowed(url, true), url)
        }
        assertTrue(firmwareDownloadUrlAllowed("https://binaries.rebble.io/a.pbz", false))
        assertFalse(firmwareDownloadUrlAllowed("http://binaries.rebble.io/a.pbz", false))
    }
}
