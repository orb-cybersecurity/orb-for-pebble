package coredevices.haversine

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow

// Orb builds Android only; this mirrors the iOS call site so the module keeps its shape.
actual class KMPHaversineSatelliteManager(
    pairedSatelliteIdProvider: () -> String?,
    debugDelegate: KMPHaversineDebugDelegate,
    hacksDelegate: KMPHaversineHacksDelegate,
    collectionIndexStorage: CollectionIndexStorage,
    hwVersion: Pair<Int, Int>,
    scope: CoroutineScope,
    updateJsonProvider: suspend (KMPHaversineSatellite?) -> String?,
) {
    private val inert = InertManager()

    actual val advertisements: SharedFlow<KMPHaversineAdvertisement> get() = inert.advertisements
    actual val lastRing: StateFlow<KMPHaversineSatellite?> get() = inert.lastRing

    actual suspend fun awaitBluetoothReady() {}

    actual suspend fun startScanning(): Flow<SatelliteStatus> = inert.startScanning()

    actual suspend fun notifyPairedSatelliteChanged() {}

    actual suspend fun programSatelliteWithUserID(satelliteId: String, userId: String): Result<Unit> =
        inert.programSatelliteWithUserID()

    actual fun restartPreemptiveTransfer() {}

    actual suspend fun getSatelliteById(satelliteId: String): KMPHaversineSatellite? = null

    actual suspend fun ingestAdvertisement(
        satelliteId: String,
        name: String?,
        rssi: Int,
        manufacturerData: ByteArray,
    ): KMPHaversineSatellite = throw IllegalStateException(REMOVED)
}
