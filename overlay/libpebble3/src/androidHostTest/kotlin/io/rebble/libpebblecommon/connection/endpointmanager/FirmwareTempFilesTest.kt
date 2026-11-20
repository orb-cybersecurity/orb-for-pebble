package io.rebble.libpebblecommon.connection.endpointmanager

import io.rebble.libpebblecommon.connection.FirmwareUpdateCheckResult
import io.rebble.libpebblecommon.connection.PebbleSocketIdentifier
import io.rebble.libpebblecommon.services.FirmwareVersion
import io.rebble.libpebblecommon.web.discardFirmwareDownload
import kotlinx.io.files.Path
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

class FirmwareTempFilesTest {
    private val watch = PebbleSocketIdentifier("test")
    private val version = FirmwareVersion.from("v4.47.2", false, "", Instant.DISTANT_PAST, false, false)!!

    private fun install(path: java.nio.file.Path, url: String = "https://example.org/firmware.pbz") = FirmwareInstall(
        FirmwareUpdateCheckResult.FoundUpdate(version, url, "test", false),
        Path(path.toString()), FirmwareUpdateTrigger.Ui,
    )

    @Test fun completingOrAbandoningAPendingDownloadDeletesIt() {
        val dir = Files.createTempDirectory("firmware-cleanup")
        try {
            for (reason in PendingFirmwareInstalls.Reason.entries) {
                val file = Files.write(dir.resolve("download-1234.pbz"), byteArrayOf(1))
                val pending = PendingFirmwareInstalls()
                pending.record(watch, install(file), reason)
                assertTrue(Files.exists(file)) // PRF handoff/resume still owns it.
                pending.clear(watch)
                assertFalse(Files.exists(file))
                pending.clear(watch) // Cleanup is idempotent.
            }
        } finally { dir.toFile().deleteRecursively() }
    }

    @Test fun replacementDeletesOnlyTheOldDownloadAndSideloadsArePreserved() {
        val dir = Files.createTempDirectory("firmware-replacement")
        try {
            val old = Files.write(dir.resolve("download-1111.pbz"), byteArrayOf(1))
            val next = Files.write(dir.resolve("download-2222.pbz"), byteArrayOf(2))
            val pending = PendingFirmwareInstalls()
            pending.record(watch, install(old))
            pending.record(watch, install(next))
            assertFalse(Files.exists(old))
            assertTrue(Files.exists(next))
            pending.record(watch, install(next), PendingFirmwareInstalls.Reason.ViaPrf)
            assertTrue(Files.exists(next))
            pending.clear(watch)
            assertFalse(Files.exists(next))
            val sideload = Files.write(dir.resolve("my-firmware.pbz"), byteArrayOf(3))
            pending.record(watch, install(sideload, url = ""))
            pending.clear(watch)
            assertTrue(Files.exists(sideload))
        } finally { dir.toFile().deleteRecursively() }
    }

    @Test fun firmwareAndLanguageCleanupIsSafeToRepeat() {
        val dir = Files.createTempDirectory("language-cleanup")
        try {
            for (name in listOf("download-abcd.pbz", "download-abcd.pbl", "download.pbz", "download.pbl", "language.pbl")) {
                val path = Files.write(dir.resolve(name), byteArrayOf(1))
                discardFirmwareDownload(Path(path.toString()))
                discardFirmwareDownload(Path(path.toString()))
                assertFalse(Files.exists(path))
            }
            val pbw = Files.write(dir.resolve("download-abcd.pbw"), byteArrayOf(2))
            discardFirmwareDownload(Path(pbw.toString()))
            assertTrue(Files.exists(pbw))
        } finally { dir.toFile().deleteRecursively() }
    }
}
