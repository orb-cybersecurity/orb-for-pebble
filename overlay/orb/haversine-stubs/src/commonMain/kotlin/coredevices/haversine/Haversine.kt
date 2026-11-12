package coredevices.haversine

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.time.Instant

/**
 * Orb stand-in for io.github.coredevices.haversine, the Index 01 ring's radio library, which
 * is published as a binary with no public source. The declarations share the real library's
 * names so Core's ring code compiles unchanged.
 *
 * Behaviour: no ring is ever seen. Nothing here creates a [KMPHaversineSatellite], scanning
 * reports nothing, and pairing fails.
 */
const val CACHE_SUBDIRECTORY = "haversine"
const val RING_UPDATE_URL = ""

internal const val REMOVED = "The Index 01 radio library is not part of this build"

expect class KMPHaversineSatelliteManager {
    val advertisements: SharedFlow<KMPHaversineAdvertisement>
    val lastRing: StateFlow<KMPHaversineSatellite?>

    suspend fun awaitBluetoothReady()
    suspend fun startScanning(): Flow<SatelliteStatus>
    suspend fun notifyPairedSatelliteChanged()
    suspend fun programSatelliteWithUserID(satelliteId: String, userId: String): Result<Unit>
    fun restartPreemptiveTransfer()
    suspend fun getSatelliteById(satelliteId: String): KMPHaversineSatellite?
    suspend fun ingestAdvertisement(
        satelliteId: String,
        name: String?,
        rssi: Int,
        manufacturerData: ByteArray,
    ): KMPHaversineSatellite
}

class KMPHaversineSatellite internal constructor(
    val state: StateFlow<KMPHaversineSatelliteState>,
) {
    val id: String get() = ""
    val name: String? get() = null
    val lastAdvertisement: KMPHaversineAdvertisement? get() = null

    suspend fun forceFailsafe() {}

    suspend fun eraseCollections() {}

    suspend fun measureRSSI(averagingCount: Int, connectionTimeoutSeconds: UInt? = null): KMPRSSIMeasurement =
        throw IllegalStateException(REMOVED)
}

class KMPRSSIMeasurement(val rxRSSI: Float, val phoneRSSI: Float?)

class KMPHaversineSatelliteState internal constructor() {
    val isInCollectionState: Boolean get() = false
    val rxRSSI: Float? get() = null
    val rxRSSITimestamp: Instant? get() = null
    val isNearby: Boolean get() = false
    val isInFailsafeMode: Boolean get() = false
    val firmwareVersion: String get() = ""
    val truncatedCollectionCount: Int get() = 0
    val serialNumber: String get() = ""
    val programmedSerialNumber: String? get() = null
    val applicationDataUserId: String? get() = null
    val hardwareVersion: Pair<Int, Int> get() = 0 to 0
}

class KMPHaversineAdvertisement internal constructor() {
    val id: String get() = ""
    val name: String? get() = null
    val timestamp: Instant get() = Instant.DISTANT_PAST
    val rssi: Float? get() = null
    val cacheableStateFingerprint: Long? get() = null
    val inCollectionState: Boolean? get() = null
    val pairingKeyHash: Int? get() = null

    companion object {
        fun parseToStateFingerprint(manufacturerData: ByteArray): Long? = null
    }
}

fun pairingKeyHashOf(cacheableStateFingerprint: Long): Int = 0

fun fingerprintMatchesFailsafe(fingerprint: Long): Boolean = false

fun fingerprintMatchesUserId(fingerprint: Long, userId: String): Boolean = false

fun fingerprintMatchesPTF(fingerprint: Long): Boolean = false

fun removeDCBias(data: ShortArray) {}

interface KMPHaversineHacksDelegate {
    fun shouldWipeCollectionsBeforeTransfer(satellite: KMPHaversineSatellite): Boolean
    fun wipedCollectionsBeforeTransfer(satellite: KMPHaversineSatellite)
}

interface KMPHaversineDebugDelegate {
    fun handleHaversineDebugInfo(info: KMPHaversineDebugInfo)
    fun shouldReadRxRSSI(satellite: KMPHaversineSatellite): Boolean
    fun handleRxRSSI(rssi: Float, satellite: KMPHaversineSatellite)
}

data class KMPHaversineDebugInfo(
    val timestamp: Instant,
    val satelliteId: String,
    val satelliteName: String,
    val satelliteVersion: String,
    val satelliteSerial: String,
    val satelliteProgrammedSerial: String?,
    val dump: KMPHaversineDebugDump,
)

class KMPHaversineDebugDump(
    val coreDump: ByteArray?,
    val rebootReasons: List<KMPHaversineDebugRebootReason>,
)

data class KMPHaversineDebugRebootReason(
    val code: UInt,
    val context: UInt,
    val description: String?,
)

interface CollectionIndexStorage {
    val lastSuccessfulCollectionIndex: StateFlow<Int?>
    fun setLastSuccessfulCollectionIndex(index: Int?)
}

enum class BluetoothFailureReason { PeerRemovedPairingInformation, AuthenticationFailure, Unknown }

class DataDecodeException(override val cause: Throwable, val data: ByteArray) : Exception(cause)

class MultipartCollection internal constructor() {
    val startIndex: Int get() = 0
    val finalSequence: String? get() = null
    val indices: Set<Int> get() = emptySet()
    val releaseTimestamp: Instant? get() = null
    val isContiguous: Boolean get() = false
}

sealed class TransferStatus(val satellite: KMPHaversineSatellite) {
    class TransferStarted(
        satellite: KMPHaversineSatellite,
        val willTransferRange: IntRange,
        val rollover: Boolean,
    ) : TransferStatus(satellite)

    class TransferTypeDetermined(
        satellite: KMPHaversineSatellite,
        val isAudio: Boolean,
        val buttonSequence: String?,
        val collectionStartIndex: Int?,
        val collectionIndex: Int,
        val final: Boolean,
        val advertisementReceivedTimestamp: Instant,
        val lifetimeCollectionCount: UInt?,
        val batteryVoltageMilliV: UShort?,
        val buttonReleaseTimestamp: Instant?,
        val ringInCollectionState: Boolean? = null,
    ) : TransferStatus(satellite)

    class TransferInProgress(
        satellite: KMPHaversineSatellite,
        val collectionStartIndex: Int,
        val currentCollectionIndex: Int,
    ) : TransferStatus(satellite)

    class TransferComplete(
        satellite: KMPHaversineSatellite,
        val collectionStartCount: Long,
        val buttonSequence: String?,
        val collectionIndex: Int,
        val samples: ShortArray,
        val sampleRate: Long,
        val buttonReleaseTimestamp: Instant?,
        val transferCompleteTimestamp: Instant,
        val isContiguous: Boolean,
        val ringInCollectionState: Boolean? = null,
    ) : TransferStatus(satellite)

    class TransferFailed(
        satellite: KMPHaversineSatellite,
        val exception: Exception?,
        val collectionIndex: Int,
    ) : TransferStatus(satellite)

    class IrrecoverableDataDetected(
        satellite: KMPHaversineSatellite,
        val exception: Exception?,
        val collection: MultipartCollection?,
    ) : TransferStatus(satellite)
}

sealed interface SatelliteStatus {
    val satellite: KMPHaversineSatellite

    class Transferring(
        override val satellite: KMPHaversineSatellite,
        val transferStatus: TransferStatus,
    ) : SatelliteStatus

    class BluetoothFailure(
        override val satellite: KMPHaversineSatellite,
        val reason: BluetoothFailureReason,
    ) : SatelliteStatus

    sealed class FirmwareUpdating : SatelliteStatus {
        class NotStarted(override val satellite: KMPHaversineSatellite, val newVersion: String) : FirmwareUpdating()
        class Started(override val satellite: KMPHaversineSatellite, val newVersion: String) : FirmwareUpdating()
        class Success(override val satellite: KMPHaversineSatellite, val newVersion: String) : FirmwareUpdating()
        class Failed(override val satellite: KMPHaversineSatellite, val newVersion: String) : FirmwareUpdating()
    }

    sealed class ProgrammingUserId : SatelliteStatus {
        class InProgress(override val satellite: KMPHaversineSatellite) : ProgrammingUserId()
        class Completed(override val satellite: KMPHaversineSatellite) : ProgrammingUserId()
        class Failed(override val satellite: KMPHaversineSatellite, val error: Throwable) : ProgrammingUserId()
    }
}

class ButtonGesture(
    val sequence: String,
    val releaseTimestamp: Instant,
    val collectionStartIndex: Int?,
)

class ButtonSequenceDebouncer(scope: CoroutineScope) {
    val buttonGestures: SharedFlow<ButtonGesture> = MutableSharedFlow()

    fun onTransferStatus(status: TransferStatus) {}

    fun onButtonSequence(
        sequence: String,
        releaseTimestamp: Instant,
        collectionStartIndex: Int?,
        ringInCollectionState: Boolean? = null,
        isLastInBurst: Boolean? = null,
        final: Boolean = false,
    ) {}
}
