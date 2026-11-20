package coredevices.pebble.services

import io.rebble.libpebblecommon.connection.AppContext

internal actual fun hasDictationPermission(appContext: AppContext) = true

internal actual fun notifyDictationPermissionNeeded(appContext: AppContext) = Unit
