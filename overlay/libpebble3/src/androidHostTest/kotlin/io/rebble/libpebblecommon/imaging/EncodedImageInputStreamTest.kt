package io.rebble.libpebblecommon.imaging

import java.io.ByteArrayInputStream
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class EncodedImageInputStreamTest {
    @Test fun boundsHeaderAndRemainingBytesShareTheDecodeLimit() {
        for (size in listOf(MAX_ENCODED_IMAGE_BYTES, MAX_ENCODED_IMAGE_BYTES + 1)) {
            EncodedImageInputStream(ByteArrayInputStream(ByteArray(size))).use { stream ->
                // Mimic bounds decoding consuming a header and skipping metadata.
                repeat(32) { stream.read() }
                stream.skip(256)
                val buffer = ByteArray(8192)
                fun drain() { while (stream.read(buffer) != -1) { } }
                if (size > MAX_ENCODED_IMAGE_BYTES) {
                    assertFailsWith<IOException> { drain() }
                    // BitmapFactory may swallow an IOException; the subsequent drain must still fail.
                    assertFailsWith<IOException> { stream.read(buffer) }
                } else { drain(); assertEquals(-1, stream.read()) }
            }
        }
    }
}
