package coredevices.haversine

import android.bluetooth.le.ScanResult
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow

actual class KMPHaversineSatelliteManager(
    pairedSatelliteIdProvider: () -> String?,
    debugDelegate: KMPHaversineDebugDelegate,
    hacksDelegate: KMPHaversineHacksDelegate,
    collectionIndexStorage: CollectionIndexStorage,
    context: Context,
    hwVersion: Pair<Int, Int>,
    scope: CoroutineScope,
    updateJsonProvider: suspend (KMPHaversineSatellite?) -> String?,
    useScanReceiver: Boolean = false,
    scanByPairedAddress: Boolean = false,
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

    suspend fun handleScanResults(results: List<ScanResult>) {}
}

fun pairedScanDeviceAddresses(pairedSatelliteId: String): List<String> = emptyList()
