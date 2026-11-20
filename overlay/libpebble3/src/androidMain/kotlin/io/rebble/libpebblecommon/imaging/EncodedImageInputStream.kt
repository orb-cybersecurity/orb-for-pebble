package io.rebble.libpebblecommon.imaging

import java.io.IOException
import java.io.InputStream

internal const val MAX_ENCODED_IMAGE_BYTES = 8 * 1024 * 1024

/** Count every encoded byte, including the header consumed by bounds decoding. No image buffer. */
internal class EncodedImageInputStream(private val source: InputStream) : InputStream() {
    private var count = 0
    val totalBytes: Int get() = count

    override fun read(): Int {
        checkLimit()
        return source.read().also { if (it != -1) record(1) }
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        checkLimit()
        return source.read(buffer, offset, minOf(length, MAX_ENCODED_IMAGE_BYTES - count + 1)).also {
            if (it > 0) record(it)
        }
    }

    private fun record(bytes: Int) {
        count += bytes
        checkLimit()
    }

    private fun checkLimit() {
        if (count > MAX_ENCODED_IMAGE_BYTES) throw IOException("Encoded image exceeds limit")
    }

    override fun close() = source.close()
}
