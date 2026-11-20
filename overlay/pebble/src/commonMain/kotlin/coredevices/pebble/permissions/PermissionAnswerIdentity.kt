package coredevices.pebble.permissions

import io.ktor.http.encodeURLPathPart
import kotlin.uuid.Uuid

/** Extras aren't part of PendingIntent identity; the displayed set and display id must be. */
internal fun permissionAnswerIdentity(app: Uuid, permissions: List<String>, requestId: String, granted: Boolean): String =
    "orb-permission://answer/$app/${requestId.encodeURLPathPart()}/$granted/" +
        permissions.sorted().joinToString("/") { it.encodeURLPathPart() }
