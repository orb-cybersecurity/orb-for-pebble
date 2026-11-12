package dev.gitlive.firebase.firestore

import dev.gitlive.firebase.EncodeSettings
import dev.gitlive.firebase.Firebase
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.SerializationStrategy
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

private const val REMOVED = "Firestore is not part of this build"

val Firebase.firestore: FirebaseFirestore get() = FirebaseFirestore

object FirebaseFirestore {
    var settings: FirebaseFirestoreSettings = FirebaseFirestoreSettings()

    fun collection(collectionPath: String): CollectionReference = CollectionReference()

    fun collectionGroup(collectionId: String): Query = Query()

    fun document(documentPath: String): DocumentReference = DocumentReference()

    fun batch(): WriteBatch = WriteBatch()

    suspend fun <T> runTransaction(func: suspend Transaction.() -> T): T =
        throw FirebaseFirestoreException(REMOVED, FirestoreExceptionCode.UNAVAILABLE)
}

class FirebaseFirestoreSettings internal constructor() {
    companion object {
        const val CACHE_SIZE_UNLIMITED: Long = -1L
    }

    class Builder internal constructor() {
        var cacheSettings: LocalCacheSettings = LocalCacheSettings.Persistent(CACHE_SIZE_UNLIMITED)
    }
}

sealed class LocalCacheSettings {
    class Persistent internal constructor(val sizeBytes: Long) : LocalCacheSettings() {
        class Builder internal constructor() {
            var sizeBytes: Long = FirebaseFirestoreSettings.CACHE_SIZE_UNLIMITED
        }
    }
}

fun firestoreSettings(
    settings: FirebaseFirestoreSettings? = null,
    builder: FirebaseFirestoreSettings.Builder.() -> Unit,
): FirebaseFirestoreSettings {
    FirebaseFirestoreSettings.Builder().apply(builder)
    return settings ?: FirebaseFirestoreSettings()
}

fun persistentCacheSettings(
    builder: LocalCacheSettings.Persistent.Builder.() -> Unit,
): LocalCacheSettings.Persistent =
    LocalCacheSettings.Persistent(LocalCacheSettings.Persistent.Builder().apply(builder).sizeBytes)

enum class Direction { ASCENDING, DESCENDING }

enum class Source { CACHE, SERVER, DEFAULT }

// Like a real listener on an unreachable store: nothing arrives and the flow stays open.
private fun <T> silent(): Flow<T> = flow { awaitCancellation() }

open class Query internal constructor() {
    fun where(filter: FilterBuilder.() -> Filter?): Query {
        FilterBuilder().filter()
        return this
    }

    fun orderBy(field: String, direction: Direction = Direction.ASCENDING): Query = this

    fun orderBy(field: FieldPath, direction: Direction = Direction.ASCENDING): Query = this

    fun limit(limit: Number): Query = this

    fun startAfter(vararg fieldValues: Any?): Query = this

    fun startAfter(document: DocumentSnapshot): Query = this

    fun startAt(vararg fieldValues: Any?): Query = this

    fun endBefore(vararg fieldValues: Any?): Query = this

    fun endAt(vararg fieldValues: Any?): Query = this

    val snapshots: Flow<QuerySnapshot> get() = silent()

    fun snapshots(includeMetadataChanges: Boolean = false): Flow<QuerySnapshot> = silent()

    suspend fun get(source: Source = Source.DEFAULT): QuerySnapshot = QuerySnapshot()

    suspend fun count(): Long = 0
}

class CollectionReference internal constructor() : Query() {
    val path: String get() = ""
    val id: String get() = ""
    val document: DocumentReference get() = DocumentReference()

    fun document(documentPath: String): DocumentReference = DocumentReference()

    suspend fun <T : Any> add(data: T, buildSettings: EncodeSettings.Builder.() -> Unit = {}): DocumentReference =
        throw FirebaseFirestoreException(REMOVED, FirestoreExceptionCode.UNAVAILABLE)

    suspend fun <T : Any> add(
        strategy: SerializationStrategy<T>,
        data: T,
        buildSettings: EncodeSettings.Builder.() -> Unit = {},
    ): DocumentReference = throw FirebaseFirestoreException(REMOVED, FirestoreExceptionCode.UNAVAILABLE)
}

class DocumentReference internal constructor() {
    val id: String get() = ""
    val path: String get() = ""
    val parent: CollectionReference get() = CollectionReference()

    fun collection(collectionPath: String): CollectionReference = CollectionReference()

    val snapshots: Flow<DocumentSnapshot> get() = silent()

    fun snapshots(includeMetadataChanges: Boolean = false): Flow<DocumentSnapshot> = silent()

    suspend fun get(source: Source = Source.DEFAULT): DocumentSnapshot = DocumentSnapshot(this)

    suspend fun <T : Any> set(
        data: T,
        merge: Boolean = false,
        buildSettings: EncodeSettings.Builder.() -> Unit = {},
    ) {}

    suspend fun <T : Any> set(
        strategy: SerializationStrategy<T>,
        data: T,
        merge: Boolean = false,
        buildSettings: EncodeSettings.Builder.() -> Unit = {},
    ) {}

    suspend fun <T : Any> update(data: T, buildSettings: EncodeSettings.Builder.() -> Unit = {}) {}

    suspend fun <T : Any> update(
        strategy: SerializationStrategy<T>,
        data: T,
        buildSettings: EncodeSettings.Builder.() -> Unit = {},
    ) {}

    suspend fun updateFields(vararg fieldsAndValues: Pair<String, Any?>) {}

    suspend fun updateFields(fieldsAndValuesBuilder: FieldsAndValuesUpdateDSL.() -> Unit) {}

    suspend fun delete() {}
}

class FieldsAndValuesUpdateDSL internal constructor() : EncodeSettings.Builder {
    override var encodeDefaults: Boolean = true

    infix fun <T> String.to(value: T) {}

    infix fun <T> FieldPath.to(value: T) {}
}

class DocumentSnapshot internal constructor(
    val reference: DocumentReference = DocumentReference(),
) {
    val exists: Boolean get() = false
    val id: String get() = ""
    val metadata: SnapshotMetadata get() = SnapshotMetadata()

    fun contains(field: String): Boolean = false

    inline fun <reified T> get(field: String): T = noData()

    inline fun <reified T> data(): T = noData()

    fun <T> data(strategy: DeserializationStrategy<T>): T =
        throw NoSuchElementException("Firestore stand-in has no documents")

    @PublishedApi
    internal inline fun <reified T> noData(): T =
        if (null is T) {
            null as T
        } else {
            throw NoSuchElementException("Firestore stand-in has no documents")
        }
}

class QuerySnapshot internal constructor() {
    val documents: List<DocumentSnapshot> get() = emptyList()
    val documentChanges: List<DocumentChange> get() = emptyList()
    val metadata: SnapshotMetadata get() = SnapshotMetadata()
}

enum class ChangeType { ADDED, MODIFIED, REMOVED }

class DocumentChange internal constructor() {
    val document: DocumentSnapshot get() = DocumentSnapshot()
    val type: ChangeType get() = ChangeType.ADDED
    val newIndex: Int get() = -1
    val oldIndex: Int get() = -1
}

class SnapshotMetadata internal constructor() {
    val isFromCache: Boolean get() = true
    val hasPendingWrites: Boolean get() = false
}

class WriteBatch internal constructor() {
    fun <T : Any> set(documentRef: DocumentReference, data: T, merge: Boolean = false): WriteBatch = this

    fun <T : Any> set(
        documentRef: DocumentReference,
        strategy: SerializationStrategy<T>,
        data: T,
        merge: Boolean = false,
    ): WriteBatch = this

    fun <T : Any> update(documentRef: DocumentReference, data: T): WriteBatch = this

    fun update(documentRef: DocumentReference, vararg fieldsAndValues: Pair<String, Any?>): WriteBatch = this

    fun delete(documentRef: DocumentReference): WriteBatch = this

    suspend fun commit() {}
}

class Transaction internal constructor() {
    suspend fun get(documentRef: DocumentReference): DocumentSnapshot = DocumentSnapshot(documentRef)

    fun <T : Any> set(documentRef: DocumentReference, data: T, merge: Boolean = false): Transaction = this

    fun <T : Any> update(documentRef: DocumentReference, data: T): Transaction = this

    fun delete(documentRef: DocumentReference): Transaction = this
}

sealed class Filter {
    class WithConstraint internal constructor() : Filter()
}

class FilterBuilder internal constructor() {
    private fun constraint() = Filter.WithConstraint()

    infix fun String.equalTo(value: Any?): Filter.WithConstraint = constraint()
    infix fun FieldPath.equalTo(value: Any?): Filter.WithConstraint = constraint()
    infix fun String.notEqualTo(value: Any?): Filter.WithConstraint = constraint()
    infix fun FieldPath.notEqualTo(value: Any?): Filter.WithConstraint = constraint()
    infix fun String.lessThan(value: Any): Filter.WithConstraint = constraint()
    infix fun String.lessThanOrEqualTo(value: Any): Filter.WithConstraint = constraint()
    infix fun String.greaterThan(value: Any): Filter.WithConstraint = constraint()
    infix fun String.greaterThanOrEqualTo(value: Any): Filter.WithConstraint = constraint()
    infix fun String.contains(value: Any): Filter.WithConstraint = constraint()
    infix fun String.containsAny(values: List<Any>): Filter.WithConstraint = constraint()
    infix fun String.inArray(values: List<Any>): Filter.WithConstraint = constraint()
    infix fun FieldPath.inArray(values: List<Any>): Filter.WithConstraint = constraint()
    infix fun String.notInArray(values: List<Any>): Filter.WithConstraint = constraint()
    infix fun Filter.and(right: Filter): Filter = this
    infix fun Filter.or(right: Filter): Filter = this
}

class FieldPath(vararg fieldNames: String) {
    companion object {
        val documentId: FieldPath = FieldPath("__name__")
    }
}

class FieldValue internal constructor() {
    companion object {
        val serverTimestamp: FieldValue get() = FieldValue()
        val delete: FieldValue get() = FieldValue()

        fun increment(value: Int): FieldValue = FieldValue()

        fun arrayUnion(vararg elements: Any): FieldValue = FieldValue()

        fun arrayRemove(vararg elements: Any): FieldValue = FieldValue()
    }
}

class FirebaseFirestoreException internal constructor(
    message: String,
    internal val codeInternal: FirestoreExceptionCode,
) : Exception(message)

val FirebaseFirestoreException.code: FirestoreExceptionCode get() = codeInternal

enum class FirestoreExceptionCode {
    OK,
    CANCELLED,
    UNKNOWN,
    INVALID_ARGUMENT,
    DEADLINE_EXCEEDED,
    NOT_FOUND,
    ALREADY_EXISTS,
    PERMISSION_DENIED,
    RESOURCE_EXHAUSTED,
    FAILED_PRECONDITION,
    ABORTED,
    OUT_OF_RANGE,
    UNIMPLEMENTED,
    INTERNAL,
    UNAVAILABLE,
    DATA_LOSS,
    UNAUTHENTICATED,
}

@Serializable(with = BaseTimestampSerializer::class)
abstract class BaseTimestamp internal constructor()

@Serializable(with = TimestampSerializer::class)
class Timestamp(val seconds: Long, val nanoseconds: Int) : BaseTimestamp() {
    companion object {
        fun now(): Timestamp = Timestamp(0, 0)
    }

    object ServerTimestamp : BaseTimestamp()
}

fun Timestamp.Companion.fromMilliseconds(milliseconds: Double): Timestamp =
    Timestamp((milliseconds / 1000).toLong(), ((milliseconds % 1000) * 1_000_000).toInt())

fun Timestamp.toMilliseconds(): Double = seconds * 1000.0 + nanoseconds / 1_000_000.0

// Nothing is ever read from or written to a store, so no timestamp reaches a codec.
object BaseTimestampSerializer : KSerializer<BaseTimestamp> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("dev.gitlive.firebase.firestore.BaseTimestamp", PrimitiveKind.LONG)

    override fun deserialize(decoder: Decoder): BaseTimestamp = throw SerializationException(REMOVED)

    override fun serialize(encoder: Encoder, value: BaseTimestamp): Unit =
        throw SerializationException(REMOVED)
}

object TimestampSerializer : KSerializer<Timestamp> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("dev.gitlive.firebase.firestore.Timestamp", PrimitiveKind.LONG)

    override fun deserialize(decoder: Decoder): Timestamp = throw SerializationException(REMOVED)

    override fun serialize(encoder: Encoder, value: Timestamp): Unit =
        throw SerializationException(REMOVED)
}
