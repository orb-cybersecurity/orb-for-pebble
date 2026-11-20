package coredevices.pebble.config

import io.rebble.libpebblecommon.permissions.AppPermissionStatus
import io.rebble.libpebblecommon.permissions.PermissionStatus
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class ConfigPageNetworkPolicyTest {
    private val app = Uuid.parse("00000000-0000-0000-0000-000000000123")
    private fun status(key: String, value: PermissionStatus = PermissionStatus.Granted, used: Long? = null) =
        AppPermissionStatus(app, key, value, lastUsedAtMs = used)

    @Test fun nullDomainsStillBlockBrowserSocketsAndWorkers() {
        val csp = configPageCsp(null, "https://config.example/settings")
        assertTrue("connect-src https: http:;" in csp)
        assertTrue("worker-src 'none'; object-src 'none'" in csp)
        assertFalse("ws:" in csp || "wss:" in csp || "connect-src *" in csp)
    }

    @Test fun ownOriginAndNavigationSurviveARestrictedResourcePolicy() {
        val page = "https://config.example:8443/settings"
        val csp = configPageCsp(listOf("api.example"), page)
        assertTrue("frame-src 'none';" in csp)
        assertTrue("form-action " in csp && "https://config.example:8443 pebblejs:" in csp)
        assertTrue(configPageMayUseBridge(page, "https://config.example:8443", true, "$page/next"))
        assertFalse(configPageMayUseBridge(page, "https://api.example", true, page))
        assertFalse(configPageMayUseBridge(page, "https://config.example:8443", false, page))
        assertTrue("connect-src 'none';" in configPageCsp(emptyList(), page))
    }

    @Test fun everyLostNetworkGrantClosesThePageIncludingAutomaticAndRemovedGrants() {
        for (key in listOf("Internet", "Internet/api.example", "LocalNetwork", "GlobalInternet")) {
            val granted = listOf(status(key))
            assertTrue(configPageNetworkRevoked(granted, listOf(status(key, PermissionStatus.Denied))))
            assertTrue(configPageNetworkRevoked(granted, listOf(status(key, PermissionStatus.Waiting))))
            assertTrue(configPageNetworkRevoked(granted, emptyList()))
            assertTrue(configPageNetworkRevoked(listOf(status(key, PermissionStatus.AllowedAutomatically)), emptyList()))
        }
    }

    @Test fun usagePromptsAndUnrelatedDecisionsDoNotCloseThePage() {
        val before = listOf(status("Internet/api.example"), status("Location"))
        assertFalse(configPageNetworkRevoked(before, before.map { it.copy(lastUsedAtMs = 99) }))
        assertFalse(configPageNetworkRevoked(before, before + status("Internet/new.example", PermissionStatus.Waiting)))
        assertFalse(configPageNetworkRevoked(before, listOf(status("Internet/api.example"), status("Location", PermissionStatus.Denied))))
        assertFalse(configPageNetworkRevoked(emptyList(), before))
    }

    @Test fun theOpenPageObservesRevocationWithoutRestartingTheCollector() = runTest {
        val statuses = MutableSharedFlow<List<AppPermissionStatus>?>()
        var closed = 0
        backgroundScope.launch { configPageNetworkRevocations(statuses).collect { closed++ } }
        runCurrent()
        statuses.emit(listOf(status("Internet")))
        statuses.emit(listOf(status("Internet", used = 10)))
        statuses.emit(listOf(status("Internet"), status("Internet/new.example", PermissionStatus.Waiting)))
        kotlin.test.assertEquals(0, closed)
        statuses.emit(listOf(status("Internet", PermissionStatus.Denied)))
        runCurrent()
        kotlin.test.assertEquals(1, closed)
    }
}
