package io.rebble.libpebblecommon.web

import co.touchlab.kermit.Logger
import io.ktor.client.HttpClient
import io.ktor.client.request.prepareGet
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.isSuccess
import io.ktor.utils.io.readRemaining
import io.rebble.libpebblecommon.connection.AppContext
import io.rebble.libpebblecommon.locker.getLockerPBWCacheDirectory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.io.IOException
import kotlinx.io.files.Path
import kotlinx.io.buffered
import kotlinx.io.files.SystemFileSystem
import kotlinx.io.readByteArray
import okio.ByteString.Companion.toByteString
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

class FirmwareDownloader(
    private val httpClient: HttpClient,
    private val appContext: AppContext,
) {
    private val logger = Logger.withTag("FirmwareDownloader")
    private val fwDir = getFirmwareDownloadDirectory(appContext)

    init {
        // No in-memory install survives a process restart. Remove old downloads, including
        // those written to the PBW directory by earlier versions, before accepting new work.
        for (directory in setOf(fwDir, getLockerPBWCacheDirectory(appContext))) {
            if (SystemFileSystem.exists(directory)) {
                SystemFileSystem.list(directory).filter { isFirmwareDownload(it) }.forEach(::discardFirmwareDownload)
            }
        }
    }

    internal fun discardDownload(path: Path) {
        if (path.parent == fwDir) discardFirmwareDownload(path)
    }

    suspend fun downloadFirmware(url: String, type: String): Path? {
        val path = Path(fwDir, "download-${kotlin.uuid.Uuid.random()}.$type")
        var complete = false
        return try {
            val downloaded = withTimeoutOrNull(30.seconds) {
                val rawUrl = url.substringBefore('#')
                val github = url.substringAfter('#', "").split('&').contains("orb-github")
                val digest = url.substringAfter("#orb-sha256=", "").substringBefore('&')
                require(type == "pbl" || Regex("[0-9a-f]{64}").matches(digest)) { "Missing firmware digest" }
                require(firmwareDownloadUrlAllowed(rawUrl, github)) { "Invalid download URL" }
                httpClient.prepareGet(rawUrl).execute { response ->
                    require(response.status.isSuccess()) { "Firmware download failed" }
                    require(firmwareDownloadUrlAllowed(response.call.request.url.toString(), github)) { "Invalid final URL" }
                    val bytes = response.bodyAsChannel().readRemaining(MAX_FIRMWARE_BYTES + 1).readByteArray()
                    require(bytes.size.toLong() <= MAX_FIRMWARE_BYTES) { "Firmware too large" }
                    if (digest.isNotEmpty()) require(bytes.toByteString().sha256().hex() == digest) { "Firmware digest mismatch" }
                    SystemFileSystem.sink(path).buffered().use { it.write(bytes) }
                }
                path
            }
            complete = downloaded != null
            downloaded
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (_: Exception) {
            logger.w { "Firmware download refused" }
            null
        } finally {
            if (!complete) SystemFileSystem.delete(path, mustExist = false)
        }
    }

}

expect fun getFirmwareDownloadDirectory(context: AppContext): Path

suspend fun <T> withTimeoutOr(timeout: Duration, block: suspend CoroutineScope.() -> T, onTimeout: () -> T): T {
    return try {
        withTimeout(timeout, block)
    } catch (e: TimeoutCancellationException) {
        onTimeout()
    }
}

internal fun isFirmwareDownload(path: Path): Boolean =
    path.name in setOf("download.pbz", "download.pbl", "language.pbl") || Regex("download-[0-9a-fA-F-]+\\.(pbz|pbl)").matches(path.name)

internal fun discardFirmwareDownload(path: Path) {
    if (!isFirmwareDownload(path)) return
    try {
        SystemFileSystem.delete(path, mustExist = false)
    } catch (_: Exception) {
        Logger.withTag("FirmwareDownloader").w { "Could not remove temporary firmware download" }
    }
}
