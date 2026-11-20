@file:OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class, org.koin.core.annotation.KoinInternalApi::class)

package coredevices.coreapp

import android.app.Application
import android.content.Context
import com.russhwolf.settings.MapSettings
import com.russhwolf.settings.Settings
import coredevices.coreapp.di.androidDefaultModule
import coredevices.coreapp.di.utilModule
import coredevices.pebble.PebbleAppDelegate
import coredevices.pebble.PebbleAndroidDelegate
import coredevices.pebble.watchModule
import coredevices.util.AndroidPermissionRequester
import coredevices.util.PermissionRequester
import coredevices.database.CoreDatabase
import io.rebble.libpebblecommon.connection.LibPebble
import io.rebble.libpebblecommon.connection.LibPebble3
import io.rebble.libpebblecommon.database.Database
import io.rebble.libpebblecommon.di.LibPebbleCoroutineScope
import java.lang.reflect.ParameterizedType
import java.lang.reflect.Type
import java.lang.reflect.WildcardType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.koin.core.Koin
import org.koin.core.definition.Kind
import org.koin.core.context.startKoin
import org.koin.core.context.stopKoin
import org.koin.dsl.module
import org.mockito.Mockito
import org.mockito.stubbing.Answer
import kotlin.test.Test
import kotlin.test.assertIs
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertSame

/** Both production graphs, including the real LibPebble factory and permission requester. */
class RemovedIntegrationGraphTest {
    @Test fun productionStartupAndEverySingletonResolve() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val directory = kotlin.io.path.createTempDirectory("orb-graph-").toFile()
        val context = Mockito.mock(Application::class.java)
        Mockito.`when`(context.applicationContext).thenReturn(context)
        Mockito.`when`(context.filesDir).thenReturn(directory)
        Mockito.`when`(context.cacheDir).thenReturn(directory)
        Mockito.`when`(context.packageName).thenReturn("com.orbcybersecurity.orb")
        val packages = Mockito.mock(android.content.pm.PackageManager::class.java)
        val packageInfo = Mockito.mock(android.content.pm.PackageInfo::class.java).apply { versionName = "2.0.0-orb1" }
        Mockito.`when`(packages.getPackageInfo(Mockito.anyString(), Mockito.anyInt())).thenReturn(packageInfo)
        Mockito.`when`(context.packageManager).thenReturn(packages)
        Mockito.`when`(context.applicationInfo).thenReturn(Mockito.mock(android.content.pm.ApplicationInfo::class.java))
        Mockito.`when`(context.contentResolver).thenReturn(Mockito.mock(android.content.ContentResolver::class.java))
        val settings = MapSettings()
        val data = EmptyDatabase()
        val leaves = module {
            single<Context> { context }
            single<Application> { context }
            single<Settings> { settings }
            single { data.mock(CoreDatabase::class.java) }
            single { Mockito.mock(dev.jordond.compass.geocoder.Geocoder::class.java) }
            single { Mockito.mock(com.viktormykhailiv.kmp.health.HealthManager::class.java) }
        }
        val libraryLeaves = module {
            single<Settings> { settings }
            single { data.mock(Database::class.java) }
            single { LibPebbleCoroutineScope(backgroundScope.coroutineContext) }
        }
        // Skip only OS observer constructors; Koin still resolves every constructor argument.
        val osConstructors = listOf(
            io.rebble.libpebblecommon.calendar.AndroidSystemCalendar::class.java,
            io.rebble.libpebblecommon.io.rebble.libpebblecommon.calls.AndroidSystemCallLog::class.java,
            io.rebble.libpebblecommon.io.rebble.libpebblecommon.contacts.AndroidSystemContacts::class.java,
            io.rebble.libpebblecommon.io.rebble.libpebblecommon.music.AndroidSystemMusicControl::class.java,
            io.rebble.libpebblecommon.io.rebble.libpebblecommon.util.AndroidSystemGeolocation::class.java,
        ).map { Mockito.mockConstruction(it) }
        var library: Koin? = null
        // Decorate the real loader only to install OS/data leaves before create() resolves it.
        // No app/library service or cross-graph edge is replaced, including transcription.
        val facade = Class.forName("io.rebble.libpebblecommon.di.LibPebbleModuleKt")
        val loader = Mockito.mockStatic(facade, Answer { invocation ->
            invocation.callRealMethod().also { result ->
                if (invocation.method.name == "initKoin") {
                    (result as Koin).loadModules(listOf(libraryLeaves))
                    library = result
                }
            }
        })
        val app = startKoin { modules(androidDefaultModule, utilModule, watchModule, leaves) }
        try {
            app.createEagerInstances()
            val lib = assertIs<LibPebble3>(app.koin.get<LibPebble>())
            app.koin.get<PebbleAppDelegate>()
            app.koin.get<CommonAppDelegate>()
            app.koin.get<PebbleAndroidDelegate>()
            assertIs<AndroidPermissionRequester>(app.koin.get<PermissionRequester>())
            assertSame(lib, library!!.get<LibPebble>())
            val libKoin = library!!
            libKoin.createEagerInstances()
            resolveSingletons(app.koin)
            resolveSingletons(libKoin)
            permissionSnapshotsKeepReadSyncWithoutReusingActions(libKoin)
            // Run eager stateIn/launch collectors as well as constructor-time resolution.
            runCurrent()
        } finally {
            // Never create a logger during failed startup or obscure the original failure at teardown.
            app.koin.instanceRegistry.instances.values.filter {
                it.beanDefinition.primaryType == coredevices.coreapp.util.FileLogWriter::class && it.isCreated()
            }.forEach { runCatching { app.koin.get<coredevices.coreapp.util.FileLogWriter>().close() } }
            stopKoin()
            library?.close()
            loader.close()
            osConstructors.asReversed().forEach { it.close() }
            Dispatchers.resetMain()
            directory.deleteRecursively()
        }
    }

    private fun permissionSnapshotsKeepReadSyncWithoutReusingActions(koin: Koin) {
        val handler = koin.get<io.rebble.libpebblecommon.io.rebble.libpebblecommon.notification.NotificationHandler>()
        val previous = kotlin.uuid.Uuid.random()
        val current = io.rebble.libpebblecommon.io.rebble.libpebblecommon.notification.LibPebbleNotification(
            packageName = "com.orbcybersecurity.orb", uuid = kotlin.uuid.Uuid.random(), groupKey = null,
            key = "permission-snapshot", timestamp = kotlin.time.Instant.fromEpochMilliseconds(0), title = "Requests",
            body = "Location and Internet", icon = io.rebble.libpebblecommon.packets.blobdb.TimelineIcon.NotificationReminder,
            actions = emptyList(), people = emptyList(), vibrationPattern = null,
            previousUuids = listOf(previous), canUsePreviousActions = false,
        )
        val field = handler.javaClass.getDeclaredField("inflightNotifications").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        val inflight = field.get(handler) as MutableMap<String, Any>
        inflight[current.key] = current
        assertSame(current, handler.getNotification(current.uuid))
        assertNull(handler.getNotification(previous))
        val removed = Mockito.mock(android.service.notification.StatusBarNotification::class.java)
        Mockito.`when`(removed.key).thenReturn(current.key)
        Mockito.`when`(removed.packageName).thenReturn(current.packageName)
        handler.handleNotificationRemoved(removed)
        assertEquals(current.uuid, handler.notificationDeleteQueue.tryReceive().getOrNull())
        assertEquals(previous, handler.notificationDeleteQueue.tryReceive().getOrNull())
    }

    private fun resolveSingletons(koin: Koin) {
        koin.instanceRegistry.instances.values.toSet().forEach { factory ->
            val bean = factory.beanDefinition
            if (bean.kind == Kind.Singleton) koin.get<Any>(bean.primaryType, bean.qualifier)
        }
    }
}

/** Empty Room boundary with real DAO interfaces and deterministic empty flows. */
private class EmptyDatabase {
    private val instances = mutableMapOf<Class<*>, Any>()
    fun <T : Any> mock(type: Class<T>): T {
        @Suppress("UNCHECKED_CAST")
        return instances.getOrPut(type) {
            Mockito.mock(type, Answer { call ->
                val result = call.method.returnType
                when {
                    Flow::class.java.isAssignableFrom(result) -> MutableStateFlow(emptyValue(
                        (call.method.genericReturnType as ParameterizedType).actualTypeArguments[0]))
                    result == Any::class.java && call.method.parameterTypes.lastOrNull()?.name == "kotlin.coroutines.Continuation" -> {
                        val continuation = call.method.genericParameterTypes.last() as ParameterizedType
                        emptyValue(continuation.actualTypeArguments[0])
                    }
                    result.name.endsWith("Dao") -> mock(result)
                    else -> Mockito.RETURNS_DEFAULTS.answer(call)
                }
            })
        } as T
    }

    private fun emptyValue(type: Type): Any? = when (type) {
        is WildcardType -> emptyValue(type.lowerBounds.firstOrNull() ?: type.upperBounds.first())
        is ParameterizedType -> emptyValue(type.rawType)
        List::class.java, Collection::class.java -> emptyList<Any>()
        Set::class.java -> emptySet<Any>()
        Map::class.java -> emptyMap<Any, Any>()
        Boolean::class.javaObjectType -> false
        Int::class.javaObjectType -> 0
        Long::class.javaObjectType -> 0L
        kotlin.Unit::class.java -> Unit
        else -> null
    }
}
