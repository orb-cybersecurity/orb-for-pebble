package coredevices.coreapp.auth

import PlatformUiContext
import coredevices.util.auth.GoogleAuthUtil
import coredevices.util.auth.SilentSignIn
import dev.gitlive.firebase.auth.AuthCredential

// Orb: Google sign-in needs Google Play services, which this build does not use.
actual class RealGoogleAuthUtil : GoogleAuthUtil, SilentSignIn {
    override suspend fun signInGoogle(context: PlatformUiContext): AuthCredential? = null

    override suspend fun attempt(): Boolean = false
}
