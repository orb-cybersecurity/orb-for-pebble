package coredevices.pebble.firmware

import co.touchlab.kermit.Logger
import com.russhwolf.settings.Settings
import coredevices.api.EngDashArtifact
import coredevices.api.EngDashLatestResult
import coredevices.api.EngDashOtaApi
import coredevices.util.sha256
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.prepareGet
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.isSuccess
import io.ktor.utils.io.readRemaining
import io.rebble.libpebblecommon.disk.pbz.DiskUtil
import io.rebble.libpebblecommon.metadata.pbz.manifest.PbzManifestWrapper
import io.rebble.libpebblecommon.util.crc32
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.io.RawSource
import kotlinx.io.buffered
import kotlinx.io.files.Path
import kotlinx.io.files.SystemFileSystem
import kotlinx.io.files.SystemTemporaryDirectory
import kotlinx.io.readByteArray
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlin.uuid.Uuid

/**
 * Orb: PebbleOS for Core's watches from Core's public releases on GitHub, since Core's own update
 * server answers only signed-in accounts.
 *
 * Releases are tried newest first. Each has to pass [metadataProblem] and, once downloaded,
 * [bundleProblem]; one that fails is skipped for the next older one, as long as that is still
 * newer than what the watch runs. A version pinned in settings ([PINNED_FIRMWARE_KEY]) replaces
 * the newest-first choice, and may be older than what the watch runs.
 */
class GitHubFirmwareApi(
    private val httpClient: HttpClient,
    private val settings: Settings,
) : EngDashOtaApi {
    private val logger = Logger.withTag("GitHubFirmware")
    private val mutex = Mutex()

    // Bundles already checked this session, by download URL: null when they passed.
    private val checked = mutableMapOf<String, String?>()

    override suspend fun getLatestFirmware(
        deviceSerial: String,
        hardwareVersion: String,
        currentVersion: String?,
        deviceMac: String?,
    ): EngDashLatestResult? = mutex.withLock {
        val releases = fetchReleases()
        val pinned = settings.getStringOrNull(PINNED_FIRMWARE_KEY)?.takeIf { it.isNotBlank() }
        if (pinned != null) {
            return@withLock pinnedRelease(releases, hardwareVersion, currentVersion, pinned)
        }
        for (candidate in firmwareCandidates(releases, hardwareVersion, currentVersion).take(MAX_TRIES)) {
            val problem = problemWith(candidate, hardwareVersion)
            if (problem == null) return@withLock candidate.asResult()
            logger.w { "Skipping PebbleOS ${candidate.tag} for $hardwareVersion: $problem" }
        }
        null
    }

    private suspend fun pinnedRelease(
        releases: List<GitHubRelease>,
        board: String,
        running: String?,
        pinned: String,
    ): EngDashLatestResult? {
        val tag = "v" + pinned.removePrefix("v")
        val release = releases.firstOrNull { it.tagName == tag }
            ?: throw IllegalStateException("PebbleOS $tag is not among Core's releases")
        if (running != null && running.removePrefix("v") == tag.removePrefix("v")) return null
        val problem = metadataProblem(release, board) ?: problemWith(candidateFrom(release, board)!!, board)
        if (problem != null) throw IllegalStateException("PebbleOS $tag can't be installed on this watch: $problem")
        return candidateFrom(release, board)!!.asResult()
    }

    private suspend fun fetchReleases(): List<GitHubRelease> {
        val response = httpClient.get(RELEASES_URL) {
            header("Accept", "application/vnd.github+json")
            parameter("per_page", 100)
        }
        check(response.status.isSuccess()) { "Couldn't list PebbleOS releases: ${response.status}" }
        return response.body()
    }

    private suspend fun problemWith(candidate: FirmwareCandidate, board: String): String? {
        val url = candidate.asset.url
        if (url in checked) return checked[url]
        val problem = try {
            bundleProblem(download(candidate.asset), candidate, board)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            // Not remembered: a failed download says nothing about the bundle.
            return "download failed: ${e.message}"
        }
        checked[url] = problem
        return problem
    }

    private suspend fun download(asset: GitHubAsset): ByteArray =
        httpClient.prepareGet(asset.url).execute { response ->
            check(response.status.isSuccess()) { "HTTP ${response.status}" }
            response.bodyAsChannel().readRemaining(asset.size + 1).readByteArray()
        }

    private fun FirmwareCandidate.asResult() = EngDashLatestResult(
        version = tag,
        notes = "PebbleOS $tag from Core's releases on GitHub.",
        artifacts = listOf(EngDashArtifact(asset.url)),
    )

    companion object {
        const val PINNED_FIRMWARE_KEY = "orb.pinnedPebbleOsVersion"
        private const val RELEASES_URL = "https://api.github.com/repos/coredevices/PebbleOS/releases"
        private const val MAX_TRIES = 5
    }
}

@Serializable
data class GitHubRelease(
    @SerialName("tag_name") val tagName: String,
    val draft: Boolean = false,
    val prerelease: Boolean = false,
    val assets: List<GitHubAsset> = emptyList(),
)

@Serializable
data class GitHubAsset(
    val name: String,
    @SerialName("browser_download_url") val url: String,
    val size: Long = 0,
    val state: String = "",
    val digest: String? = null,
)

data class FirmwareCandidate(val tag: String, val version: ReleaseVersion, val asset: GitHubAsset)

data class ReleaseVersion(val major: Int, val minor: Int, val patch: Int) : Comparable<ReleaseVersion> {
    override fun compareTo(other: ReleaseVersion): Int =
        compareValuesBy(this, other, { it.major }, { it.minor }, { it.patch })

    companion object {
        private val RELEASE = Regex("""v?(\d+)\.(\d+)\.(\d+)""")

        /** Release tags only: dev builds (v4.46.0-3-gabc123) and four-part tags are not releases. */
        fun parse(tag: String): ReleaseVersion? = RELEASE.matchEntire(tag)?.destructured?.let { (a, b, c) ->
            ReleaseVersion(a.toInt(), b.toInt(), c.toInt())
        }
    }
}

const val MAX_BUNDLE_SIZE = 32L * 1024 * 1024
private val SHA256_DIGEST = Regex("sha256:[0-9a-f]{64}")

fun bundleName(board: String, tag: String) = "normal_${board}_$tag.pbz"

/** Why [release] can't be offered for [board] without downloading anything, or null if it can. */
fun metadataProblem(release: GitHubRelease, board: String): String? {
    val asset = release.assets.firstOrNull { it.name == bundleName(board, release.tagName) }
    return when {
        release.draft -> "draft release"
        release.prerelease -> "marked as a pre-release"
        ReleaseVersion.parse(release.tagName) == null -> "not a release tag"
        asset == null -> "no ${bundleName(board, release.tagName)}"
        asset.state != "uploaded" -> "bundle upload incomplete"
        asset.size !in 1..MAX_BUNDLE_SIZE -> "implausible bundle size ${asset.size}"
        asset.digest == null || !SHA256_DIGEST.matches(asset.digest) -> "no SHA-256 digest published"
        else -> null
    }
}

private fun candidateFrom(release: GitHubRelease, board: String): FirmwareCandidate? {
    if (metadataProblem(release, board) != null) return null
    return FirmwareCandidate(
        tag = release.tagName,
        version = ReleaseVersion.parse(release.tagName)!!,
        asset = release.assets.first { it.name == bundleName(board, release.tagName) },
    )
}

/**
 * Releases to try for [board], newest first: those passing [metadataProblem] that are newer than
 * [running]. A watch without a running version (recovery firmware) can take any of them; one
 * running a build that isn't a release is left alone.
 */
fun firmwareCandidates(releases: List<GitHubRelease>, board: String, running: String?): List<FirmwareCandidate> {
    val runningVersion = running?.let { ReleaseVersion.parse(it) ?: return emptyList() }
    return releases
        .mapNotNull { candidateFrom(it, board) }
        .filter { runningVersion == null || it.version > runningVersion }
        .sortedByDescending { it.version }
}

/** Why the downloaded [bytes] of [candidate] must not go to a [board] watch, or null if fine. */
fun bundleProblem(bytes: ByteArray, candidate: FirmwareCandidate, board: String): String? {
    if (bytes.size.toLong() != candidate.asset.size) return "size ${bytes.size} != published ${candidate.asset.size}"
    if ("sha256:" + sha256(bytes).toHexString() != candidate.asset.digest) return "SHA-256 does not match the published digest"
    val path = Path(SystemTemporaryDirectory, "orb-firmware-${Uuid.random()}.pbz")
    return try {
        SystemFileSystem.sink(path).buffered().use { it.write(bytes) }
        val manifests = try {
            DiskUtil.requirePbzManifests(path)
        } catch (e: Exception) {
            return "unreadable bundle: ${e.message}"
        }
        manifests.firstNotNullOfOrNull { manifestProblem(it, candidate, board) }
    } finally {
        runCatching { SystemFileSystem.delete(path) }
    }
}

private fun manifestProblem(wrapper: PbzManifestWrapper, candidate: FirmwareCandidate, board: String): String? {
    val firmware = wrapper.manifest.firmware
    val resources = wrapper.manifest.resources
    return when {
        firmware.type != "normal" -> "firmware type ${firmware.type}"
        firmware.hwRev.revision != board -> "built for ${firmware.hwRev.revision}"
        firmware.versionTag?.removePrefix("v") != candidate.tag.removePrefix("v") ->
            "bundle says ${firmware.versionTag}"
        firmware.size <= 0 || firmware.crc <= 0 -> "firmware size or CRC missing"
        resources != null && (resources.size <= 0 || resources.crc <= 0) -> "resources size or CRC missing"
        !crcMatches(wrapper.getFirmware(), firmware.size, firmware.crc) -> "firmware CRC mismatch"
        resources != null && !crcMatches(wrapper.getResources()!!, resources.size, resources.crc) ->
            "resources CRC mismatch"
        else -> null
    }
}

private fun crcMatches(source: RawSource, size: Long, crc: Long): Boolean =
    source.buffered().use { it.crc32(size) } == crc.toUInt()
