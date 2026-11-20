package io.rebble.libpebblecommon.permissions

import io.rebble.libpebblecommon.plugin.PluginPermissions
import io.rebble.libpebblecommon.plugin.PluginNetworkVerdict
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class WatchappNetworkGateTest {
    @Test fun bareInternetDoesNotGrantLocalNetworkEvenWhenDomainsAndCspWereNull() = runTest {
        val permissions = permissions(FakePermissionDao(), installed = installedAs(subject(legacy = false)))
        permissions.setDecisions(APP, mapOf(PluginPermissions.INTERNET to true))
        assertEquals(null, permissions.grantedDomains(APP))
        val gate = NetworkGate(permissions, "Settings", APP)
        assertEquals(PluginNetworkVerdict.Allowed, gate.check("wss://api.example/socket", false))
        for (host in listOf("localhost", "127.0.0.1", "192.168.1.1", "thing.local", "[::1]")) {
            assertTrue(gate.check("wss://$host/socket", false) is PluginNetworkVerdict.Denied)
        }
        permissions.setDecisions(APP, mapOf(PluginPermissions.LOCAL_NETWORK to true))
        assertEquals(PluginNetworkVerdict.Allowed, gate.check("wss://192.168.1.1/socket", false))
        permissions.setDecisions(APP, mapOf(PluginPermissions.INTERNET to false))
        assertTrue(gate.check("wss://api.example/socket", false) is PluginNetworkVerdict.Denied)
    }

    @Test fun domainAndLegacyGrantsAreRecheckedForEveryHttpAndSocketRequest() = runTest {
        for (legacy in listOf(false, true)) {
            val permissions = permissions(FakePermissionDao(), installed = installedAs(subject(legacy = legacy)))
            val permission = if (legacy) PluginPermissions.GLOBAL_INTERNET else internetKey("api.example")
            permissions.setDecisions(APP, mapOf(permission to true))
            val gate = NetworkGate(permissions, "Settings", APP)
            for (scheme in listOf("https", "wss")) {
                assertEquals(PluginNetworkVerdict.Allowed, gate.check("$scheme://api.example/data", false))
            }
            permissions.setDecisions(APP, mapOf(permission to false))
            for (scheme in listOf("https", "wss")) {
                assertTrue(gate.check("$scheme://api.example/data", false) is PluginNetworkVerdict.Denied)
            }
        }
    }
}
