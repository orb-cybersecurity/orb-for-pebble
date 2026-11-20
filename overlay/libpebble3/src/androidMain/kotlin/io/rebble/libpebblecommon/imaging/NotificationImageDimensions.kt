package io.rebble.libpebblecommon.imaging

import android.content.Context
import android.graphics.BitmapFactory
import android.media.ExifInterface
import android.net.Uri

internal suspend fun notificationImageDimensions(context: Context, uri: Uri): Pair<Int, Int>? {
    if (uri.scheme != "content" && uri.scheme != "android.resource") return null
    return readImageWithTimeout { resources ->
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        val (stream, length) = openImageStream(context, uri, resources) ?: return@readImageWithTimeout null
        val total = stream.use {
            if (length > MAX_ENCODED_IMAGE_BYTES) return@readImageWithTimeout null
            if (length >= 0) {
                ImageSliceInputStream(stream, length.toInt()).use {
                    BitmapFactory.decodeStream(it, null, bounds)
                }
                length.toInt()
            } else {
                EncodedImageInputStream(stream).use { counted ->
                    BitmapFactory.decodeStream(counted, null, bounds)
                    // Only pipes/unknown-length streams need a full count.
                    val buffer = ByteArray(8192)
                    while (counted.read(buffer) != -1) { }
                    counted.totalBytes
                }
            }
        }
        if (bounds.outWidth !in 1..8192 || bounds.outHeight !in 1..8192 ||
            bounds.outWidth.toLong() * bounds.outHeight > 32L * 1024 * 1024) return@readImageWithTimeout null
        val (exif, exifLength) = openImageStream(context, uri, resources) ?: return@readImageWithTimeout null
        val orientation = exif.use { source ->
            (if (exifLength < 0) EncodedImageInputStream(source) else ImageSliceInputStream(source, total)).use {
                ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            }
        }
        if (orientation in 5..8) bounds.outHeight to bounds.outWidth else bounds.outWidth to bounds.outHeight
    }
}
