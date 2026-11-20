package io.rebble.libpebblecommon.permissions

import io.rebble.libpebblecommon.plugin.PluginPermission
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RemovedPermissionsTest {
    @Test fun removedNamesStillParseButHaveNoDefinitionOrAuthority() {
        for (name in listOf("SetIndexAlarms", "SendMessagesBeeper", "WriteIndexNotes", "WriteIndexReminders")) {
            val permission = Json.decodeFromString<PluginPermission>("\"$name\"")
            assertEquals(name, permission.name)
            assertNull(PermissionRegistry[name])
            assertNull(permissionKind(name, emptyMap()))
        }
    }
}

class CompanionDeclarationLifecycleTest {
    @Test fun anUpdateRemovesObsoleteCompanionsButPreservesUnrelatedPermissions() = kotlinx.coroutines.test.runTest {
        val dao = FakePermissionDao()
        val permissions = permissions(dao)
        permissions.recordRequested(APP, RequestedPermissions(null, false, pebbleKit2Packages = listOf("old.companion")))
        permissions.setDecisions(APP, mapOf(pebbleKit2Key("old.companion") to true))
        permissions.recordRequested(APP, listOf("Calendar"))
        permissions.recordRequested(APP, RequestedPermissions(null, false, pebbleKit2Packages = listOf("new.companion")))
        val keys = dao.getByAppUuid(APP).map { it.permission }
        kotlin.test.assertFalse(pebbleKit2Key("old.companion") in keys)
        kotlin.test.assertTrue(pebbleKit2Key("new.companion") in keys)
        kotlin.test.assertTrue("Calendar" in keys)
    }
}
