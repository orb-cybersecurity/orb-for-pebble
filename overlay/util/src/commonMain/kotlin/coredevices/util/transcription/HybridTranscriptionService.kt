package coredevices.util.transcription

import co.touchlab.kermit.Logger
import coredevices.util.AudioEncoding
import coredevices.util.CoreConfigFlow
import coredevices.util.models.CactusSTTMode
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.io.Buffer
import kotlinx.io.readByteArray
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Duration
import kotlin.time.TimeSource

/**
 * Orb: dictation goes to the phone's speech recognition service ([PlatformSpeechRecognizer]).
 *
 * Core's version also routes to its cloud recognizers, which need a Core account, and to its
 * on-device engine, a prebuilt binary. Orb has neither. Rebble's service is chosen by
 * STTRouter before this is reached.
 */
class HybridTranscriptionService(
    private val coreConfigFlow: CoreConfigFlow,
    private val platform: PlatformSpeechRecognizer,
) : TranscriptionService {
    companion object {
        private val logger = Logger.withTag("HybridTranscriptionService")
        private const val BYTES_PER_SAMPLE = 2
        private const val MIN_AUDIO_SECONDS = 0.1
    }

    private val sttConfig get() = coreConfigFlow.value.sttConfig

    private var _lastSuccessfulMode: CactusSTTMode? = null
    private var _lastModelUsed: String? = null

    // Diagnostics for the shared logs.
    val configuredMode get() = sttConfig.mode
    val configuredLanguage get() = sttConfig.spokenLanguage
    val lastSuccessfulMode get() = _lastSuccessfulMode
    val lastModelUsed get() = _lastModelUsed

    override val onInitialized: Channel<Boolean> = Channel(Channel.CONFLATED)

    override suspend fun isAvailable(): Boolean = platform.isAvailable() && platform.isAuthorized()

    override suspend fun transcribe(
        audioStreamFrames: Flow<ByteArray>?,
        sampleRate: Int,
        language: STTLanguage,
        conversationContext: STTConversationContext?,
        dictionaryContext: List<String>?,
        contentContext: String?,
        encoding: AudioEncoding,
        initialTimeout: Duration?,
        totalTimeout: Duration?,
    ): Flow<TranscriptionSessionStatus> = flow {
        val start = TimeSource.Monotonic.markNow()
        emit(TranscriptionSessionStatus.Open)
        if (audioStreamFrames == null) return@flow

        val buffer = Buffer()
        audioStreamFrames.collect { buffer.write(it) }
        val seconds = buffer.size / (sampleRate * BYTES_PER_SAMPLE).coerceAtLeast(1).toDouble()
        if (buffer.size == 0L || seconds < MIN_AUDIO_SECONDS) {
            throw TranscriptionException.NoSpeechDetected("No audio data received")
        }
        if (!isAvailable()) {
            throw TranscriptionException.TranscriptionServiceUnavailable(PLATFORM_STT_MODEL_NAME)
        }

        val languageTag = ((language as? STTLanguage.Specific)?.languageCodes?.firstOrNull()
            ?: sttConfig.spokenLanguage)?.let { toBcp47(it, null) }
        val text = try {
            platform.transcribe(buffer.readByteArray(), sampleRate, languageTag)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            logger.w(e) { "System speech recognition failed: ${e.message}" }
            throw e
        }
        logger.d { "Transcription completed in ${start.elapsedNow()}, ${text.length} chars" }
        if (text.isBlank()) {
            throw TranscriptionException.NoSpeechDetected("Failed to understand audio", modelUsed = PLATFORM_STT_MODEL_NAME)
        }
        _lastSuccessfulMode = CactusSTTMode.PlatformOnly
        _lastModelUsed = PLATFORM_STT_MODEL_NAME
        emit(TranscriptionSessionStatus.Transcription(text, PLATFORM_STT_MODEL_NAME))
    }
}
