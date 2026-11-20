package coredevices.coreapp

import com.russhwolf.settings.MapSettings
import com.russhwolf.settings.Settings
import coredevices.coreapp.di.androidDefaultModule
import coredevices.coreapp.di.utilModule
import coredevices.coreapp.ui.screens.BugReportProcessor
import coredevices.pebble.PebbleAppDelegate
import coredevices.pebble.firmware.FirmwareUpdateUiTracker
import coredevices.pebble.firmware.RealFirmwareUpdateUiTracker
import coredevices.pebble.permissions.PermissionRequestNotifier
import coredevices.pebble.services.HybridTranscription
import coredevices.pebble.services.STTRouter
import coredevices.pebble.watchModule
import coredevices.util.AndroidPermissionRequester
import coredevices.util.CoreConfig
import coredevices.util.CoreConfigFlow
import coredevices.util.CoreConfigHolder
import coredevices.util.PermissionRequester
import coredevices.util.transcription.HybridTranscriptionService
import io.rebble.libpebblecommon.voice.TranscriptionProvider
import java.lang.reflect.Proxy
import kotlinx.serialization.json.Json
import org.koin.dsl.bind
import org.koin.dsl.koinApplication
import org.koin.dsl.module
import kotlin.reflect.KClass
import kotlin.test.Test
import kotlin.test.assertIs
import kotlin.time.Clock

/** Resolve production bindings, replacing only OS/data boundaries; never start those services. */
class RemovedIntegrationGraphTest {
    @Test fun retainedAppBindingsResolveWithoutTheRemovedIntegrations() {
        val roots = listOf(CommonAppDelegate::class.java, BugReportProcessor::class.java,
            PebbleAppDelegate::class.java, RealFirmwareUpdateUiTracker::class.java,
            PermissionRequestNotifier::class.java, HybridTranscription::class.java,
            HybridTranscriptionService::class.java, STTRouter::class.java)
        val rootInterfaces = setOf(FirmwareUpdateUiTracker::class.java,
            coredevices.CoreBackgroundSync::class.java, TranscriptionProvider::class.java)
        val allowed = setOf("Settings", "Clock", "AppContext", "LibPebble", "WeatherFetcher",
            "PlatformHealthSync", "CoreConfigHolder", "CoreConfigFlow", "PermissionRequester",
            "CompanionDevice", "FileLogWriter", "PlatformSpeechRecognizer", "AudioFrameDecoder",
            "RebbleAsrTranscription", "AppResumed", "DoneInitialOnboarding", "WeatherLocationDao",
            "AppstoreSourceInitializer", "Platform", "PebbleWebServices", "BatteryChargedNotifier",
            "Plugins", "WeatherPlugin", "PreferencesPlugin", "VisibleConfigPage", "LanguagePackRepository")
        val unsafe = sun.misc.Unsafe::class.java.getDeclaredField("theUnsafe").apply { isAccessible = true }
            .get(null) as sun.misc.Unsafe
        val settings = MapSettings()
        val holder = CoreConfigHolder(CoreConfig(), settings, Json { ignoreUnknownKeys = true })
        val boundaries = module {
            roots.flatMap { it.constructors.single().parameterTypes.toList() }.toSet()
                .filter { it !in roots && it !in rootInterfaces }.forEach { type ->
                    check(type.simpleName in allowed) { "Unexpected dependency: $type" }
                    val value: Any = when (type) {
                        Settings::class.java -> settings
                        Clock::class.java -> Clock.System
                        CoreConfigHolder::class.java -> holder
                        CoreConfigFlow::class.java -> CoreConfigFlow(holder.config)
                        PermissionRequester::class.java -> unsafe.allocateInstance(AndroidPermissionRequester::class.java)
                        else -> if (type.isEnum) type.enumConstants.first() else if (type.isInterface) {
                            Proxy.newProxyInstance(type.classLoader, arrayOf(type)) { _, method, _ ->
                                error("Boundary must not be used during resolution: ${type.name}.${method.name}")
                            }
                        } else unsafe.allocateInstance(type)
                    }
                    @Suppress("UNCHECKED_CAST")
                    single { value } bind (type.kotlin as KClass<Any>)
                }
        }
        val app = koinApplication { modules(androidDefaultModule, utilModule, watchModule, boundaries) }
        try {
            val koin = app.koin
            koin.get<CommonAppDelegate>()
            koin.get<BugReportProcessor>()
            koin.get<PebbleAppDelegate>()
            koin.get<PermissionRequestNotifier>()
            assertIs<RealFirmwareUpdateUiTracker>(koin.get<FirmwareUpdateUiTracker>())
            koin.get<HybridTranscription>()
            koin.get<HybridTranscriptionService>()
            assertIs<STTRouter>(koin.get<TranscriptionProvider>())
        } finally { app.close() }
    }
}
