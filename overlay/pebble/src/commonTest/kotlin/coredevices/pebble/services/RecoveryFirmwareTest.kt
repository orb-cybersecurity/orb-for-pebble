package coredevices.pebble.services

import coredevices.api.EngDashArtifact
import coredevices.api.EngDashLatestResult
import coredevices.api.EngDashOtaApi
import io.rebble.libpebblecommon.connection.FirmwareUpdateCheckResult
import io.rebble.libpebblecommon.metadata.WatchColor
import io.rebble.libpebblecommon.metadata.WatchHardwarePlatform
import io.rebble.libpebblecommon.services.FirmwareVersion
import io.rebble.libpebblecommon.services.WatchInfo
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.time.Instant

class RecoveryFirmwareTest {
    private fun watch(recovery: Boolean, tag: String) = WatchInfo(
        runningFwVersion = FirmwareVersion.from("v4.47.2", recovery, "", Instant.DISTANT_PAST, false, false)!!
            .copy(stringVersion = tag),
        recoveryFwVersion = null, platform = WatchHardwarePlatform.CORE_ASTERIX,
        bootloaderTimestamp = Instant.DISTANT_PAST, board = "asterix", serial = "test", btAddress = "test",
        resourceCrc = 0, resourceTimestamp = Instant.DISTANT_PAST, language = "", languageVersion = 0,
        capabilities = emptySet(), isUnfaithful = false, healthInsightsVersion = null,
        javascriptVersion = null, color = WatchColor.ClassicBlack,
    )

    @Test fun recoveryNeverSuppliesItsVersionAsTheUpdateFloor() = runTest {
        for (tag in listOf("v4.47.2", "v9.99.0", "unparseable-recovery")) {
            var called = false
            val ota = EngDashOta(object : EngDashOtaApi {
                override suspend fun getLatestFirmware(hardwareVersion: String, currentVersion: String?): EngDashLatestResult {
                    called = true
                    assertNull(currentVersion)
                    return EngDashLatestResult("v4.47.2", artifacts = listOf(EngDashArtifact("https://example.org/fw")))
                }
            })
            assertIs<FirmwareUpdateCheckResult.FoundUpdate>(ota.getLatestFirmware(watch(true, tag)))
            assertEquals(true, called)
        }
    }

    @Test fun normalFirmwareKeepsItsVersionFloor() = runTest {
        val ota = EngDashOta(object : EngDashOtaApi {
            override suspend fun getLatestFirmware(hardwareVersion: String, currentVersion: String?): EngDashLatestResult? {
                assertEquals("v4.47.2", currentVersion)
                return null
            }
        })
        assertEquals(FirmwareUpdateCheckResult.FoundNoUpdate, ota.getLatestFirmware(watch(false, "4.47.2")))
    }
}
