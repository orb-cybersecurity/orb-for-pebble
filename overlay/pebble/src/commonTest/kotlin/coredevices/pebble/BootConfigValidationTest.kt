package coredevices.pebble

import coredevices.pebble.RealPebbleDeepLinkHandler.Companion.parseBootConfigFrom
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class BootConfigValidationTest {
    @Test
    fun rejectsAmbiguousOrUnencryptedServers() {
        for (server in listOf(
            "http://boot.rebble.io",
            "https://boot.rebble.io@other.example",
            "https://user:password@boot.rebble.io",
            "https://%62oot.rebble.io",
            "https://bóot.rebble.io",
            "https://[::1]",
        )) {
            assertNull(parseBootConfigFrom("/$server/boot?access_token=abc&t=1"), server)
        }
    }

    @Test
    fun displaysTheExplicitPortOfTheAcceptedServer() {
        val path = "/https://boot.rebble.io:8443/boot?access_token=abc&t=1"
        assertEquals(
            PendingBootConfig(bootUrl = path, token = "abc", host = "boot.rebble.io:8443"),
            parseBootConfigFrom(path),
        )
    }
}
