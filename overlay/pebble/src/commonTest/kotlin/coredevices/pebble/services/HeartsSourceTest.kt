package coredevices.pebble.services

import coredevices.database.AppstoreSource
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HeartsSourceTest {
    @Test fun onlySignedInRebbleGetsASyntheticHeartsCollection() {
        for (url in listOf(PEBBLE_FEED_URL, "https://custom.example/api", "http://old.example/api")) {
            val source = AppstoreSource(url = url, title = "test")
            assertFalse(source.supportsHearts(false))
            assertFalse(source.supportsHearts(true))
        }
        val rebble = AppstoreSource(url = REBBLE_FEED_URL, title = "Rebble")
        assertFalse(rebble.supportsHearts(false))
        assertTrue(rebble.supportsHearts(true))
    }
}
