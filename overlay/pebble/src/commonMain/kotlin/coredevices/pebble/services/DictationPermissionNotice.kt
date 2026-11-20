package coredevices.pebble.services

import io.rebble.libpebblecommon.connection.AppContext

internal expect fun hasDictationPermission(appContext: AppContext): Boolean

internal expect fun notifyDictationPermissionNeeded(appContext: AppContext)
