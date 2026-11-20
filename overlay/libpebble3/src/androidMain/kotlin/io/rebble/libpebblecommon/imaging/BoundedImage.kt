package io.rebble.libpebblecommon.imaging

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.CancellationSignal
import java.io.Closeable
import java.io.InputStream

/** Resource URIs may be compressed; only content providers support cancellable descriptor opens. */
internal fun openImageStream(context: Context, uri: Uri, resources: ImageReadResources): Pair<InputStream, Long>? {
    if (uri.scheme == "android.resource") {
        // Local and never blocking. Not tracked: an asset stream is unsafe to close from another thread.
        return context.contentResolver.openInputStream(uri)?.let { it to -1L }
    }
    if (uri.scheme != "content") return null
    val signal = CancellationSignal()
    resources.track(Closeable { signal.cancel() })
    val descriptor = context.contentResolver.openAssetFileDescriptor(uri, "r", signal)
        ?.let { resources.track(it) } ?: return null
    val length = descriptor.length.takeIf { it >= 0 } ?: descriptor.parcelFileDescriptor.statSize
    return resources.track(descriptor.createInputStream()) to length
}

internal data class ImageSnapshot(val bytes: ByteArray, val bitmap: Bitmap, val width: Int, val height: Int)
internal fun boundedImage(context: Context, uri: Uri, resources: ImageReadResources): ImageSnapshot? {
    if (uri.scheme != "content" && uri.scheme != "android.resource") return null
    return try {
        val (stream, length) = openImageStream(context, uri, resources) ?: return null
        if (length > MAX_ENCODED_IMAGE_BYTES) return null
        val bytes = stream.use { source ->
            val sink = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(8192)
            while (true) {
                val count = source.read(buffer)
                if (count < 0) break
                if (sink.size() + count > MAX_ENCODED_IMAGE_BYTES) return null
                sink.write(buffer, 0, count)
            }
            sink.toByteArray()
        }
        if (bytes.size > MAX_ENCODED_IMAGE_BYTES) return null
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
        ImageSnapshot(bytes, bitmap, bounds.outWidth, bounds.outHeight)
    } catch (_: Exception) { null }
}
