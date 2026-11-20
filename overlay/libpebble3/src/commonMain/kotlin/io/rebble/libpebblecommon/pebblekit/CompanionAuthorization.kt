package io.rebble.libpebblecommon.pebblekit

internal suspend fun authorizedCompanion(
    callers: Collection<String>, associated: Collection<String>, granted: suspend (String) -> Boolean,
): Boolean = callers.any { it in associated && granted(it) }
