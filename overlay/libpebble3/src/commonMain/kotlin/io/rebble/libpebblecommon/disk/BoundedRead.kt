package io.rebble.libpebblecommon.disk

import kotlinx.io.Buffer
import kotlinx.io.Source
import kotlinx.io.readString

internal const val MAX_ZIP_JSON_BYTES = 1L shl 20
internal const val MAX_ZIP_TEXT_BYTES = 8L shl 20

/** Limit actual inflated bytes before making a String, regardless of ZIP entry size claims. */
internal fun Source.readStringBounded(max: Long): String {
    require(max >= 0 && max < Long.MAX_VALUE)
    val out = Buffer()
    while (true) {
        val count = readAtMostTo(out, minOf(8192L, max - out.size + 1))
        if (count == -1L) break
        check(out.size <= max) { "Archive text entry exceeds size limit" }
    }
    return out.readString()
}
