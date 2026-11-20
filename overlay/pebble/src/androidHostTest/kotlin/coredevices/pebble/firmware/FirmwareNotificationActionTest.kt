package coredevices.pebble.firmware

import com.russhwolf.settings.MapSettings
import coredevices.util.CoreConfig
import coredevices.util.CoreConfigFlow
import io.rebble.libpebblecommon.connection.AppContext
import io.rebble.libpebblecommon.connection.CommonConnectedDevice
import io.rebble.libpebblecommon.connection.FirmwareUpdateCheckResult
import io.rebble.libpebblecommon.connection.FirmwareUpdateCheckState
import io.rebble.libpebblecommon.connection.LibPebble
import io.rebble.libpebblecommon.connection.PebbleDevice
import io.rebble.libpebblecommon.connection.PebbleSocketIdentifier
import io.rebble.libpebblecommon.connection.endpointmanager.FirmwareUpdateTrigger
import io.rebble.libpebblecommon.services.FirmwareVersion
import kotlinx.coroutines.flow.MutableStateFlow
import java.lang.reflect.Proxy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.time.Clock
import kotlin.time.Instant

class FirmwareNotificationActionTest {
    @Test fun onlyTheAdvertisedWatchAndVersionCanInstall() {
        val identifier = PebbleSocketIdentifier("watch-A")
        val version = FirmwareVersion.from("v4.47.2", false, "", Instant.DISTANT_PAST, false, false)!!
        val update = FirmwareUpdateCheckResult.FoundUpdate(version, "https://example.org/firmware", "", true)
        val installs = mutableListOf<Pair<FirmwareUpdateCheckResult.FoundUpdate, FirmwareUpdateTrigger>>()
        val watch = Proxy.newProxyInstance(CommonConnectedDevice::class.java.classLoader,
            arrayOf(CommonConnectedDevice::class.java)) { _, method, args ->
            when (method.name) {
                "toString" -> "test-watch"
                "getIdentifier" -> identifier
                "getFirmwareUpdateAvailable" -> FirmwareUpdateCheckState(false, update)
                "updateFirmware" -> { installs.add((args!![0] as FirmwareUpdateCheckResult.FoundUpdate) to (args[1] as FirmwareUpdateTrigger)); Unit }
                else -> error("Unexpected watch call ${method.name}")
            }
        } as CommonConnectedDevice
        val lib = Proxy.newProxyInstance(LibPebble::class.java.classLoader, arrayOf(LibPebble::class.java)) { _, method, _ ->
            check(method.name == "getWatches")
            MutableStateFlow(listOf<PebbleDevice>(watch))
        } as LibPebble
        val unsafe = sun.misc.Unsafe::class.java.getDeclaredField("theUnsafe").apply { isAccessible = true }
            .get(null) as sun.misc.Unsafe
        val tracker = RealFirmwareUpdateUiTracker(MapSettings(), Clock.System,
            unsafe.allocateInstance(AppContext::class.java) as AppContext,
            CoreConfigFlow(MutableStateFlow(CoreConfig())))
        tracker.updateWatchNow(lib, "watch-B", version.stringVersion)
        tracker.updateWatchNow(lib, identifier.asString, "v4.46.0")
        assertTrue(installs.isEmpty())
        tracker.updateWatchNow(lib, identifier.asString, version.stringVersion)
        assertEquals(listOf(update to FirmwareUpdateTrigger.Ui), installs)
    }
}
