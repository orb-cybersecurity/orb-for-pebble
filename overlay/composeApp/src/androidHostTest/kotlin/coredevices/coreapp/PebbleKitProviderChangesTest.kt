@file:OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)

package coredevices.coreapp

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import io.rebble.libpebblecommon.LibPebbleConfig
import io.rebble.libpebblecommon.WatchConfigFlow
import io.rebble.libpebblecommon.database.dao.LockerAppPermissionDao
import io.rebble.libpebblecommon.permissions.InstalledApps
import io.rebble.libpebblecommon.permissions.PermissionPolicy
import io.rebble.libpebblecommon.permissions.PermissionSubject
import io.rebble.libpebblecommon.permissions.RunningApps
import io.rebble.libpebblecommon.connection.FakeConnectedDevice
import io.rebble.libpebblecommon.connection.LibPebble
import io.rebble.libpebblecommon.connection.PebbleDevice
import io.rebble.libpebblecommon.database.entity.LockerAppPermission
import io.rebble.libpebblecommon.di.LibPebbleCoroutineScope
import io.rebble.libpebblecommon.metadata.WatchHardwarePlatform
import io.rebble.libpebblecommon.pebblekit.two.PebbleKitProvider
import io.rebble.libpebblecommon.permissions.AppPermissions
import io.rebble.libpebblecommon.permissions.pebbleKit2Key
import io.rebble.libpebblecommon.services.FirmwareVersion
import io.rebble.libpebblecommon.services.WatchInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.koin.dsl.koinApplication
import org.koin.dsl.module
import org.mockito.Mockito
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.uuid.Uuid

/** Exercise the provider's real collectors, with only the OS boundary and inputs replaced. */
class PebbleKitProviderChangesTest {
    @Test fun effectiveAccessWatchesAndRunningAppsNotifyOnlySerialFreeProtocolUris() = runTest {
        val pkg = "com.orbcybersecurity.orb"
        val rootUri = Mockito.mock(Uri::class.java)
        Mockito.`when`(rootUri.toString()).thenReturn("content://$pkg.pebblekit")
        val connectedUri = Mockito.mock(Uri::class.java)
        val activeUri = Mockito.mock(Uri::class.java)
        Mockito.`when`(connectedUri.toString()).thenReturn("content://$pkg.pebblekit/connectedWatches")
        Mockito.`when`(activeUri.toString()).thenReturn("content://$pkg.pebblekit/activeApp")
        val context = Mockito.mock(Context::class.java)
        val resolver = Mockito.mock(ContentResolver::class.java)
        Mockito.`when`(context.packageName).thenReturn(pkg)
        Mockito.`when`(context.contentResolver).thenReturn(resolver)
        val notifications = mutableListOf<String>()
        Mockito.doAnswer { notifications.add(it.arguments[0].toString()); null }
            .`when`(resolver).notifyChange(Mockito.any(Uri::class.java), Mockito.isNull())
        val running = MutableStateFlow<Uuid?>(null)
        val watch = Mockito.mock(FakeConnectedDevice::class.java)
        val info = Mockito.mock(WatchInfo::class.java)
        Mockito.`when`(info.serial).thenReturn("private-watch-serial")
        Mockito.`when`(info.platform).thenReturn(WatchHardwarePlatform.PEBBLE_SNOWY_DVT)
        Mockito.`when`(info.runningFwVersion).thenReturn(
            FirmwareVersion.from("v4.3", false, "", kotlin.time.Instant.DISTANT_PAST, false, false)!!)
        Mockito.`when`(watch.watchInfo).thenReturn(info)
        Mockito.`when`(watch.displayName()).thenReturn("Watch")
        Mockito.`when`(watch.runningApp).thenReturn(running)
        val watches = MutableStateFlow<List<PebbleDevice>>(listOf(watch))
        val lib = Mockito.mock(LibPebble::class.java)
        Mockito.`when`(lib.watches).thenReturn(watches)
        val decisions = MutableStateFlow<List<LockerAppPermission>>(emptyList())
        val subjects = MutableStateFlow<Map<Uuid, PermissionSubject>>(emptyMap())
        val config = MutableStateFlow(LibPebbleConfig())
        val dao = Mockito.mock(LockerAppPermissionDao::class.java)
        Mockito.`when`(dao.allFlow()).thenReturn(decisions)
        val installed = object : InstalledApps {
            override fun subjectsOf(appUuids: Set<Uuid>) = subjects.map { all -> all.filterKeys { it in appUuids } }
            override fun pluginPermissions() = flowOf(emptyMap<String, io.rebble.libpebblecommon.permissions.PluginDefinedPermission>())
        }
        val permissions = AppPermissions(dao, installed, WatchConfigFlow(config), kotlin.time.Clock.System,
            RunningApps(lib), LibPebbleCoroutineScope(backgroundScope.coroutineContext))
        val koin = koinApplication { modules(module {
            single<LibPebble> { lib }
            single { permissions }
            single { LibPebbleCoroutineScope(backgroundScope.coroutineContext) }
        }) }
        val provider = Mockito.mock(PebbleKitProvider::class.java, Mockito.CALLS_REAL_METHODS)
        Mockito.doReturn(koin.koin).`when`(provider).getKoin()
        Mockito.doReturn(context).`when`(provider).context
        val contractClass = Class.forName("io.rebble.pebblekit2.PebbleKitProviderContract\$ConnectedWatch")
        val contract = Mockito.mockStatic(contractClass)
        val uris = Mockito.mockStatic(Uri::class.java)
        try {
            contract.`when`<Uri> { contractClass.getMethod("getContentUri", String::class.java).invoke(null, pkg) }.thenReturn(connectedUri)
            uris.`when`<Uri> { Uri.parse("content://$pkg.pebblekit") }.thenReturn(rootUri)
            uris.`when`<Uri> { Uri.parse("content://$pkg.pebblekit/activeApp") }.thenReturn(activeUri)
            provider.initialize()
            runCurrent()
            notifications.clear()
            val grant = LockerAppPermission(Uuid.random(), pebbleKit2Key("companion.example"), true, 0)
            subjects.value = mapOf(grant.appUuid to PermissionSubject(grant.appUuid, legacy = false))
            decisions.value = listOf(grant)
            runCurrent()
            assertEquals(listOf(rootUri.toString()), notifications)
            notifications.clear()
            decisions.value = listOf(grant.copy(lastUsedAtMs = 42, askedAtMs = 42))
            runCurrent()
            assertEquals(emptyList(), notifications)
            decisions.value = listOf(grant.copy(granted = false))
            runCurrent()
            assertEquals(listOf(rootUri.toString()), notifications)
            notifications.clear()
            // A legacy declaration can precede its locker entry, with no explicit grant.
            val legacy = LockerAppPermission(Uuid.random(), pebbleKit2Key("legacy.example"), null, 0)
            decisions.value = listOf(legacy)
            runCurrent()
            assertEquals(emptyList(), notifications)
            subjects.value = subjects.value + (legacy.appUuid to PermissionSubject(legacy.appUuid, legacy = true))
            runCurrent()
            assertEquals(listOf(rootUri.toString()), notifications)
            notifications.clear()
            config.value = config.value.copy(watchConfig = config.value.watchConfig.copy(askLegacyAppsForPermissions = true))
            runCurrent()
            assertEquals(listOf(rootUri.toString()), notifications)
            notifications.clear()
            decisions.value = listOf(legacy.copy(askedAtMs = 100, lastUsedAtMs = 100))
            runCurrent()
            assertEquals(emptyList(), notifications)
            config.value = config.value.copy(watchConfig = config.value.watchConfig.copy(permissionPolicy = PermissionPolicy.NeverAsk))
            runCurrent()
            assertEquals(listOf(rootUri.toString()), notifications)
            notifications.clear()
            // Explicit -> automatic permission changes keep the same effectively allowed set.
            decisions.value = listOf(legacy.copy(granted = true))
            runCurrent()
            assertEquals(emptyList(), notifications)
            decisions.value = listOf(legacy)
            runCurrent()
            assertEquals(emptyList(), notifications)
            subjects.value = emptyMap()
            runCurrent()
            assertEquals(listOf(rootUri.toString()), notifications)
            notifications.clear()
            running.value = Uuid.random()
            runCurrent()
            assertEquals(listOf(activeUri.toString()), notifications)
            notifications.clear()
            running.value = Uuid.random()
            runCurrent()
            assertEquals(listOf(activeUri.toString()), notifications)
            notifications.clear()
            watches.value = emptyList()
            runCurrent()
            assertEquals(setOf(connectedUri.toString(), activeUri.toString()), notifications.toSet())
        } finally {
            uris.close()
            contract.close()
            koin.close()
        }
    }
}
