@file:JvmName("Cactus")
package com.cactus

// Orb: the Cactus engine ships only as a prebuilt binary, so this build has no engine.
// isCactusSupported() reports that, and Core's "unsupported device" paths take over.

private const val REMOVED = "The Cactus engine is not part of this build"

private fun removed(): Nothing = throw UnsupportedOperationException(REMOVED)

actual fun isCactusSupported(): Boolean = false

actual fun cactusSetBackend(backend: String): Int = -1
actual fun cactusInit(modelPath: String, corpusDir: String?, cacheIndex: Boolean): Long = removed()
actual fun cactusDestroy(handle: Long) {}
actual fun cactusReset(handle: Long) {}
actual fun cactusStop(handle: Long) {}
actual fun cactusComplete(handle: Long, messagesJson: String, optionsJson: String?, toolsJson: String?, callback: CactusTokenCallback?, pcmData: ByteArray?): String = removed()
actual fun cactusPrefill(handle: Long, messagesJson: String, optionsJson: String?, toolsJson: String?, pcmData: ByteArray?): String = removed()
actual fun cactusTokenize(handle: Long, text: String): IntArray = removed()
actual fun cactusScoreWindow(handle: Long, tokens: IntArray, start: Long, end: Long, context: Long): String = removed()
actual fun cactusTranscribe(handle: Long, audioPath: String?, prompt: String, optionsJson: String?, callback: CactusTokenCallback?, pcmData: ByteArray?): String = removed()
actual fun cactusStreamTranscribeStart(handle: Long, optionsJson: String?): Long = removed()
actual fun cactusStreamTranscribeProcess(stream: Long, pcmData: ByteArray?): String = removed()
actual fun cactusStreamTranscribeStop(stream: Long): String = removed()
actual fun cactusEmbed(handle: Long, text: String, normalize: Boolean): FloatArray = removed()
actual fun cactusImageEmbed(handle: Long, imagePath: String): FloatArray = removed()
actual fun cactusAudioEmbed(handle: Long, audioPath: String): FloatArray = removed()
actual fun cactusRagQuery(handle: Long, query: String, topK: Long): String = removed()
actual fun cactusIndexInit(indexDir: String, embeddingDim: Long): Long = removed()
actual fun cactusIndexAdd(handle: Long, ids: IntArray, documents: Array<String>, metadatas: Array<String>?, embeddings: Array<FloatArray>, embeddingDim: Long): Int = removed()
actual fun cactusIndexDelete(handle: Long, ids: IntArray): Int = removed()
actual fun cactusIndexGet(handle: Long, ids: IntArray): String = removed()
actual fun cactusIndexQuery(handle: Long, embedding: FloatArray, optionsJson: String?): String = removed()
actual fun cactusIndexCompact(handle: Long): Int = removed()
actual fun cactusIndexDestroy(handle: Long) {}
actual fun cactusGetLastError(): String = REMOVED
actual fun cactusLogSetLevel(level: Int) {}
actual fun cactusLogSetCallback(callback: CactusLogCallback?) {}
actual fun cactusSetTelemetryEnvironment(framework: String?, cacheLocation: String?, version: String?) {}
actual fun cactusSetAppId(appId: String) {}
actual fun cactusTelemetryFlush() {}
actual fun cactusTelemetryShutdown() {}
