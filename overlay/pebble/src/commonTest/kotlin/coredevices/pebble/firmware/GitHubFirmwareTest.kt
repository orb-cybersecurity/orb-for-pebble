package coredevices.pebble.firmware

import com.russhwolf.settings.MapSettings
import coredevices.util.sha256
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import io.rebble.libpebblecommon.util.Crc32Calculator
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

private const val BOARD = "asterix"

class GitHubFirmwareTest {
    @Test
    fun newestVersionComesFirstWhateverTheOrderOfPublication() {
        val releases = listOf(release("v4.27.5"), release("v4.46.0"), release("v4.44.4"))
        assertEquals(
            listOf("v4.46.0", "v4.44.4", "v4.27.5"),
            firmwareCandidates(releases, BOARD, running = null).map { it.tag },
        )
    }

    @Test
    fun onlyVersionsNewerThanTheRunningOneAreCandidates() {
        val releases = listOf(release("v4.46.0"), release("v4.44.4"), release("v4.27.5"))
        assertEquals(listOf("v4.46.0"), firmwareCandidates(releases, BOARD, running = "v4.44.4").map { it.tag })
        assertEquals(emptyList(), firmwareCandidates(releases, BOARD, running = "v4.46.0"))
    }

    @Test
    fun aWatchRunningADevBuildIsLeftAlone() {
        assertEquals(emptyList(), firmwareCandidates(listOf(release("v4.46.0")), BOARD, running = "v4.44.4-3-gabc123"))
    }

    @Test
    fun releasesFailingTheMetadataChecksAreNotCandidates() {
        val releases = listOf(
            release("v4.50.0", draft = true),
            release("v4.49.0", prerelease = true),
            release("v4.9.142.12"),
            release("v4.48.0", board = "obelix_pvt"),
            release("v4.47.0", digest = null),
            release("v4.46.1", state = "starter"),
            release("v4.46.0"),
        )
        assertEquals(listOf("v4.46.0"), firmwareCandidates(releases, BOARD, running = null).map { it.tag })
        assertEquals("draft release", metadataProblem(releases[0], BOARD))
        assertEquals("marked as a pre-release", metadataProblem(releases[1], BOARD))
        assertEquals("not a release tag", metadataProblem(releases[2], BOARD))
        assertEquals("no normal_asterix_v4.48.0.pbz", metadataProblem(releases[3], BOARD))
        assertEquals("no SHA-256 digest published", metadataProblem(releases[4], BOARD))
        assertEquals("bundle upload incomplete", metadataProblem(releases[5], BOARD))
    }

    @Test
    fun aGoodBundlePasses() {
        val bundle = pbz("v4.46.0")
        assertNull(bundleProblem(bundle, candidate("v4.46.0", bundle), BOARD))
    }

    @Test
    fun bundleChecksCatchCorruptionAndMislabelling() {
        val good = pbz("v4.46.0")
        val tampered = good.copyOf().also { it[it.size / 2] = (it[it.size / 2] + 1).toByte() }
        assertEquals(
            "SHA-256 does not match the published digest",
            bundleProblem(tampered, candidate("v4.46.0", good), BOARD),
        )
        val otherBoard = pbz("v4.46.0", board = "obelix_pvt")
        assertEquals("built for obelix_pvt", bundleProblem(otherBoard, candidate("v4.46.0", otherBoard), BOARD))
        val otherVersion = pbz("v4.45.0")
        assertEquals("bundle says v4.45.0", bundleProblem(otherVersion, candidate("v4.46.0", otherVersion), BOARD))
        val badCrc = pbz("v4.46.0", crcOffset = 1)
        assertEquals("firmware CRC mismatch", bundleProblem(badCrc, candidate("v4.46.0", badCrc), BOARD))
        val notAZip = "not a zip".encodeToByteArray()
        assertTrue(bundleProblem(notAZip, candidate("v4.46.0", notAZip), BOARD)!!.startsWith("unreadable bundle"))
    }

    @Test
    fun aFailingNewestReleaseFallsBackToTheNextOne() = runTest {
        val broken = pbz("v4.45.0") // published as v4.46.0: fails the version check
        val good = pbz("v4.45.0")
        val server = FakeGitHub(
            release("v4.46.0", bundle = broken) to broken,
            release("v4.45.0", bundle = good) to good,
            release("v4.44.0", bundle = pbz("v4.44.0")) to pbz("v4.44.0"),
        )
        val result = server.api().getLatestFirmware("serial", BOARD, "v4.44.0")
        assertEquals("v4.45.0", result?.version)
        assertEquals(bundleUrl("v4.45.0"), result?.artifacts?.single()?.url)
    }

    @Test
    fun noUpdateWhenEveryNewerReleaseFails() = runTest {
        val broken = pbz("v4.40.0")
        val server = FakeGitHub(
            release("v4.46.0", bundle = broken) to broken,
            release("v4.45.0", bundle = broken) to broken,
            release("v4.44.0", bundle = pbz("v4.44.0")) to pbz("v4.44.0"),
        )
        assertNull(server.api().getLatestFirmware("serial", BOARD, "v4.44.0"))
    }

    @Test
    fun aBundleIsDownloadedAndCheckedOncePerSession() = runTest {
        val good = pbz("v4.46.0")
        val server = FakeGitHub(release("v4.46.0", bundle = good) to good)
        val api = server.api()
        api.getLatestFirmware("serial", BOARD, "v4.44.0")
        api.getLatestFirmware("serial", BOARD, "v4.44.0")
        assertEquals(1, server.bundleDownloads)
    }

    @Test
    fun aPinnedVersionIsOfferedEvenWhenOlder() = runTest {
        val newest = pbz("v4.46.0")
        val older = pbz("v4.44.4")
        val server = FakeGitHub(release("v4.46.0", bundle = newest) to newest, release("v4.44.4", bundle = older) to older)
        val settings = MapSettings(GitHubFirmwareApi.PINNED_FIRMWARE_KEY to "4.44.4")
        assertEquals("v4.44.4", server.api(settings).getLatestFirmware("serial", BOARD, "v4.46.0")?.version)
        assertNull(server.api(settings).getLatestFirmware("serial", BOARD, "v4.44.4"))
    }

    @Test
    fun aPinnedVersionThatFailsItsChecksIsAnError() = runTest {
        val broken = pbz("v4.40.0")
        val server = FakeGitHub(release("v4.44.4", bundle = broken) to broken)
        val settings = MapSettings(GitHubFirmwareApi.PINNED_FIRMWARE_KEY to "v4.44.4")
        assertFailsWith<IllegalStateException> { server.api(settings).getLatestFirmware("serial", BOARD, "v4.46.0") }
        val missing = MapSettings(GitHubFirmwareApi.PINNED_FIRMWARE_KEY to "v9.9.9")
        assertFailsWith<IllegalStateException> { server.api(missing).getLatestFirmware("serial", BOARD, "v4.46.0") }
    }
}

private class FakeGitHub(vararg releases: Pair<GitHubRelease, ByteArray>) {
    private val releaseList = releases.map { it.first }
    private val bundles = releases.associate { (release, bytes) -> release.assets.single().url to bytes }
    var bundleDownloads = 0

    fun api(settings: MapSettings = MapSettings()) = GitHubFirmwareApi(
        HttpClient(MockEngine { request ->
            val url = request.url.toString()
            when {
                url.startsWith("https://api.github.com/repos/coredevices/PebbleOS/releases") -> respond(
                    Json.encodeToString(releaseList),
                    headers = headersOf(HttpHeaders.ContentType, "application/json"),
                )
                url in bundles -> {
                    bundleDownloads++
                    respond(bundles.getValue(url))
                }
                else -> respondError(HttpStatusCode.NotFound)
            }
        }) {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
        },
        settings,
    )
}

private fun bundleUrl(tag: String, board: String = BOARD) =
    "https://github.com/coredevices/PebbleOS/releases/download/$tag/${bundleName(board, tag)}"

private fun release(
    tag: String,
    draft: Boolean = false,
    prerelease: Boolean = false,
    board: String = BOARD,
    bundle: ByteArray = ByteArray(1000),
    digest: String? = "sha256:" + sha256(bundle).toHexString(),
    state: String = "uploaded",
) = GitHubRelease(
    tagName = tag,
    draft = draft,
    prerelease = prerelease,
    assets = listOf(GitHubAsset(bundleName(board, tag), bundleUrl(tag, board), bundle.size.toLong(), state, digest)),
)

private fun candidate(tag: String, bundle: ByteArray) =
    FirmwareCandidate(tag, ReleaseVersion.parse(tag)!!, release(tag, bundle = bundle).assets.single())

/** A single-slot bundle as PebbleOS's build produces it, with [crcOffset] added to the recorded CRC. */
private fun pbz(tag: String, board: String = BOARD, crcOffset: Long = 0): ByteArray {
    val firmware = ByteArray(4096) { (it * 31 + tag.length).toByte() }
    val crc = Crc32Calculator().apply { addBytes(firmware.asUByteArray()) }.finalize().toLong() + crcOffset
    val manifest = """{"manifestVersion":2,"generatedAt":1,"firmware":{"name":"pebbleos.bin","type":"normal",""" +
        """"timestamp":1,"commit":"abc","hwrev":"$board","size":${firmware.size},"crc":$crc,"versionTag":"$tag"},"type":"firmware"}"""
    return storedZip(listOf("manifest.json" to manifest.encodeToByteArray(), "pebbleos.bin" to firmware))
}

private fun storedZip(files: List<Pair<String, ByteArray>>): ByteArray {
    var local = ByteArray(0)
    var central = ByteArray(0)
    for ((name, data) in files) {
        val n = name.encodeToByteArray()
        val crc = zipCrc(data)
        val offset = local.size
        local += le32(0x04034b50) + le16(20) + le16(0) + le16(0) + le16(0) + le16(0) +
            le32(crc) + le32(data.size) + le32(data.size) + le16(n.size) + le16(0) + n + data
        central += le32(0x02014b50) + le16(20) + le16(20) + le16(0) + le16(0) + le16(0) + le16(0) +
            le32(crc) + le32(data.size) + le32(data.size) + le16(n.size) + le16(0) + le16(0) +
            le16(0) + le16(0) + le32(0) + le32(offset) + n
    }
    val end = le32(0x06054b50) + le16(0) + le16(0) + le16(files.size) + le16(files.size) +
        le32(central.size) + le32(local.size) + le16(0)
    return local + central + end
}

private fun le16(v: Int) = byteArrayOf(v.toByte(), (v shr 8).toByte())
private fun le32(v: Int) = byteArrayOf(v.toByte(), (v shr 8).toByte(), (v shr 16).toByte(), (v shr 24).toByte())
private fun le32(v: Long) = le32(v.toInt())

private fun zipCrc(data: ByteArray): Long {
    var crc = 0xFFFFFFFFL
    for (b in data) {
        crc = crc xor (b.toLong() and 0xFF)
        repeat(8) { crc = if (crc and 1L != 0L) (crc ushr 1) xor 0xEDB88320L else crc ushr 1 }
    }
    return crc xor 0xFFFFFFFFL
}
