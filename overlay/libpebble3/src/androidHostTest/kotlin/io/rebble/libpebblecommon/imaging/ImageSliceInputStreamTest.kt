package io.rebble.libpebblecommon.imaging

import java.io.ByteArrayInputStream
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals

class ImageSliceInputStreamTest {
    @Test fun exifSeesTheCountedLengthEvenIfTheProviderReportsZeroAndCannotReadPastIt() {
        val bytes = ByteArray(128) { it.toByte() }
        val provider = object : ByteArrayInputStream(bytes) { override fun available() = 0 }
        ImageSliceInputStream(provider, 64).use { bounded ->
            assertEquals(64, bounded.available())
            assertEquals(bytes[0].toInt(), bounded.read())
            assertEquals(10, bounded.skip(10))
            assertEquals(53, bounded.available())
            // The framework EXIF parser sizes its read using available().
            assertContentEquals(bytes.copyOfRange(11, 64), bounded.readNBytes(bounded.available()))
            assertEquals(0, bounded.available())
            assertEquals(-1, bounded.read())
            assertEquals(0, bounded.read(ByteArray(0)))
        }
        assertEquals(64, provider.read())
    }
}
