package coredevices.pebble.account

import co.touchlab.kermit.Logger
import com.russhwolf.settings.Settings
import coredevices.database.AppstoreSourceDao
import coredevices.pebble.services.AppstoreService
import coredevices.pebble.services.REBBLE_FEED_URL
import coredevices.pebble.ui.CommonAppType
import io.rebble.libpebblecommon.database.entity.APP_VERSION_REGEX
import io.rebble.libpebblecommon.database.entity.LockerAppPermission
import io.rebble.libpebblecommon.permissions.PermissionDecisionRecord
import io.rebble.libpebblecommon.web.LockerEntry
import io.rebble.libpebblecommon.web.LockerModel
import io.rebble.libpebblecommon.web.LockerModelWrapper
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import org.koin.core.component.KoinComponent
import org.koin.core.component.get
import org.koin.core.parameter.parametersOf
import kotlin.time.Duration
import kotlin.uuid.Uuid

// Orb: Core keeps the list of a user's store apps in its cloud (Firestore), per Core account. Orb
// has neither, so the same list is kept on the phone: which store each installed store app came
// from. The interface keeps Core's name so its users stay unchanged.

private val logger = Logger.withTag("Locker")

/** The store apps the user installed, and the store each came from. */
interface FirestoreLocker {
    /** Never null in Orb: the list is on the phone and loads at once. */
    val locker: StateFlow<List<FirestoreLockerEntry>?>
    suspend fun fetchLocker(forceRefresh: Boolean): LockerModelWrapper?
    suspend fun addApp(entry: CommonAppType.Store, timelineToken: String?): Boolean
    suspend fun removeApp(uuid: Uuid): Boolean
}

class LocalLocker(
    private val libPebbleLockerProxy: LibPebbleLockerProxy,
    private val settings: Settings,
) : KoinComponent, FirestoreLocker {
    private val json = Json { ignoreUnknownKeys = true }
    private val serializer = ListSerializer(FirestoreLockerEntry.serializer())
    private val writes = Mutex()
    private val _locker = MutableStateFlow<List<FirestoreLockerEntry>?>(load())
    override val locker: StateFlow<List<FirestoreLockerEntry>?> = _locker.asStateFlow()

    private fun load(): List<FirestoreLockerEntry> = try {
        settings.getStringOrNull(KEY)?.let { json.decodeFromString(serializer, it) } ?: emptyList()
    } catch (e: Exception) {
        logger.w(e) { "Discarding an unreadable store-app list" }
        emptyList()
    }

    private suspend fun change(transform: (List<FirestoreLockerEntry>) -> List<FirestoreLockerEntry>) = writes.withLock {
        _locker.update { transform(it.orEmpty()) }
        settings.putString(KEY, json.encodeToString(serializer, _locker.value.orEmpty()))
    }

    /**
     * Core's sync, with this list in place of the cloud one: each store refreshes the apps installed
     * from it, and Rebble, when signed in, also brings in the user's Rebble locker. Nothing is removed
     * by a sync: libpebble deletes what the result leaves out, so every installed app that wasn't
     * fetched is reported as not fetched, which keeps it as it is.
     */
    override suspend fun fetchLocker(forceRefresh: Boolean): LockerModelWrapper {
        val entries = locker.value.orEmpty()
        val designatedSourceByUuid = entries.associate { it.uuid.toString() to it.appstoreSource }
        val installed = libPebbleLockerProxy.getAllLockerUuids().first().toSet()
        val apps = get<AppstoreSourceDao>().getAllEnabledSources().flatMap { source ->
            val appstore: AppstoreService = get { parametersOf(source) }
            val entriesForSource = entries.filter { it.appstoreSource == source.url }
            val rebbleLocker = source.url == REBBLE_FEED_URL && appstore.isLoggedIn()
            if (entriesForSource.isEmpty() && !rebbleLocker) return@flatMap emptyList()
            val appsForSource = appstore.fetchAppStoreApps(entriesForSource, useCache = !forceRefresh)
            if (appsForSource == null) {
                logger.w { "Failed to fetch apps from source ${source.url}" }
                return@flatMap emptyList()
            }
            val fromSource = appsForSource.fromDesignatedSource(source.url, designatedSourceByUuid)
            if (rebbleLocker) {
                val known = entries.map { it.uuid }.toSet()
                val added = fromSource.filter { Uuid.parse(it.uuid) !in known }.map {
                    FirestoreLockerEntry(
                        uuid = Uuid.parse(it.uuid),
                        appstoreId = it.id,
                        appstoreSource = source.url,
                        timelineToken = it.userToken,
                    )
                }
                if (added.isNotEmpty()) change { it + added }
            }
            fromSource
        }
        val fetchedUuids = apps.map { Uuid.parse(it.uuid) }.toSet()
        logger.d { "Fetched ${apps.size} store apps; keeping ${(installed - fetchedUuids).size} others as they are" }
        return LockerModelWrapper(
            locker = LockerModel(applications = apps),
            failedToFetchUuids = installed - fetchedUuids,
            permissions = emptyMap(),
        )
    }

    override suspend fun addApp(entry: CommonAppType.Store, timelineToken: String?): Boolean {
        val uuid = entry.storeApp?.uuid?.let { Uuid.parse(it) } ?: return false
        val added = FirestoreLockerEntry(
            uuid = uuid,
            appstoreId = entry.storeApp.id,
            appstoreSource = entry.storeSource.url,
            timelineToken = timelineToken,
        )
        change { list -> list.filterNot { it.uuid == uuid } + added }
        return true
    }

    override suspend fun removeApp(uuid: Uuid): Boolean {
        change { list -> list.filterNot { it.uuid == uuid } }
        return true
    }

    private companion object {
        const val KEY = "orb_store_apps"
    }
}

/**
 * Workaround for a cyclic dependency, because koin doesn't support Provider
 */
interface LibPebbleLockerProxy {
    fun getAllLockerUuids(): Flow<List<Uuid>>
    suspend fun addAppsToLocker(apps: List<LockerEntry>, permissions: Map<Uuid, Map<String, PermissionDecisionRecord>>)
    suspend fun waitUntilAppSyncedToWatch(id: Uuid, timeout: Duration): Boolean
    suspend fun startAppOnWatch(id: Uuid): Boolean
    fun requestLockerSync()
    suspend fun permissionDecisions(): List<LockerAppPermission>
}

/**
 * An app only ever updates from the store it was installed from: another store publishing the same
 * UUID must not take over its permissions and data. Apps not yet in the locker are [sourceUrl]'s.
 */
internal fun List<LockerEntry>.fromDesignatedSource(sourceUrl: String, designatedSourceByUuid: Map<String, String>) =
    filter { (designatedSourceByUuid[it.uuid] ?: sourceUrl) == sourceUrl }

@Serializable
data class FirestoreLockerEntry(
    val uuid: Uuid,
    val appstoreId: String,
    val appstoreSource: String,
    val timelineToken: String?,
    /** The user's decisions, by permission key, from any device or the web store. */
    val permissions: Map<String, PermissionDecisionRecord>? = null,
    /** Set when read: another client may have stored the entry under a different ID. */
    @Transient val documentId: String? = null,
)

/**
 * Compare two version strings numerically by major.minor segments.
 * null versions sort lower than non-null.
 */
internal fun compareVersionStrings(a: String?, b: String?): Int {
    if (a == null && b == null) return 0
    if (a == null) return -1
    if (b == null) return 1
    val aMatch = APP_VERSION_REGEX.find(a)
    val bMatch = APP_VERSION_REGEX.find(b)
    val aMajor = aMatch?.groupValues?.getOrNull(1)?.toIntOrNull() ?: 0
    val aMinor = aMatch?.groupValues?.getOrNull(2)?.toIntOrNull() ?: 0
    val bMajor = bMatch?.groupValues?.getOrNull(1)?.toIntOrNull() ?: 0
    val bMinor = bMatch?.groupValues?.getOrNull(2)?.toIntOrNull() ?: 0
    return compareValuesBy(aMajor to aMinor, bMajor to bMinor, { it.first }, { it.second })
}