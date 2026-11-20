package io.rebble.libpebblecommon.permissions

import com.russhwolf.settings.MapSettings
import io.rebble.libpebblecommon.WatchConfig
import io.rebble.libpebblecommon.database.dao.LockerAppPermissionDao
import io.rebble.libpebblecommon.database.entity.LockerAppPermission
import io.rebble.libpebblecommon.di.LibPebbleCoroutineScope
import io.rebble.libpebblecommon.locker.Locker
import io.rebble.libpebblecommon.plugin.PluginPermission
import io.rebble.libpebblecommon.plugin.PluginPermissions.CALENDAR
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

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

    @Test fun unknownRowsAreHarmlessBeforeStartupCleanup() = runTest {
        for (policy in PermissionPolicy.entries) {
            for (legacy in listOf(false, true)) {
                for (granted in listOf(null, false, true)) {
                    for (key in listOf(RETIRED, "$RETIRED/old", "UnknownPermission")) {
                        val dao = FakePermissionDao()
                        val subject = subject(legacy = legacy)
                        val running = RunningApps(NoWatches).apply { started(APP) }
                        val config = WatchConfig(permissionPolicy = policy)
                        val permissions = permissions(dao, config = config,
                            installed = installedAs(subject), running = running,
                            scope = LibPebbleCoroutineScope(backgroundScope.coroutineContext))
                        dao.insertOrReplace(LockerAppPermission(APP, key, granted, requestedAtMs = 1,
                            askedAtMs = 1, lastUsedAtMs = 2, reason = "Old companion", required = true))
                        assertEquals(PermissionDecision.Denied, permissions.check(subject, key))
                        assertEquals(PermissionDecision.Denied, permissions.request(subject, key))
                        assertEquals(PermissionDecision.Denied, permissions.query(APP, key))
                        assertEquals(emptySet(), permissions.grantedKeys(subject, listOf(key)).first())
                        assertEquals(emptyList(), permissions.statuses(APP).first())
                        assertEquals(emptyList(), permissions.statuses(null).first())
                        assertEquals(emptyList(), permissions.pendingPermissionRequests().first())
                        assertEquals(emptyList(), permissions.activePermissionRequests().first())
                        assertEquals(emptyList(), permissions.permissionDecisions().first())
                        assertEquals(emptyMap(), permissions.localWatchPermissions().first())
                        assertFalse(permissions.canExfiltrate(APP))
                        val baseline = permissions(FakePermissionDao(), config = config, installed = installedAs(subject))
                        assertEquals(baseline.grantedDomains(APP), permissions.grantedDomains(APP))
                        assertEquals(baseline.query(APP, CALENDAR), permissions.query(APP, CALENDAR))
                        assertEquals(2L, dao.row(key)!!.lastUsedAtMs)
                        val missing = permissions(dao, installed = installedAs(null))
                        assertEquals(emptyList(), missing.statuses(APP).first())
                        assertEquals(emptyList(), missing.statuses(null).first())
                    }
                }
            }
        }
    }

    @Test fun unknownRowsDoNotIncrementThePendingAppCount() = runTest {
        val dao = FakePermissionDao()
        val permissions = permissions(dao, config = WatchConfig(permissionPolicy = PermissionPolicy.AlwaysAsk),
            scope = LibPebbleCoroutineScope(backgroundScope.coroutineContext))
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            permissions.appsWithPendingPermissionRequests.collect {}
        }
        dao.insertOrReplace(LockerAppPermission(APP, RETIRED, null, requestedAtMs = 1, askedAtMs = 1))
        runCurrent()
        assertEquals(emptySet(), permissions.appsWithPendingPermissionRequests.value)
        dao.insertOrReplace(LockerAppPermission(APP, CALENDAR, null, requestedAtMs = 1, askedAtMs = 1))
        runCurrent()
        assertEquals(setOf(APP), permissions.appsWithPendingPermissionRequests.value)
    }

    @Test fun bulkCleanupCoversEveryAppAndKeepsBuiltInsAndPluginNames() = runTest {
        val dao = FakePermissionDao()
        val settings = MapSettings().apply { putBoolean("have_backfilled_declared_permissions", true) }
        var deletes = 0
        val counted = object : LockerAppPermissionDao by dao {
            override suspend fun deleteRetiredPermissions() {
                deletes++
                dao.deleteRetiredPermissions()
            }
        }
        val pluginKey = pluginPermissionKey(APP, RETIRED)
        for (app in listOf(APP, Uuid.random())) {
            for (key in listOf(RETIRED, "$RETIRED/old", CALENDAR, pluginKey)) {
                dao.insertOrReplace(LockerAppPermission(app, key, false, requestedAtMs = 2))
            }
        }
        Locker.removeRetiredPermissionsOnce(counted, settings)
        assertEquals(4, dao.rows.value.size)
        assertEquals(setOf(CALENDAR, pluginKey), dao.rows.value.keys.map { it.second }.toSet())
        assertTrue(dao.rows.value.values.all { it.granted == false && it.requestedAtMs == 2L })
        Locker.removeRetiredPermissionsOnce(counted, settings)
        assertEquals(1, deletes)
    }

    @Test fun failedCleanupDoesNotSetItsFlagAndCanRetry() = runTest {
        val dao = FakePermissionDao()
        val settings = MapSettings()
        val failing = object : LockerAppPermissionDao by dao {
            override suspend fun deleteRetiredPermissions() { error("Database unavailable") }
        }
        assertFailsWith<IllegalStateException> { Locker.removeRetiredPermissionsOnce(failing, settings) }
        assertFalse(settings.getBoolean("have_removed_classic_permissions", false))
        dao.insertOrReplace(LockerAppPermission(APP, RETIRED, true, requestedAtMs = 1))
        Locker.removeRetiredPermissionsOnce(dao, settings)
        assertNull(dao.row(RETIRED))
        assertTrue(settings.getBoolean("have_removed_classic_permissions", false))
    }

    @Test fun cleanupRestoresTheBuiltInFastPathWithoutPluginLoads() = runTest {
        val dao = FakePermissionDao()
        dao.insertOrReplace(LockerAppPermission(APP, RETIRED, true, requestedAtMs = 1))
        dao.insertOrReplace(LockerAppPermission(APP, CALENDAR, true, requestedAtMs = 2))
        var loads = 0
        val permissions = permissions(dao, installed = installedAs(subject(), plugins = flow {
            loads++
            emit(emptyMap())
        }))
        dao.deleteRetiredPermissions()
        assertEquals(PermissionDecision.Granted, permissions.check(APP, CALENDAR))
        assertEquals(PermissionDecision.Granted, permissions.request(APP, CALENDAR))
        assertEquals(PermissionDecision.Granted, permissions.query(APP, CALENDAR))
        assertFalse(permissions.canExfiltrate(APP))
        val requested = RequestedPermissions(listOf(PluginPermission(CALENDAR)), hasPkjs = false)
        assertEquals(emptyList(), permissions.toReview(APP, requested))
        permissions.automaticallyGranted(APP, requested)
        permissions.recordRequested(APP, requested)
        assertEquals(0, loads)
        assertNull(dao.row(RETIRED))
    }

    @Test fun pluginScopedRetiredNameKeepsItsDeclarationReviewAndRuntimeAccess() = runTest {
        val plugin = Uuid.random()
        val key = pluginPermissionKey(plugin, RETIRED)
        val declaration = PluginPermission(RETIRED, plugin = plugin.toString(), required = true, reason = "Plugin access")
        val requested = RequestedPermissions(listOf(declaration, PluginPermission(CALENDAR)), hasPkjs = false)
        assertEquals(listOf(key), declaration.keys())
        assertTrue(requested.declared!!.describesRequired())
        assertEquals(listOf(key, CALENDAR), requested.all)
        assertTrue(InstallReview(APP, "App", requested.all, declared = requested.declared).needsAnswer(key))
        assertFalse(InstallReview(APP, "App", requested.all, declared = requested.declared).needsAnswer(CALENDAR))
        val defined = mapOf(key to PluginDefinedPermission(key, plugin, "Plugin", "Companion", PermissionKind.Write))
        val dao = FakePermissionDao()
        val permissions = permissions(dao, installed = installedAs(subject(), flowOf(defined)))
        permissions.recordRequested(APP, requested)
        assertEquals("Plugin access", dao.row(key)!!.reason)
        assertEquals(true, dao.row(key)!!.required)
        assertEquals(listOf(key), permissions.toReview(APP, requested))
        assertEquals(PermissionDecision.NeedsApproval, permissions.request(APP, key))
        permissions.setDecisions(APP, mapOf(key to true))
        assertEquals(PermissionDecision.Granted, permissions.check(APP, key))
        assertTrue(permissions.statuses(APP).first().any { it.permission == key && it.status == PermissionStatus.Granted })
        assertEquals(listOf(key), permissions.permissionDecisions().first().map { it.permission })
    }
}
