package io.rebble.libpebblecommon.disk

import io.rebble.libpebblecommon.disk.pbw.PbwApp
import io.rebble.libpebblecommon.disk.pbz.PbzFirmware
import io.rebble.libpebblecommon.metadata.WatchType
import kotlinx.io.Buffer
import kotlinx.io.RawSource
import kotlinx.io.buffered
import kotlinx.io.files.Path
import kotlinx.io.writeString
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import java.util.zip.ZipInputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ArchiveMetadataLimitTest {
    private fun bomb(vararg entries: Pair<String, Long>, smallEntries: Map<String, ByteArray> = emptyMap(), check: (Path) -> Unit) {
        val file = File.createTempFile("metadata-limit-", ".zip")
        try {
            ZipOutputStream(file.outputStream()).use { zip ->
                for ((name, bytes) in smallEntries) {
                    zip.putNextEntry(ZipEntry(name))
                    zip.write(bytes)
                    zip.closeEntry()
                }
                val chunk = ByteArray(8192) { ' '.code.toByte() }
                for ((name, size) in entries) {
                    zip.putNextEntry(ZipEntry(name))
                    var remaining = size
                    while (remaining > 0) {
                        val count = minOf(remaining, chunk.size.toLong()).toInt()
                        zip.write(chunk, 0, count)
                        remaining -= count
                    }
                    zip.closeEntry()
                }
            }
            assertTrue(file.length() < 128 * 1024, "The compressed import limit must not mask this test")
            check(Path(file.absolutePath))
        } finally {
            file.delete()
        }
    }

    private fun rejected(block: () -> Unit) {
        assertEquals("Archive text entry exceeds size limit", assertFailsWith<IllegalStateException>(block = block).message)
    }

    @Test fun pbwAppInfoBombIsRejectedBeforeParsing() = bomb("appinfo.json" to (64L shl 20)) {
        rejected { PbwApp(it).info }
    }

    @Test fun rootAndPlatformPbwManifestBombsAreRejected() {
        for ((name, platform) in listOf("manifest.json" to WatchType.APLITE, "aplite/manifest.json" to WatchType.APLITE, "chalk/manifest.json" to WatchType.CHALK)) {
            bomb(name to (MAX_ZIP_JSON_BYTES + 1)) { rejected { PbwApp(it).getManifest(platform) } }
        }
    }

    @Test fun pbzRootAndSlotManifestBombsAreRejected() {
        for (dir in listOf("", "slot0/", "slot1/")) {
            val small = if (dir == "slot1/") {
                val manifest = ZipInputStream(javaClass.classLoader!!.getResourceAsStream("normal_obelix_test.pbz")!!).use { zip ->
                    var entry = zip.nextEntry
                    while (entry != null && entry.name != "slot0/manifest.json") entry = zip.nextEntry
                    check(entry != null) { "Fixture must contain slot0/manifest.json" }
                    zip.readBytes()
                }
                mapOf("slot0/manifest.json" to manifest)
            } else emptyMap()
            bomb("${dir}manifest.json" to (MAX_ZIP_JSON_BYTES + 1), smallEntries = small) {
                rejected { PbzFirmware(it).manifests }
            }
        }
    }

    @Test fun archiveTextHasItsOwnLargerBound() = bomb("config.html" to (MAX_ZIP_TEXT_BYTES + 1)) {
        rejected { PbwApp(it).getTextFile("config.html") }
    }

    @Test fun readerAcceptsTheExactLimitAndConsumesOnlyOneExtraByteToReject() {
        assertEquals("1234", Buffer().apply { writeString("1234") }.readStringBounded(4))
        var consumed = 0L
        val source = object : RawSource {
            override fun readAtMostTo(sink: Buffer, byteCount: Long): Long {
                val count = minOf(8192L, byteCount)
                sink.write(ByteArray(count.toInt()))
                consumed += count
                return count
            }
            override fun close() = Unit
        }.buffered()
        source.use { rejected { it.readStringBounded(MAX_ZIP_JSON_BYTES) } }
        assertTrue(consumed <= MAX_ZIP_JSON_BYTES + 8192)
    }
}
