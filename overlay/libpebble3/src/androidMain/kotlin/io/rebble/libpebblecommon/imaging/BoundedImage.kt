package io.rebble.libpebblecommon.imaging

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri

internal data class ImageSnapshot(val bytes: ByteArray, val bitmap: Bitmap)
internal fun boundedImage(context: Context, uri: Uri): ImageSnapshot? {
    if (uri.scheme != "content" && uri.scheme != "android.resource") return null
    return try {
        val bytes = context.contentResolver.openInputStream(uri)?.use { source ->
            val sink = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(8192)
            while (true) {
                val count = source.read(buffer)
                if (count < 0) break
                if (sink.size() + count > 8 * 1024 * 1024) return null
                sink.write(buffer, 0, count)
            }
            sink.toByteArray()
        } ?: return null
        if (bytes.size > 8 * 1024 * 1024) return null
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth !in 1..8192 || bounds.outHeight !in 1..8192 ||
            bounds.outWidth.toLong() * bounds.outHeight > 32L * 1024 * 1024) return null
        val options = BitmapFactory.Options().apply {
            while (maxOf(bounds.outWidth, bounds.outHeight) / inSampleSize.coerceAtLeast(1) > 600) {
                inSampleSize = inSampleSize.coerceAtLeast(1) * 2
            }
        }
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options) ?: return null
        ImageSnapshot(bytes, bitmap)
    } catch (_: Exception) { null }
}
