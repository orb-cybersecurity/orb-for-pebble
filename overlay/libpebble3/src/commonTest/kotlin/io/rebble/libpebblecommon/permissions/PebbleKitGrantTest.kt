package io.rebble.libpebblecommon.permissions

import io.rebble.libpebblecommon.pebblekit.authorizedCompanion
import io.rebble.libpebblecommon.pebblekit.recordedCompanionPackages
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PebbleKitGrantTest {
    @Test fun aStoredAssociationAloneDoesNotGrantProviderAccess() = runTest {
        val dao = FakePermissionDao()
        val p = permissions(dao)
        val key = pebbleKit2Key("companion")
        suspend fun allowed(): Boolean = authorizedCompanion(
            listOf("companion"), recordedCompanionPackages(dao.getByAppUuid(APP)),
        ) { pkg -> p.check(APP, pebbleKit2Key(pkg)) == PermissionDecision.Granted }
        assertFalse(allowed())
        p.setDecisions(APP, mapOf(key to false))
        assertFalse(allowed())
        p.setDecisions(APP, mapOf(key to true))
        assertTrue(allowed())
        p.setDecisions(APP, mapOf(key to false))
        assertFalse(allowed())
    }
}
