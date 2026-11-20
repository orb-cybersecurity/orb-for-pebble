@file:OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)

package coredevices.coreapp

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
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
    @Test fun grantsAndRunningAppsNotifyOnlySerialFreeProtocolUris() = runTest {
        val pkg = "com.orbcybersecurity.orb"
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
        val permissions = Mockito.mock(AppPermissions::class.java)
        Mockito.`when`(permissions.permissionDecisions()).thenReturn(decisions)
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
            uris.`when`<Uri> { Uri.parse("content://$pkg.pebblekit/activeApp") }.thenReturn(activeUri)
            provider.initialize()
            runCurrent()
            notifications.clear()
            val grant = LockerAppPermission(Uuid.random(), pebbleKit2Key("companion.example"), true, 0)
            decisions.value = listOf(grant)
            runCurrent()
            assertEquals(listOf(connectedUri.toString()), notifications)
            notifications.clear()
            decisions.value = listOf(grant.copy(lastUsedAtMs = 42))
            runCurrent()
            assertEquals(emptyList(), notifications)
            decisions.value = listOf(grant.copy(granted = false))
            runCurrent()
            assertEquals(listOf(connectedUri.toString()), notifications)
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
