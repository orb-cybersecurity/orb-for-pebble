package io.rebble.libpebblecommon.di

import io.rebble.libpebblecommon.LibPebbleConfig
import io.rebble.libpebblecommon.connection.AppContext
import io.rebble.libpebblecommon.connection.TokenProvider
import io.rebble.libpebblecommon.js.InjectedPKJSHttpInterceptors
import io.rebble.libpebblecommon.plugin.JsPluginFactory
import io.rebble.libpebblecommon.voice.TranscriptionProvider
import io.rebble.libpebblecommon.connection.WebServices
import java.lang.reflect.Proxy
import org.koin.dsl.bind
import org.koin.dsl.module
import kotlin.reflect.KClass
import kotlin.test.Test
import kotlin.test.assertNotNull

class RemovedIntegrationGraphTest {
    @Test fun pluginFactoryResolvesInTheLibraryGraphWithoutHostedOauth() {
        val unsafe = sun.misc.Unsafe::class.java.getDeclaredField("theUnsafe").apply { isAccessible = true }
            .get(null) as sun.misc.Unsafe
        fun boundary(type: Class<*>): Any = if (type.isInterface) {
            Proxy.newProxyInstance(type.classLoader, arrayOf(type)) { _, method, _ ->
                error("Boundary must not be used during resolution: ${type.name}.${method.name}")
            }
        } else unsafe.allocateInstance(type)
        val koin = initKoin(LibPebbleConfig(), boundary(WebServices::class.java) as WebServices,
            boundary(AppContext::class.java) as AppContext, boundary(TokenProvider::class.java) as TokenProvider,
            boundary(TranscriptionProvider::class.java) as TranscriptionProvider,
            boundary(InjectedPKJSHttpInterceptors::class.java) as InjectedPKJSHttpInterceptors)
        val allowed = setOf("AppContext", "LibPebbleCoroutineScope", "HttpClient", "HttpInterceptorManager",
            "AppPermissions", "RunningApps", "PluginFileAccess", "PluginFileSystem", "PluginLogs",
            "DataUsageRecorder", "PluginSources", "RemoteTimelineEmulator")
        val boundaries = module {
            JsPluginFactory::class.java.constructors.single().parameterTypes.forEach { type ->
                check(type.simpleName in allowed) { "Unexpected dependency: $type" }
                val value = boundary(type)
                @Suppress("UNCHECKED_CAST")
                single { value } bind (type.kotlin as KClass<Any>)
            }
        }
        koin.loadModules(listOf(boundaries))
        try { assertNotNull(koin.get<JsPluginFactory>()) }
        finally { koin.unloadModules(listOf(boundaries)) }
    }
}
