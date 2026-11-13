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
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
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
 * newer than what the watch runs. A download that fails says nothing about the bundle, so it
 * fails the whole check instead (reported, not cached, retried on the next check).
 *
 * The offered URL carries the verified SHA-256 ([withVerifiedDigest]); Orb's edit to libpebble's
 * FirmwareDownloader checks the installed download against it, so only the bytes checked here can
 * be installed.
 *
 * A version pinned in settings ([PINNED_FIRMWARE_KEY]) replaces the newest-first choice and may be
 * older than what the watch runs. Pinned offers are never installed automatically.
 */
class GitHubFirmwareApi(
    private val httpClient: HttpClient,
    private val settings: Settings,
) : EngDashOtaApi {
    private val logger = Logger.withTag("GitHubFirmware")
    private val mutex = Mutex()

    // Bundles already judged this session, by published digest, tag and board: null when they passed.
    private val judged = mutableMapOf<String, String?>()
    private var recentReleases: Pair<String, List<GitHubRelease>>? = null

    override suspend fun getLatestFirmware(
        deviceSerial: String,
        hardwareVersion: String,
        currentVersion: String?,
        deviceMac: String?,
    ): EngDashLatestResult? = mutex.withLock {
        val pinned = settings.getStringOrNull(PINNED_FIRMWARE_KEY)?.takeIf { it.isNotBlank() }
        if (pinned != null) {
            return@withLock pinnedRelease(hardwareVersion, currentVersion, pinned)
        }
        for (candidate in firmwareCandidates(fetchRecentReleases(), hardwareVersion, currentVersion).take(MAX_TRIES)) {
            val problem = problemWith(candidate, hardwareVersion)
            if (problem == null) return@withLock candidate.asResult(pinned = false)
            logger.w { "Skipping PebbleOS ${candidate.tag} for $hardwareVersion: $problem" }
        }
        null
    }

    private suspend fun pinnedRelease(board: String, running: String?, pinned: String): EngDashLatestResult? {
        val tag = "v" + pinned.removePrefix("v")
        if (running != null && ReleaseVersion.parseRunning(running) == ReleaseVersion.parse(tag)) return null
        val response = httpClient.get("$RELEASES_URL/tags/$tag") { header("Accept", GITHUB_JSON) }
        if (response.status == HttpStatusCode.NotFound) {
            throw IllegalStateException("PebbleOS $tag is not among Core's releases")
        }
        check(response.status.isSuccess()) { "Couldn't look up PebbleOS $tag: ${response.status}" }
        val release = response.body<GitHubRelease>()
        val problem = metadataProblem(release, board) ?: problemWith(candidateFrom(release, board)!!, board)
        if (problem != null) throw IllegalStateException("PebbleOS $tag can't be installed on this watch: $problem")
        return candidateFrom(release, board)!!.asResult(pinned = true)
    }

    /** The newest releases, revalidated with the ETag so an unchanged list costs no download. */
    private suspend fun fetchRecentReleases(): List<GitHubRelease> {
        val cached = recentReleases
        val response = httpClient.get(RELEASES_URL) {
            header("Accept", GITHUB_JSON)
            parameter("per_page", RECENT_RELEASES)
            cached?.let { header(HttpHeaders.IfNoneMatch, it.first) }
        }
        if (response.status == HttpStatusCode.NotModified && cached != null) return cached.second
        check(response.status.isSuccess()) { "Couldn't list PebbleOS releases: ${response.status}" }
        val releases = response.body<List<GitHubRelease>>()
        recentReleases = response.headers[HttpHeaders.ETag]?.let { it to releases }
        return releases
    }

    /** Why [candidate]'s bundle must not be offered, or null if it passed. Throws if it can't be fetched. */
    private suspend fun problemWith(candidate: FirmwareCandidate, board: String): String? {
        // The verdict is about these bytes as this release for this board.
        val key = "${candidate.asset.digest}|${candidate.tag}|$board"
        if (key in judged) return judged[key]
        val bytes = try {
            download(candidate.asset)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            throw IllegalStateException("Couldn't download PebbleOS ${candidate.tag} to check it", e)
        }
        return bundleProblem(bytes, candidate, board).also { judged[key] = it }
    }

    private suspend fun download(asset: GitHubAsset): ByteArray =
        httpClient.prepareGet(asset.url).execute { response ->
            check(response.status.isSuccess()) { "HTTP ${response.status}" }
            response.bodyAsChannel().readRemaining(asset.size + 1).readByteArray()
        }

    private fun FirmwareCandidate.asResult(pinned: Boolean) = EngDashLatestResult(
        version = tag,
        notes = if (pinned) "PebbleOS $tag, pinned in Orb's debug settings." else "PebbleOS $tag from Core's releases on GitHub.",
        artifacts = listOf(EngDashArtifact(withVerifiedDigest(asset, pinned))),
    )

    companion object {
        const val PINNED_FIRMWARE_KEY = "orb.pinnedPebbleOsVersion"
        private const val RELEASES_URL = "https://api.github.com/repos/coredevices/PebbleOS/releases"
        private const val GITHUB_JSON = "application/vnd.github+json"
        private const val MAX_TRIES = 5
        // Enough to reach past the parallel release trains to the newest few versions.
        private const val RECENT_RELEASES = 20
    }
}

/**
 * [asset]'s URL with its verified SHA-256 in the fragment, which HTTP clients don't send. Orb's
 * edits to libpebble read the same markers: FirmwareDownloader checks the download against the
 * digest, and FirmwareUpdateUiTracker doesn't auto-install pinned offers.
 */
fun withVerifiedDigest(asset: GitHubAsset, pinned: Boolean): String =
    asset.url + "#orb-sha256=" + asset.digest!!.removePrefix("sha256:") + if (pinned) "&orb-pinned" else ""

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

data class ReleaseVersion(val major: Int, val minor: Int, val patch: Int, val build: Int = 0) : Comparable<ReleaseVersion> {
    override fun compareTo(other: ReleaseVersion): Int =
        compareValuesBy(this, other, { it.major }, { it.minor }, { it.patch }, { it.build })

    companion object {
        private val RELEASE = Regex("""v?(\d+)\.(\d+)\.(\d+)""")
        private val RUNNING = Regex("""v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?""")

        /**
         * Release tags only, as PebbleOS's own tooling counts them (see FirmwareBootOrder): dev
         * builds (v4.46.0-3-gabc123) and four-part tags (v4.9.142.12) are not releases.
         */
        fun parse(tag: String): ReleaseVersion? = RELEASE.matchEntire(tag)?.destructured?.let { (a, b, c) ->
            ReleaseVersion(a.toInt(), b.toInt(), c.toInt())
        }

        /** What a watch runs: a release, or a four-part build such as v4.9.142.12; not a dev build. */
        fun parseRunning(version: String): ReleaseVersion? = RUNNING.matchEntire(version)?.groupValues?.let { g ->
            ReleaseVersion(g[1].toInt(), g[2].toInt(), g[3].toInt(), g[4].ifEmpty { "0" }.toInt())
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
 * running a dev build is left alone.
 */
fun firmwareCandidates(releases: List<GitHubRelease>, board: String, running: String?): List<FirmwareCandidate> {
    val runningVersion = running?.let { ReleaseVersion.parseRunning(it) ?: return emptyList() }
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
