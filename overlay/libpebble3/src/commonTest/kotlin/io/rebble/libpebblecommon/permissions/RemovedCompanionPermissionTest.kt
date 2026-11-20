package io.rebble.libpebblecommon.permissions

import io.rebble.libpebblecommon.WatchConfig
import io.rebble.libpebblecommon.database.entity.LockerAppPermission
import io.rebble.libpebblecommon.plugin.PluginPermission
import io.rebble.libpebblecommon.plugin.PluginPermissions.CALENDAR
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

// This key can still arrive in an old manifest or a restored database.
private const val RETIRED = "LegacyPebbleKit"

class RemovedCompanionPermissionTest {
    @Test fun declarationsAreNeverRequestedCountedOrReviewed() = runTest {
        val dao = FakePermissionDao()
        val permissions = permissions(dao, config = WatchConfig(permissionPolicy = PermissionPolicy.AlwaysAsk))
        val retired = PluginPermission(RETIRED, required = true, reason = "Old companion")
        val requested = RequestedPermissions(listOf(retired), hasPkjs = false)
        assertNull(PermissionRegistry[RETIRED])
        assertEquals(emptyList(), retired.keys())
        assertEquals(emptyList(), PluginPermission("$RETIRED/old").keys())
        assertEquals(emptyList(), requested.all)
        assertFalse(requested.declared!!.describesRequired())
        assertEquals(emptyList(), permissions.toReview(APP, requested))
        assertEquals(emptyList(), permissions.automaticallyGranted(APP, requested))
        val mixed = requested.copy(declared = listOf(retired, PluginPermission(CALENDAR)))
        assertEquals(listOf(CALENDAR), mixed.all)
        assertFalse(mixed.declared!!.describesRequired())
        assertTrue(InstallReview(APP, "App", mixed.all, declared = mixed.declared).needsAnswer(CALENDAR))
        permissions.recordRequested(APP, requested)
        assertTrue(dao.rows.value.isEmpty())
    }

    @Test fun savedRowsNeverAppearInAnyPermissionViewOrCount() = runTest {
        for (policy in PermissionPolicy.entries) {
            for (legacy in listOf(false, true)) {
                for (granted in listOf(null, false, true)) {
                    val dao = FakePermissionDao()
                    val subject = subject(legacy = legacy)
                    val running = RunningApps(NoWatches).apply { started(APP) }
                    val permissions = permissions(dao, config = WatchConfig(permissionPolicy = policy),
                        installed = installedAs(subject), running = running)
                    dao.insertOrReplace(LockerAppPermission(APP, RETIRED, granted, requestedAtMs = 1,
                        askedAtMs = 1, lastUsedAtMs = 2, reason = "Old companion", required = true))
                    assertEquals(PermissionDecision.Denied, permissions.check(subject, RETIRED))
                    assertEquals(PermissionDecision.Denied, permissions.request(subject, RETIRED))
                    assertEquals(emptyList(), permissions.statuses(APP).first())
                    assertEquals(emptyList(), permissions.statuses(null).first())
                    assertEquals(emptyList(), permissions.pendingPermissionRequests().first())
                    assertEquals(emptyList(), permissions.activePermissionRequests().first())
                    assertEquals(emptyList(), permissions.permissionDecisions().first())
                    assertFalse(permissions.canExfiltrate(APP))
                    assertEquals(2L, dao.row(RETIRED)!!.lastUsedAtMs)
                }
            }
        }
    }

    @Test fun reconcilingAnAppDeletesRetiredRowsAndPreservesOtherDecisions() = runTest {
        val dao = FakePermissionDao()
        dao.insertOrReplace(LockerAppPermission(APP, RETIRED, true, requestedAtMs = 1))
        dao.insertOrReplace(LockerAppPermission(APP, CALENDAR, false, requestedAtMs = 2))
        val requested = RequestedPermissions(listOf(PluginPermission(RETIRED), PluginPermission(CALENDAR)), hasPkjs = false)
        permissions(dao).recordRequested(APP, requested)
        assertNull(dao.row(RETIRED))
        assertEquals(false, dao.row(CALENDAR)!!.granted)
        assertEquals(setOf(CALENDAR), dao.rows.value.keys.map { it.second }.toSet())
    }
}
