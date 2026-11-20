package io.rebble.libpebblecommon.pebblekit

internal suspend fun authorizedCompanion(
    callers: Collection<String>, associated: Collection<String>, granted: suspend (String) -> Boolean,
): Boolean = callers.any { it in associated && granted(it) }

/** Companion rows survive PBW eviction, including old installs without the declared flag. */
internal fun recordedCompanionPackages(
    rows: List<io.rebble.libpebblecommon.database.entity.LockerAppPermission>,
): List<String> = rows.mapNotNull {
    io.rebble.libpebblecommon.permissions.packageOf(it.permission)?.takeIf { pkg ->
        pkg.isNotBlank() && it.permission == io.rebble.libpebblecommon.permissions.pebbleKit2Key(pkg)
    }
}

/** Do not enumerate connected watches until the caller is authorized. */
internal suspend fun <K, V> companionResults(allowed: Boolean, enumerate: suspend () -> Map<K, V>): Map<K, V> =
    if (allowed) enumerate() else emptyMap()
