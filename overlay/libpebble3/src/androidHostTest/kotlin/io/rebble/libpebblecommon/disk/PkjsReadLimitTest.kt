package io.rebble.libpebblecommon.disk

import kotlinx.io.Buffer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class PkjsReadLimitTest {
    @Test fun acceptsTheCapAndRejectsTheNextInflatedByte() {
        val data = "x".repeat(MAX_PKJS_BYTES.toInt())
        assertEquals(data, Buffer().apply { write(data.encodeToByteArray()) }.readStringBounded(MAX_PKJS_BYTES))
        assertFailsWith<IllegalStateException> {
            Buffer().apply { write((data + "x").encodeToByteArray()) }.readStringBounded(MAX_PKJS_BYTES)
        }
    }

    @Test fun compressedPbwScriptCannotInflatePastTheLimit() {
        val file = java.io.File.createTempFile("pkjs-limit-", ".pbw")
        try {
            java.util.zip.ZipOutputStream(file.outputStream()).use { zip ->
                zip.putNextEntry(java.util.zip.ZipEntry("pebble-js-app.js"))
                val block = ByteArray(8192) { 32 }
                repeat((MAX_PKJS_BYTES / block.size).toInt() + 1) { zip.write(block) }
                zip.closeEntry()
            }
            kotlin.test.assertTrue(file.length() < 32768)
            assertFailsWith<IllegalStateException> {
                io.rebble.libpebblecommon.disk.pbw.PbwApp(kotlinx.io.files.Path(file.absolutePath))
                    .getPKJSFile().use { it.readStringBounded(MAX_PKJS_BYTES) }
            }
        } finally { file.delete() }
    }
}
