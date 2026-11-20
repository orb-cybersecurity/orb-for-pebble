package io.rebble.libpebblecommon.js

import co.touchlab.kermit.LogWriter
import co.touchlab.kermit.Logger
import co.touchlab.kermit.Severity
import io.rebble.libpebblecommon.connection.ConnectedPebbleDevice
import io.rebble.libpebblecommon.connection.FakeAppMessages
import io.rebble.libpebblecommon.connection.fakeWatch
import io.rebble.libpebblecommon.database.entity.LockerEntry
import io.rebble.libpebblecommon.metadata.pbw.appinfo.PbwAppInfo
import io.rebble.libpebblecommon.metadata.pbw.appinfo.Resources
import io.rebble.libpebblecommon.permissions.NetworkAccess
import io.rebble.libpebblecommon.plugin.PluginNetworkVerdict
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.runTest
import kotlinx.io.files.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.uuid.Uuid

class ConfigUrlLoggingTest {
    @Test fun refusedConfigUrlsNeverWriteTheirReasonOrAppSuppliedText() = runTest {
        val watch = fakeWatch(connected = true) as ConnectedPebbleDevice
        val info = PbwAppInfo(Uuid.NIL.toString(), "secret-app-name", versionLabel = "1", resources = Resources())
        val entry = LockerEntry(Uuid.NIL, "1", "test", "watchapp", "test", true, "1", platforms = emptyList())
        val runner = object : JsRunner(info, entry, Path("unused"),
            CompanionAppDevice(watch.identifier, watch.watchInfo, FakeAppMessages()), Channel()) {
            override val networkAccess = NetworkAccess { url, _ -> PluginNetworkVerdict.Denied("'$url' can't be requested") }
            override suspend fun start() {}
            override suspend fun stop() {}
            override suspend fun loadAppJs(jsUrl: String) {}
            override suspend fun signalInterceptResponse(callbackId: String, result: InterceptResponse) {}
            override suspend fun signalNewAppMessageData(data: String?) = true
            override suspend fun signalAudioStream(json: String) {}
            override suspend fun signalTimelineToken(callId: String, token: String) {}
            override suspend fun signalTimelineTokenFail(callId: String) {}
            override suspend fun signalReady() {}
            override suspend fun signalShowConfiguration() {}
            override suspend fun signalWebviewClosed(data: String?) {}
            override suspend fun signalConfigMessage(requestId: Int, json: String) {}
            override suspend fun eval(js: String) {}
            override suspend fun evalWithResult(js: String): Any? = null
            override fun debugForceGC() {}
        }
        val oldWriters = Logger.config.logWriterList
        val oldSeverity = Logger.config.minSeverity
        val logs = mutableListOf<String>()
        Logger.setLogWriters(object : LogWriter() {
            override fun log(severity: Severity, message: String, tag: String, throwable: Throwable?) {
                if (tag == "JsRunner") {
                    logs += message
                    assertNull(throwable)
                }
            }
        })
        Logger.setMinSeverity(Severity.Verbose)
        try {
            assertFalse(runner.mayOpen("https://127.1/settings?token=secret#payload"))
            assertEquals(listOf("Config page refused host=127.1"), logs)
        } finally {
            Logger.setLogWriters(oldWriters)
            Logger.setMinSeverity(oldSeverity)
        }
    }
}
