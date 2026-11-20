package coredevices.pebble

import android.provider.OpenableColumns
import com.eygraber.uri.Uri
import com.eygraber.uri.toAndroidUri
import io.rebble.libpebblecommon.connection.AppContext
import io.rebble.libpebblecommon.util.getTempFilePath
import kotlinx.io.files.Path
import kotlin.uuid.Uuid

actual fun readNameFromContentUri(appContext: AppContext, uri: Uri): String? = try {
    appContext.context.contentResolver.query(uri.toAndroidUri(), arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
        if (it.moveToFirst()) it.getString(0) else null
    }
} catch (_: Exception) { null }

/** Only granted content URIs; no app-private file paths. Runs on the import IO worker. */
actual fun writeFile(appContext: AppContext, uri: Uri): Path? {
    if (uri.scheme != "content") return null
    val path = getTempFilePath(appContext, "sideloaded_file_${Uuid.random()}")
    val file = java.io.File(path.toString())
    var complete = false
    try {
        val input = appContext.context.contentResolver.openInputStream(uri.toAndroidUri()) ?: return null
        input.use { source ->
            file.outputStream().use { sink ->
                val buffer = ByteArray(8192)
                var total = 0L
                while (true) {
                    val count = source.read(buffer)
                    if (count < 0) break
                    total += count
                    require(total <= 32L * 1024 * 1024) { "Import too large" }
                    sink.write(buffer, 0, count)
                }
            }
        }
        complete = true
        return path
    } catch (_: Exception) {
        return null
    } finally {
        if (!complete) file.delete()
    }
}
