package coredevices.haversine

import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flow

// Shared body of the per-platform KMPHaversineSatelliteManager actuals.
internal class InertManager {
    val advertisements: SharedFlow<KMPHaversineAdvertisement> = MutableSharedFlow()
    val lastRing: StateFlow<KMPHaversineSatellite?> = MutableStateFlow(null)

    fun startScanning(): Flow<SatelliteStatus> = flow { awaitCancellation() }

    fun programSatelliteWithUserID(): Result<Unit> = Result.failure(IllegalStateException(REMOVED))
}
