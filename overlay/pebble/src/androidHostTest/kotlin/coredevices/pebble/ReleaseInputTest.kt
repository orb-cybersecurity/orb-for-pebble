package coredevices.pebble

import com.eygraber.uri.Uri
import coredevices.database.AppstoreSourceDao
import coredevices.pebble.account.PebbleAccount
import coredevices.pebble.firmware.FirmwareUpdateUiTracker
import coredevices.pebble.ui.PebbleNavBarRoutes
import io.rebble.libpebblecommon.connection.AppContext
import io.rebble.libpebblecommon.connection.LibPebble
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.io.files.Path
import java.lang.reflect.Proxy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** No Android operations are used by these navigation/confirmation tests. */
private fun inertContext(): AppContext {
    val field = sun.misc.Unsafe::class.java.getDeclaredField("theUnsafe").apply { isAccessible = true }
    return (field.get(null) as sun.misc.Unsafe).allocateInstance(AppContext::class.java) as AppContext
}

private inline fun <reified T> unused(): T = Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, method, _ ->
    error("Unexpected ${method.name}")
} as T

class ReleaseInputTest {
    private fun handler() = RealPebbleDeepLinkHandler(
        unused<PebbleAccount>(), unused<LibPebble>(), inertContext(), unused<AppstoreSourceDao>(),
        unused<FirmwareUpdateUiTracker>(),
    )

    @Test fun publicShowWatchesPathsOnlyNavigate() {
        val handler = handler()
        // Every call on either the watch manager or firmware tracker would fail this test.
        assertTrue(handler.handle(Uri.parse("pebble://show-watches/AA:BB:CC:DD:EE:FF")))
        assertEquals(PebbleNavBarRoutes.WatchesRoute, handler.navigateToPebbleDeepLink.value?.route)
    }

    @Test fun aStaleConfirmationCannotConsumeTheDisplayedFirmwareAndAnotherImportIsRejected() {
        val handler = handler()
        val shown = PendingFirmwareSideload(Path("/tmp/displayed.pbz"), "displayed.pbz")
        val field = RealPebbleDeepLinkHandler::class.java.getDeclaredField("_pendingFirmwareSideload").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        val pending = field.get(handler) as MutableStateFlow<PendingFirmwareSideload?>
        pending.value = shown
        handler.confirmPendingFirmwareSideload(PendingFirmwareSideload(Path("/tmp/other.pbz"), "other.pbz"))
        assertEquals(shown, handler.pendingFirmwareSideload.value)
        assertFalse(handler.handle(Uri.parse("content://untrusted/other.pbz")))
        assertFalse(handler.handle(Uri.parse("pebble://custom-boot-config-url/https%3A%2F%2Fexample.org%2F%3Faccess_token%3Dx%26t%3D1")))
        assertEquals(shown, handler.pendingFirmwareSideload.value)
    }

    @Test fun filenamesCannotSupplyExtraLinesOrBidirectionalFormatting() {
        assertEquals("firmware.pbz", orbDisplayName("\u202efirmware\n.pbz").replace(" ", ""))
        assertTrue(orbDisplayName("a".repeat(200)).length <= 64)
    }
}
