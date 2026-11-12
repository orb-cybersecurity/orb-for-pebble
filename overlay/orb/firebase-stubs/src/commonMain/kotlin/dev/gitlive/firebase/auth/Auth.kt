package dev.gitlive.firebase.auth

import dev.gitlive.firebase.Firebase
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

private const val REMOVED = "Firebase authentication is not part of this build"

val Firebase.auth: FirebaseAuth get() = FirebaseAuth

object FirebaseAuth {
    val currentUser: FirebaseUser? get() = null

    // Like the real flows while signed out: report "no user" and stay open.
    val authStateChanged: Flow<FirebaseUser?> get() = signedOut()
    val idTokenChanged: Flow<FirebaseUser?> get() = signedOut()

    suspend fun signInAnonymously(): AuthResult = throw FirebaseAuthException(REMOVED)

    suspend fun signInWithCredential(authCredential: AuthCredential): AuthResult =
        throw FirebaseAuthException(REMOVED)

    suspend fun signOut() {}
}

private fun signedOut(): Flow<FirebaseUser?> = flow {
    emit(null)
    awaitCancellation()
}

// No instance can exist: the constructor is internal and nothing here creates one.
class FirebaseUser internal constructor() {
    val uid: String get() = ""
    val isAnonymous: Boolean get() = true
    val email: String? get() = null
    val displayName: String? get() = null
    val providerData: List<UserInfo> get() = emptyList()

    suspend fun getIdToken(forceRefresh: Boolean): String? = null

    suspend fun linkWithCredential(credential: AuthCredential): AuthResult =
        throw FirebaseAuthException(REMOVED)

    suspend fun delete() {}
}

class UserInfo internal constructor() {
    val providerId: String get() = ""
}

open class AuthCredential internal constructor(val providerId: String)

class AuthResult internal constructor() {
    val user: FirebaseUser? get() = null
}

open class FirebaseAuthException internal constructor(message: String) : Exception(message)

class FirebaseAuthUserCollisionException internal constructor(message: String) :
    FirebaseAuthException(message)

object GoogleAuthProvider {
    fun credential(idToken: String?, accessToken: String?): AuthCredential =
        throw FirebaseAuthException(REMOVED)
}
