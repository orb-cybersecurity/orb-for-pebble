package io.rebble.libpebblecommon.pebblekit

import io.rebble.libpebblecommon.di.LibPebbleKoinComponent
import io.rebble.libpebblecommon.disk.pbw.PbwApp
import io.rebble.libpebblecommon.locker.Locker
import io.rebble.libpebblecommon.locker.LockerPBWCache
import io.rebble.libpebblecommon.metadata.pbw.appinfo.pebbleKit2Packages
import io.rebble.libpebblecommon.permissions.AppPermissions
import io.rebble.libpebblecommon.permissions.PermissionDecision
import io.rebble.libpebblecommon.permissions.pebbleKit2Key
import kotlinx.coroutines.flow.first
import kotlin.uuid.Uuid

internal object PebbleKitAuthorization : LibPebbleKoinComponent {
    private suspend fun packages(uuid: Uuid): List<String> {
        val locker = getKoin().getOrNull<Locker>() ?: return emptyList()
        val entry = locker.getLockerApp(uuid).first() ?: return emptyList()
        val path = getKoin().get<LockerPBWCache>().cachedPBWFileForApp(uuid, entry.properties.version.orEmpty())
            ?: return emptyList()
        return try { PbwApp(path).info.pebbleKit2Packages() } catch (_: Exception) { emptyList() }
    }

    suspend fun allowed(callers: Collection<String>, uuid: Uuid): Boolean =
        authorizedCompanion(callers, packages(uuid)) { pkg ->
            getKoin().get<AppPermissions>().request(uuid, pebbleKit2Key(pkg)) == PermissionDecision.Granted
        }

    suspend fun associated(callers: Collection<String>): Boolean {
        if (callers.isEmpty()) return false
        val locker = getKoin().getOrNull<Locker>() ?: return false
        return locker.getAllLockerUuids().first().any { uuid ->
            authorizedCompanion(callers, packages(uuid)) { true }
        }
    }
}
