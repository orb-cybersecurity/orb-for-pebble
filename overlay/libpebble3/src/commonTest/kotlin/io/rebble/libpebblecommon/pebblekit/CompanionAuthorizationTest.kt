package io.rebble.libpebblecommon.pebblekit

import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CompanionAuthorizationTest {
    @Test fun everyControlRequiresBothAssociationAndGrant() = runTest {
        assertFalse(authorizedCompanion(emptyList(), listOf("companion")) { true })
        assertFalse(authorizedCompanion(listOf("other"), listOf("companion")) { error("must not ask") })
        assertFalse(authorizedCompanion(listOf("companion"), emptyList()) { true })
        assertFalse(authorizedCompanion(listOf("companion"), listOf("companion")) { false })
        assertTrue(authorizedCompanion(listOf("companion"), listOf("companion")) { true })
    }
}

class PersistedCompanionAuthorizationTest {
    private val app = kotlin.uuid.Uuid.random()
    private fun row(key: String, declared: Boolean = true, granted: Boolean? = true) =
        io.rebble.libpebblecommon.database.entity.LockerAppPermission(app, key, granted, 0, declared = declared)

    @Test fun storedDeclarationsAuthorizeWithNoPbwPresent() = runTest {
        val packages = recordedCompanionPackages(listOf(row("PebbleKit2/companion", declared = false)))
        assertTrue(authorizedCompanion(listOf("companion"), packages) { true })
        assertFalse(authorizedCompanion(listOf("companion"), packages) { false })
        assertFalse(authorizedCompanion(listOf("unrelated"), packages) { error("must not request") })
    }

    @Test fun missingAssociationsAndOtherPermissionRowsFailClosed() = runTest {
        val packages = recordedCompanionPackages(listOf(
            row("Notifications/companion"), row("PebbleKit2/"), row("Internet/example.org"),
        ))
        assertTrue(packages.isEmpty())
        assertFalse(authorizedCompanion(listOf("companion"), packages) { true })
    }

    @Test fun unauthorizedControlAndSendDataCannotEnumerateWatchSerials() = runTest {
        for (operation in listOf("START_APP", "STOP_APP", "SEND_DATA")) {
            val denied = companionResults<String, String>(false) { error("$operation enumerated serials") }
            assertTrue(denied.isEmpty())
        }
        val allowed = companionResults(true) { mapOf("watch-serial" to "success") }
        assertTrue(allowed.containsKey("watch-serial"))
    }
}
