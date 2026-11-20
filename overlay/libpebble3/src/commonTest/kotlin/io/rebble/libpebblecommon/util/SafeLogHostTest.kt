package io.rebble.libpebblecommon.util

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

class SafeLogHostTest {
    @Test fun hostLogsExcludeCredentialsAndEveryPartOfThePayload() {
        val host = safeLogHost("https://user:password@example.org/boot/secret?access_token=token#state")
        assertEquals("example.org", host)
        for (secret in listOf("user", "password", "secret", "token", "state")) assertFalse(secret in host)
        assertFalse('\n' in safeLogHost("https://bad\nhost.example.org/"))
    }
}
