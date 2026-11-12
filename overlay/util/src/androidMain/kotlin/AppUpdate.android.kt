package coredevices.coreapp.util

import PlatformUiContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

// Orb: updates come from the store the app was installed from, not Google Play's in-app flow.
actual data object AppUpdatePlatformContent

class AndroidAppUpdate : AppUpdate {
    private val _updateAvailable = MutableStateFlow<AppUpdateState>(AppUpdateState.NoUpdateAvailable)
    override val updateAvailable: StateFlow<AppUpdateState> = _updateAvailable.asStateFlow()

    override fun startUpdateFlow(uiContext: PlatformUiContext, update: AppUpdatePlatformContent) {}
}
