package coredevices.coreapp.ui.screens

import DocumentAttachment
import co.touchlab.kermit.Logger
import com.oldguy.common.io.File
import com.oldguy.common.io.FileMode
import com.oldguy.common.io.ZipEntry
import com.oldguy.common.io.ZipFile
import com.russhwolf.settings.Settings
import coredevices.CoreBackgroundSync
import coredevices.coreapp.util.FileLogWriter
import coredevices.coreapp.util.generateDeviceSummaryPlatformDetails
import coredevices.coreapp.util.getLogsCacheDir
import coredevices.pebble.PebbleAppDelegate
import coredevices.util.CompanionDevice
import coredevices.util.CoreConfigFlow
import coredevices.util.PermissionRequester
import coredevices.util.models.CactusSTTMode
import coredevices.util.storage.appStorageBreakdown
import coredevices.util.storage.formatStorageSummary
import coredevices.util.transcription.HybridTranscriptionService
import io.rebble.libpebblecommon.connection.AppContext
import io.rebble.libpebblecommon.connection.KnownPebbleDevice
import io.rebble.libpebblecommon.connection.LibPebble
import io.rebble.libpebblecommon.util.getTempFilePath
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.IO
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.io.Buffer
import kotlinx.io.Source
import kotlinx.io.buffered
import kotlinx.io.files.Path
import kotlinx.io.files.SystemFileSystem
import kotlinx.io.readByteArray
import kotlinx.io.readString
import kotlinx.io.writeString
import org.koin.mp.KoinPlatform
import size
import kotlin.time.Clock

data class BugReportGenerationParams(
    val userMessage: String,
    val userName: String?,
    val userEmail: String?,
    val screenContext: String,
    val attachments: List<DocumentAttachment>,
    val imageAttachments: List<DocumentAttachment>,
    val fetchPebbleLogs: Boolean,
    val fetchPebbleCoreDump: Boolean,
    val shareLocally: Boolean,
)

sealed class BugReportState {
    data object Creating : BugReportState()
    data object GatheringWatchLogs : BugReportState()
    data object UploadingAttachments : BugReportState()
    sealed class BugReportResult : BugReportState() {
        data class Success(val bugReportId: String? = null) : BugReportResult()
        data class Failed(val error: String) : BugReportResult()
    }
    data class ReadyToShare(
        val name: String,
        val file: Path,
    ) : BugReportState()
}

class BugReportProcessor(
    private val logWriter: FileLogWriter,
    private val pebbleAppDelegate: PebbleAppDelegate,
    private val clock: Clock,
    private val appContext: AppContext,
    private val coreBackgroundSync: CoreBackgroundSync,
    private val settings: Settings,
    private val libPebble: LibPebble,
    private val coreConfigFlow: CoreConfigFlow,
    private val permissionRequester: PermissionRequester,
    private val companionDevice: CompanionDevice,
) {
    private val logger = Logger.withTag("BugReportProcessor")

    private fun getPKJSSummary(): String {
        return try {
            pebbleAppDelegate.getPKJSSessions()
        } catch (e: Exception) {
            logger.e(e) { "Error grabbing PKJS sessions: ${e.message}" }
            "Error grabbing PKJS sessions\n"
        }
    }

    private fun getSTTSummary(): String {
        return try {
            // Lazy grab in case of init issues
            val transcriptionService = KoinPlatform.getKoin().get<HybridTranscriptionService>()
            val lastModel = transcriptionService.lastModelUsed
            val configuredMode = transcriptionService.configuredMode
            val configuredLanguage = transcriptionService.configuredLanguage ?: "Auto/Not specified"
            val lastSuccessfulMode = when (transcriptionService.lastSuccessfulMode) {
                CactusSTTMode.LocalOnly, CactusSTTMode.LocalFirst -> "Local"
                CactusSTTMode.RemoteOnly, CactusSTTMode.RemoteFirst -> "Remote"
                CactusSTTMode.RebbleOnly, CactusSTTMode.RebbleFirst, CactusSTTMode.RebbleFallback -> "Rebble"
                CactusSTTMode.PlatformOnly -> "Platform"
                null -> "None"
            }
            "\nSTT Summary\n" +
                    "Configured mode: $configuredMode\n" +
                    "Configured language: $configuredLanguage\n" +
                    "Last model used: $lastModel\n" +
                    "Last successful mode: $lastSuccessfulMode\n"
        } catch (e: Exception) {
            logger.e(e) { "Error grabbing STT sessions: ${e.message}" }
            "Error grabbing STT sessions\n"
        }
    }

    private suspend fun getPebbleLogFile(): List<DocumentAttachment> {
        val logFile = pebbleAppDelegate.getWatchLogs()
        return if (logFile != null) {
            withContext(Dispatchers.IO) {
                listOf(
                    DocumentAttachment(
                        fileName = "watch-logs.txt",
                        mimeType = "text/plain",
                        source = SystemFileSystem.source(logFile).buffered(),
                        size = logFile.size(),
                    )
                )
            }
        } else {
            emptyList()
        }
    }

    private suspend fun getPebbleCoreDump(): List<DocumentAttachment> {
        val coreDumpFile = pebbleAppDelegate.getCoreDump()
        return if (coreDumpFile != null) {
            withContext(Dispatchers.IO) {
                listOf(
                    DocumentAttachment(
                        fileName = "core-dump-unencrypted.bin",
                        mimeType = null,
                        source = SystemFileSystem.source(coreDumpFile).buffered(),
                        size = coreDumpFile.size(),
                    )
                )
            }
        } else {
            emptyList()
        }
    }

    private suspend fun createSummaryAttachment(attachments: List<DocumentAttachment>): DocumentAttachment {
        val summaryWithAttachmentCount =
            createSummary("", attachments)
        val logsDir = Path(getLogsCacheDir())
        if (!SystemFileSystem.exists(logsDir)) {
            SystemFileSystem.createDirectories(logsDir)
        }
        val summaryFile = Path(getLogsCacheDir() + "/summary.txt")
        SystemFileSystem.sink(summaryFile, append = false).buffered().use { sink ->
            sink.writeString(summaryWithAttachmentCount)
        }
        return DocumentAttachment(
            fileName = "bugreport_summary.txt",
            mimeType = "text/plain",
            source = SystemFileSystem.source(summaryFile).buffered(),
            size = summaryFile.size(),
        )
    }

    private suspend fun createSummary(
        screenContext: String,
        attachments: List<DocumentAttachment>,
    ): String {
        val deviceSummary = generateDeviceSummaryPlatformDetails()
        val pkjsSummary = getPKJSSummary()
        val sttSummary = getSTTSummary()
        val pebbleContext = pebbleScreenContext()
        val storageSummary = withContext(Dispatchers.IO) {
            formatStorageSummary(appContext.appStorageBreakdown())
        }
        val summaryWithAttachmentCount = buildString {
            append(deviceSummary)
            append(pkjsSummary)
            append(sttSummary)
            if (pebbleContext.isNotEmpty()) {
                append("\n${pebbleContext}")
            }
            if (screenContext.isNotEmpty()) {
                append("\n${screenContext}")
            }
            attachments.onEach {
                append("\nAttachment: ${it.fileName}")
            }
            append("\nTime since last full background sync: ${coreBackgroundSync.timeSinceLastSync()}")
            append(storageSummary)
        }
        return summaryWithAttachmentCount
    }


    /**
     * Orb: the report becomes a zip file for the user to share. Core's upload to its support
     * backend needs a Core account, so it is removed; `params.shareLocally` is always true.
     */
    fun newBugReport(params: BugReportGenerationParams): Flow<BugReportState> {
        val state = MutableSharedFlow<BugReportState>(replay = 1, extraBufferCapacity = Int.MAX_VALUE)
        state.tryEmit(BugReportState.Creating)
        GlobalScope.launch(Dispatchers.IO) {
            try {
                state.tryEmit(createReportFile(params, state))
            } catch (e: Exception) {
                logger.e(e) { "Unhandled exception in bug report processing" }
                state.tryEmit(BugReportState.BugReportResult.Failed("An unexpected error occurred"))
            }
        }
        return state
    }

    private suspend fun createReportFile(
        params: BugReportGenerationParams,
        state: MutableSharedFlow<BugReportState>,
    ): BugReportState.ReadyToShare {
        val summaryWithAttachmentCount =
            createSummary(
                params.screenContext,
                params.attachments + params.imageAttachments,
            )
        val logs = logWriter.dumpLogs()
        val attachments = gatherAttachments(params, state) + DocumentAttachment(
            fileName = "full_logs.txt",
            mimeType = "text/plain",
            source = SystemFileSystem.source(logs).buffered(),
            size = logs.size(),
        )
        // A zip file holding all the attachments and the summary.
        val timestamp = clock.now()
        val filename = "bug-report-$timestamp.zip"
        val bugReportFile = getTempFilePath(appContext, filename, "bugreports")
        val zipFile = ZipFile(File(bugReportFile.toString()), mode = FileMode.Write)
        val summaryByteArray = summaryWithAttachmentCount.encodeToByteArray()
        val localAttachments = attachments + DocumentAttachment(
            fileName = "summary.json",
            mimeType = "application/json",
            source = sourceFromByteArray(summaryByteArray),
            size = summaryByteArray.size.toLong(),
        )
        zipFile.use {
            localAttachments.forEach {
                zipFile.addEntry(ZipEntry(it.fileName), { it.source.readByteArray() })
            }
        }
        return BugReportState.ReadyToShare(name = filename, file = bugReportFile)
    }

    fun sourceFromByteArray(byteArray: ByteArray): Source {
        val buffer = Buffer()
        buffer.write(byteArray)
        return buffer
    }

    private suspend fun gatherAttachments(
        params: BugReportGenerationParams,
        state: MutableSharedFlow<BugReportState>
    ): List<DocumentAttachment> {
        // Phase 2: Gather attachments (including watch logs/core dump)
        state.tryEmit(BugReportState.GatheringWatchLogs)

        // Add full logs as the first attachment (if available)
        val attachments = mutableListOf<DocumentAttachment>()

        // Add user attachments
        attachments.addAll(params.attachments)
        attachments.addAll(params.imageAttachments)

        val screenContextByteArray = params.screenContext.encodeToByteArray()
        attachments.add(
            DocumentAttachment(
                fileName = "screen-context.json",
                mimeType = "application/json",
                source = sourceFromByteArray(screenContextByteArray),
                size = screenContextByteArray.size.toLong(),
            )
        )

        if (params.fetchPebbleLogs) {
            attachments.addAll(getPebbleLogFile())
        }
        if (params.fetchPebbleCoreDump) {
            attachments.addAll(getPebbleCoreDump())
        }
        return attachments
    }

    suspend fun pebbleScreenContext(): String {
        val watches = libPebble.watches.value.sortedByDescending {
            when (it) {
                is KnownPebbleDevice -> it.lastConnected.epochSeconds
                else -> 0
            }
        }
        val lastConnectedWatch = watches.firstOrNull() as? KnownPebbleDevice
        val watchesWithoutCompanionDevicePermission = watches.mapNotNull {
            if (it is KnownPebbleDevice && !companionDevice.hasApprovedDevice(it.identifier)) {
                "[${it.identifier} / ${it.name}]"
            } else {
                null
            }
        }
        return buildString {
            appendLine("lastConnectedFirmwareVersion: ${lastConnectedWatch?.runningFwVersion}")
            appendLine("lastConnectedSerial: ${lastConnectedWatch?.serial}")
            appendLine("lastConnectedWatchType: ${lastConnectedWatch?.watchType}")
            appendLine("activeWatchface: ${libPebble.activeWatchface.value?.let {
                "${it.properties.id} / ${it.properties.title}"
            }}")
            appendLine("otherPebbleApps: ${libPebble.otherPebbleCompanionAppsInstalled().value}")
            appendLine("libPebbleConfig: ${libPebble.config.value}")
            appendLine("coreConfig: ${coreConfigFlow.value}")
            appendLine("watch prefs: ${
                libPebble.watchPrefs.first().joinToString(", ") { "${it.pref.id}=${it.value}" }
            }")
            appendLine("missingPermissions: ${permissionRequester.missingPermissions.value}")
            appendLine("watchesWithoutCompanionDevicePermission: $watchesWithoutCompanionDevicePermission")
            appendLine(libPebble.watchesDebugState())
            appendLine("Watches (most recently connected first):")
            watches.forEachIndexed { index, watch ->
                appendLine("watch_$index $watch")
            }
        }
    }
}

fun Path?.readMostRecent(bytes: Int): String? {
    if (this == null) return null
    return try {
        SystemFileSystem.source(this).buffered().use { source ->
            val size = SystemFileSystem.metadataOrNull(this)?.size ?: 0
            val offset = maxOf(0, size - bytes)
            source.skip(offset)
            source.readString()
        }
    } catch (e: Exception) {
        Logger.e(e) { "Failed to read most recent $bytes bytes from $this" }
        null
    }
}

