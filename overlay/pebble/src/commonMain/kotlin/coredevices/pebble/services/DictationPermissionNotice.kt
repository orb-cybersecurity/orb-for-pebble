package coredevices.pebble.services

import io.rebble.libpebblecommon.connection.AppContext

internal expect fun notifyDictationPermissionNeeded(appContext: AppContext)
