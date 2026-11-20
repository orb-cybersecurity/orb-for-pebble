package io.rebble.libpebblecommon.permissions

import io.rebble.libpebblecommon.WatchConfig
import io.rebble.libpebblecommon.di.LibPebbleKoinComponent
import io.rebble.libpebblecommon.js.GeolocationInterface
import io.rebble.libpebblecommon.plugin.PluginPermissions
import io.rebble.libpebblecommon.util.GeolocationPositionResult
import io.rebble.libpebblecommon.util.SystemGeolocation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.koin.dsl.module
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.time.Duration

class OrbRevocationTest {
    @Test fun legacyNetworkAndLocationRequireExplicitDecisionsEvenUnderNeverAsk() = runTest {
        val dao = FakePermissionDao()
        val p = permissions(dao, config = WatchConfig(permissionPolicy = PermissionPolicy.NeverAsk),
            installed = installedAs(subject(legacy = true)))
        for (key in listOf(PluginPermissions.GLOBAL_INTERNET, PluginPermissions.LOCATION)) {
            assertEquals(PermissionDecision.NeedsApproval, p.check(APP, key))
            p.setDecisions(APP, mapOf(key to true))
            assertEquals(PermissionDecision.Granted, p.check(APP, key))
            p.setDecisions(APP, mapOf(key to false))
            assertEquals(PermissionDecision.Denied, p.check(APP, key))
        }
    }

    @Test fun replacedAndRevokedLocationWatchesAreCancelledAndBounded() = runTest {
        val dao = FakePermissionDao()
        val p = permissions(dao)
        p.setDecisions(APP, mapOf(PluginPermissions.LOCATION to true))
        val updates = MutableSharedFlow<GeolocationPositionResult>()
        var active = 0
        val location = object : SystemGeolocation {
            override suspend fun getCurrentPosition(maximumAge: Duration?, timeout: Duration?, highAccuracy: Boolean) =
                GeolocationPositionResult.Error("unused")
            override suspend fun watchPosition(interval: Duration, highAccuracy: Boolean): Flow<GeolocationPositionResult> = flow {
                active++
                try { updates.collect { emit(it) } } finally { active-- }
            }
        }
        val bindings = module { single { p }; single<SystemGeolocation> { location } }
        val koin = object : LibPebbleKoinComponent {}.getKoin()
        koin.loadModules(listOf(bindings))
        val delivered = mutableListOf<String>()
        val geo = object : GeolocationInterface(backgroundScope, { delivered += it }, APP) {}
        try {
            geo.watchPosition(1.0, 200.0, 0.0); runCurrent()
            assertEquals(1, active)
            geo.watchPosition(1.0, 200.0, 0.0); runCurrent()
            assertEquals(1, active)
            for (id in 2..20) geo.watchPosition(id.toDouble(), 200.0, 0.0)
            runCurrent()
            assertEquals(8, active)
            updates.emit(GeolocationPositionResult.Error("before")); runCurrent()
            assertEquals(8, delivered.size)
            p.setDecisions(APP, mapOf(PluginPermissions.LOCATION to false)); runCurrent()
            assertEquals(0, active)
            updates.emit(GeolocationPositionResult.Error("after")); runCurrent()
            assertFalse(delivered.any { "after" in it })
        } finally { geo.clearAllWatches(); koin.unloadModules(listOf(bindings)) }
    }
}
