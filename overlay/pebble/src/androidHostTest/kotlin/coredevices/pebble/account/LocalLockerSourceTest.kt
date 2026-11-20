package coredevices.pebble.account

import com.russhwolf.settings.MapSettings
import io.rebble.libpebblecommon.database.entity.LockerAppPermission
import io.rebble.libpebblecommon.permissions.PermissionDecisionRecord
import io.rebble.libpebblecommon.web.LockerEntry
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Duration
import kotlin.uuid.Uuid

class LocalLockerSourceTest {
    @Test fun explicitHttpsReplacementRelinksOnlyTheMatchingHttpRegistryAndPersistsBeforeSync() = runTest {
        val settings = MapSettings()
        val serializer = ListSerializer(FirestoreLockerEntry.serializer())
        val urls = listOf("http://store.example/api", "http://store.example/other", "http://other.example/api", "https://store.example/api")
        val entries = urls.map { FirestoreLockerEntry(Uuid.random(), "id", it, "token") }
        settings.putString("orb_store_apps", Json.encodeToString(serializer, entries))
        var syncs = 0
        val proxy = object : LibPebbleLockerProxy {
            override fun getAllLockerUuids(): Flow<List<Uuid>> = flowOf(emptyList())
            override suspend fun addAppsToLocker(apps: List<LockerEntry>, permissions: Map<Uuid, Map<String, PermissionDecisionRecord>>) = Unit
            override suspend fun waitUntilAppSyncedToWatch(id: Uuid, timeout: Duration) = false
            override suspend fun startAppOnWatch(id: Uuid) = false
            override suspend fun permissionDecisions(): List<LockerAppPermission> = emptyList()
            override fun requestLockerSync() {
                syncs++
                assertEquals("https://store.example/api", Json.decodeFromString(serializer, settings.getString("orb_store_apps", "")).first().appstoreSource)
            }
        }
        val locker = LocalLocker(proxy, settings)
        locker.relinkHttpSource("https://store.example/api")
        val expected = entries.mapIndexed { i, entry -> if (i == 0) entry.copy(appstoreSource = "https://store.example/api") else entry }
        assertEquals(expected, locker.locker.value)
        assertEquals(expected, LocalLocker(proxy, settings).locker.value)
        assertEquals(1, syncs)
        locker.relinkHttpSource("https://store.example/api")
        locker.relinkHttpSource("http://store.example/other")
        assertEquals(1, syncs)
    }
}
