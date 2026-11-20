package io.rebble.libpebblecommon.imaging

import java.io.InputStream

/** EXIF uses available() as its input length, even when a provider's stream reports zero. */
internal class ImageSliceInputStream(private val source: InputStream, length: Int) : InputStream() {
    private var remaining = length

    override fun available(): Int = remaining
    override fun read(): Int {
        if (remaining == 0) return -1
        return source.read().also { if (it == -1) remaining = 0 else remaining-- }
    }
    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (length == 0) return 0
        if (remaining == 0) return -1
        return source.read(buffer, offset, minOf(length, remaining)).also {
            if (it == -1) remaining = 0 else remaining -= it
        }
    }
    override fun skip(count: Long): Long {
        if (count <= 0) return 0
        return source.skip(minOf(count, remaining.toLong())).also { remaining -= it.toInt() }
    }
    override fun close() = source.close()
}
