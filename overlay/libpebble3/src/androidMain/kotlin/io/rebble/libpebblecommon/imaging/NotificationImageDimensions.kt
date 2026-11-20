package io.rebble.libpebblecommon.imaging

import android.content.Context
import android.content.res.AssetFileDescriptor
import android.graphics.BitmapFactory
import android.media.ExifInterface
import android.net.Uri
import android.os.CancellationSignal
import java.io.Closeable

internal suspend fun notificationImageDimensions(context: Context, uri: Uri): Pair<Int, Int>? {
    if (uri.scheme != "content" && uri.scheme != "android.resource") return null
    return readImageWithTimeout { resources ->
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        val descriptor = openImageDescriptor(context, uri, resources) ?: return@readImageWithTimeout null
        val total = descriptor.use { afd ->
            val length = afd.length.takeIf { it >= 0 } ?: afd.parcelFileDescriptor.statSize
            if (length > MAX_ENCODED_IMAGE_BYTES) return@readImageWithTimeout null
            val stream = resources.track(afd.createInputStream())
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
        val exif = openImageDescriptor(context, uri, resources) ?: return@readImageWithTimeout null
        val orientation = exif.use { afd ->
            ImageSliceInputStream(resources.track(afd.createInputStream()), total).use {
                ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            }
        }
        if (orientation in 5..8) bounds.outHeight to bounds.outWidth else bounds.outWidth to bounds.outHeight
    }
}

private fun openImageDescriptor(context: Context, uri: Uri, resources: ImageReadResources): AssetFileDescriptor? {
    val signal = CancellationSignal()
    resources.track(Closeable { signal.cancel() })
    return context.contentResolver.openAssetFileDescriptor(uri, "r", signal)?.let { resources.track(it) }
}
