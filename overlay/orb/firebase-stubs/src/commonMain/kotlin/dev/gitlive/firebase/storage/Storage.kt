package dev.gitlive.firebase.storage

import dev.gitlive.firebase.Firebase

private const val REMOVED = "Firebase Storage is not part of this build"

val Firebase.storage: FirebaseStorage get() = FirebaseStorage

object FirebaseStorage {
    val reference: StorageReference get() = StorageReference()

    fun reference(location: String): StorageReference = StorageReference()
}

class StorageReference internal constructor() {
    val name: String get() = ""
    val path: String get() = ""

    fun child(path: String): StorageReference = StorageReference()

    suspend fun getMetadata(): FirebaseStorageMetadata? = null

    suspend fun getDownloadUrl(): String = throw FirebaseStorageException(REMOVED)

    suspend fun putFile(file: File, metadata: FirebaseStorageMetadata? = null): Unit =
        throw FirebaseStorageException(REMOVED)

    suspend fun delete() {}
}

// The real class wraps a platform file handle (an android.net.Uri on Android).
class File(val uri: Any?)

class FirebaseStorageMetadata(
    var md5Hash: String? = null,
    var cacheControl: String? = null,
    var contentDisposition: String? = null,
    var contentEncoding: String? = null,
    var contentLanguage: String? = null,
    var contentType: String? = null,
    var customMetadata: MutableMap<String, String> = mutableMapOf(),
)

class FirebaseStorageException internal constructor(message: String) : Exception(message)
