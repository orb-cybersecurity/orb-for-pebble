package coredevices.util.transcription

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.os.Build
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.provider.Settings
import android.speech.RecognitionListener
import android.speech.RecognitionService
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import co.touchlab.kermit.Logger
import coredevices.util.models.ModelDownloadStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.koin.mp.KoinPlatform
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds

/**
 * Orb: hands audio to the phone's speech recognition service, which is whichever recognizer
 * app the user installed and selected. Orb ships no speech engine of its own.
 *
 * Supplying recorded audio to the service (instead of letting it open the microphone) needs
 * Android 13, and the recognizer app has to honor it.
 */
actual class PlatformSpeechRecognizer {
    private val logger = Logger.withTag("PlatformSpeechRecognizer")
    private val context: Context get() = KoinPlatform.getKoin().get()
    private val mutex = Mutex()

    actual suspend fun isAvailable(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && recognitionService() != null

    // The system refuses a recognition session to a caller without the microphone permission,
    // even when the caller supplies the audio.
    actual suspend fun isAuthorized(): Boolean =
        context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    // Recognizer apps don't report their languages up front; empty means "not known".
    actual val supportedLanguageTags: StateFlow<List<String>> = MutableStateFlow(emptyList())

    // The recognizer app manages its own models.
    actual suspend fun modelAvailability(languageTag: String?): SpeechModelAvailability =
        if (isAvailable()) SpeechModelAvailability.Installed else SpeechModelAvailability.Unsupported

    actual val downloadStatus: StateFlow<ModelDownloadStatus> = MutableStateFlow(ModelDownloadStatus.Idle)

    actual fun downloadModel(languageTag: String?): Boolean = false

    actual fun releaseUnusedModels(languageTag: String?) = Unit

    actual suspend fun transcribe(pcm: ByteArray, sampleRate: Int, languageTag: String?): String {
        val service = recognitionService()
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || service == null) {
            throw TranscriptionException.TranscriptionServiceUnavailable(PLATFORM_STT_MODEL_NAME)
        }
        // 16-bit mono: two bytes per sample.
        val audioLength = (pcm.size * 1000L / (sampleRate * 2)).milliseconds
        return mutex.withLock {
            withTimeoutOrNull(audioLength + RECOGNITION_GRACE) {
                recognize(service, pcm, sampleRate, languageTag)
            } ?: throw TranscriptionException.TranscriptionServiceError(
                "System speech recognizer did not answer",
                modelUsed = PLATFORM_STT_MODEL_NAME,
            )
        }
    }

    // SpeechRecognizer has to be created and driven from the main thread.
    private suspend fun recognize(
        service: ComponentName,
        pcm: ByteArray,
        sampleRate: Int,
        languageTag: String?,
    ): String = withContext(Dispatchers.Main) {
        val (readEnd, writeEnd) = ParcelFileDescriptor.createPipe()
        val recognizer = SpeechRecognizer.createSpeechRecognizer(context, service)
        var writer: Job? = null
        try {
            suspendCancellableCoroutine { continuation ->
                recognizer.setRecognitionListener(object : ResultListener() {
                    override fun onResults(results: Bundle?) {
                        val text = results
                            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            ?.firstOrNull()
                            .orEmpty()
                        if (continuation.isActive) continuation.resume(text)
                    }

                    override fun onError(error: Int) {
                        if (!continuation.isActive) return
                        when (error) {
                            SpeechRecognizer.ERROR_NO_MATCH,
                            SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> continuation.resume("")
                            else -> continuation.resumeWithException(error.toTranscriptionException())
                        }
                    }
                })
                recognizer.startListening(recognitionIntent(readEnd, sampleRate, languageTag))
                // The service owns its copy of the read end once the request is sent. Closing the
                // write end after the last sample is what tells it the audio is complete.
                writer = CoroutineScope(Dispatchers.IO).launch {
                    try {
                        ParcelFileDescriptor.AutoCloseOutputStream(writeEnd).use { it.write(pcm) }
                    } catch (e: IOException) {
                        logger.w(e) { "Recognizer stopped reading before the audio ended" }
                    }
                }
            }
        } finally {
            writer?.cancel()
            runCatching { readEnd.close() }
            runCatching { writeEnd.close() }
            recognizer.destroy()
        }
    }

    private fun recognitionIntent(
        audio: ParcelFileDescriptor,
        sampleRate: Int,
        languageTag: String?,
    ) = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, audio)
        putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
        putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
        putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, sampleRate)
        if (languageTag != null) putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag)
    }

    /** The recognizer the user selected in system settings, else the first one installed. */
    private fun recognitionService(): ComponentName? {
        val installed = context.packageManager
            .queryIntentServices(Intent(RecognitionService.SERVICE_INTERFACE), 0)
            .map { ComponentName(it.serviceInfo.packageName, it.serviceInfo.name) }
        val selected = Settings.Secure.getString(context.contentResolver, VOICE_RECOGNITION_SERVICE)
            ?.let(ComponentName::unflattenFromString)
        return selected?.takeIf { it in installed } ?: installed.firstOrNull()
    }

    private fun Int.toTranscriptionException(): TranscriptionException = when (this) {
        SpeechRecognizer.ERROR_NETWORK,
        SpeechRecognizer.ERROR_NETWORK_TIMEOUT,
        SpeechRecognizer.ERROR_SERVER,
        SpeechRecognizer.ERROR_SERVER_DISCONNECTED -> TranscriptionException.TranscriptionNetworkError(
            IOException("System speech recognizer network error $this"),
            PLATFORM_STT_MODEL_NAME,
        )
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY ->
            TranscriptionException.TranscriptionInProgress(PLATFORM_STT_MODEL_NAME)
        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED,
        SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
            TranscriptionException.NoSupportedLanguage(PLATFORM_STT_MODEL_NAME)
        else -> TranscriptionException.TranscriptionServiceError(
            "System speech recognizer error $this",
            modelUsed = PLATFORM_STT_MODEL_NAME,
        )
    }

    private abstract class ResultListener : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) = Unit
        override fun onBeginningOfSpeech() = Unit
        override fun onRmsChanged(rmsdB: Float) = Unit
        override fun onBufferReceived(buffer: ByteArray?) = Unit
        override fun onEndOfSpeech() = Unit
        override fun onPartialResults(partialResults: Bundle?) = Unit
        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    private companion object {
        // Settings.Secure.VOICE_RECOGNITION_SERVICE, which is hidden from the SDK.
        const val VOICE_RECOGNITION_SERVICE = "voice_recognition_service"
        val RECOGNITION_GRACE = 60.seconds
    }
}
