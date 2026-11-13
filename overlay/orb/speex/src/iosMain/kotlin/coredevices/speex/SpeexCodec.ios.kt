package coredevices.speex

// Orb for Pebble builds for Android only. Core's iOS implementation needs prebuilt static
// libraries, so this stand-in only lets the iOS targets of the build configure.
actual class SpeexCodec actual constructor(
    sampleRate: Long,
    bitRate: Int,
    frameSize: Int,
) : AutoCloseable {
    init {
        throw UnsupportedOperationException("Speex is not built for iOS in Orb for Pebble")
    }

    actual fun decodeFrame(
        encodedFrame: ByteArray,
        decodedFrame: ByteArray,
        hasHeaderByte: Boolean,
    ): SpeexDecodeResult = throw UnsupportedOperationException()

    actual override fun close() {}
}
