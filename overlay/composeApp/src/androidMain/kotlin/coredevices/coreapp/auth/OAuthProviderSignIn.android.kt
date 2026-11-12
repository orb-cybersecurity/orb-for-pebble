package coredevices.coreapp.auth

import PlatformUiContext
import dev.gitlive.firebase.auth.AuthCredential

// Orb: provider sign-in runs through the Firebase SDK, which this build does not use.
internal suspend fun oAuthProviderCredential(
    context: PlatformUiContext,
    providerId: String,
    scopes: List<String>,
): AuthCredential? = null
