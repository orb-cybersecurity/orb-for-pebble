package coredevices.pebble.account

import com.russhwolf.settings.MapSettings
import coredevices.database.AppstoreSourceDao
import coredevices.pebble.services.PebbleWebServices
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import java.lang.reflect.Proxy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

private inline fun <reified T> proxy(crossinline answer: (String) -> Any?): T =
    Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, method, _ -> answer(method.name) } as T

class AccountIdentityTest {
    private val settings = MapSettings().apply {
        putString("account_token_key", "previous-token")
        putString("dev_token_key", "previous-user")
    }
    private val sources = proxy<AppstoreSourceDao> { if (it == "getAllSources") flowOf(emptyList<Any>()) else Unit }
    private val boot = object : BootConfigProvider {
        override suspend fun setUrl(url: String?) {}
        override fun getUrl(): String? = null
        override suspend fun getBootConfig(): BootConfig? = null
    }

    @Test fun logoutClearsBothPersistedAndInMemoryIdentityWithoutLookingUpAUser() = runTest {
        val services = proxy<PebbleWebServices> { error("Logout must not fetch identity") }
        val account = RealPebbleAccount(settings, services, boot, sources)
        account.setToken(null, null)
        assertNull(account.loggedIn.value)
        assertNull(account.devToken.value)
        assertNull(settings.getStringOrNull("dev_token_key"))
    }

    @Test fun failedAccountSwitchDoesNotRetainThePreviousIdentity() = runTest {
        val account = RealPebbleAccount(settings, proxy<PebbleWebServices> { null }, boot, sources)
        account.setToken("replacement-token", null)
        assertEquals("replacement-token", account.loggedIn.value)
        assertNull(account.devToken.value)
        assertNull(settings.getStringOrNull("dev_token_key"))
    }

    @Test fun aNewIdentityIsCommittedOnlyAfterTheOldIdentityHasBeenCleared() = runTest {
        lateinit var account: RealPebbleAccount
        val services = proxy<PebbleWebServices> {
            assertNull(account.devToken.value)
            assertNull(settings.getStringOrNull("dev_token_key"))
            UsersMeResponse(listOf(UsersMeUser("new-user", emptyList())))
        }
        account = RealPebbleAccount(settings, services, boot, sources)
        account.setToken("replacement-token", null)
        assertEquals("new-user", account.devToken.value)
        assertEquals("new-user", settings.getStringOrNull("dev_token_key"))
    }
}
