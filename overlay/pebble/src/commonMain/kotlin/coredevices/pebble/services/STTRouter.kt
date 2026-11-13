package coredevices.pebble.services

import coredevices.util.CoreConfigFlow
import coredevices.util.models.CactusSTTMode
import io.rebble.libpebblecommon.voice.TranscriptionProvider
import io.rebble.libpebblecommon.voice.TranscriptionResult
import io.rebble.libpebblecommon.voice.VoiceEncoderInfo
import kotlinx.coroutines.flow.Flow

/**
 * Mode-aware [TranscriptionProvider]: Rebble's ASR ([RebbleAsrTranscription]) when the user
 * chose it, otherwise the phone's speech recognition service ([HybridTranscription]).
 *
 * Orb: Core's mixed modes fall back to its on-device engine, which Orb doesn't have, so every
 * Rebble mode means Rebble alone.
 */
class STTRouter(
    private val system: HybridTranscription,
    private val rebble: RebbleAsrTranscription,
    private val coreConfigFlow: CoreConfigFlow,
) : TranscriptionProvider {
    companion object {
        private val rebbleModes = setOf(
            CactusSTTMode.RebbleOnly,
            CactusSTTMode.RebbleFirst,
            CactusSTTMode.RebbleFallback,
        )
    }

    private fun useRebble() = coreConfigFlow.value.sttConfig.mode in rebbleModes

    override suspend fun canServeSession(): Boolean =
        if (useRebble()) rebble.isAvailable() else system.canServeSession()

    override suspend fun transcribe(
        encoderInfo: VoiceEncoderInfo,
        audioFrames: Flow<UByteArray>,
        isNotificationReply: Boolean
    ): TranscriptionResult =
        if (useRebble()) {
            rebble.transcribe(encoderInfo, audioFrames, isNotificationReply)
        } else {
            system.transcribe(encoderInfo, audioFrames, isNotificationReply)
        }
}
