package io.rebble.libpebblecommon.pebblekit

import io.rebble.libpebblecommon.database.dao.LockerAppPermissionDao
import io.rebble.libpebblecommon.di.LibPebbleKoinComponent
import io.rebble.libpebblecommon.locker.Locker
import io.rebble.libpebblecommon.permissions.AppPermissions
import io.rebble.libpebblecommon.permissions.PermissionDecision
import io.rebble.libpebblecommon.permissions.pebbleKit2Key
import kotlinx.coroutines.flow.first
import kotlin.uuid.Uuid

internal object PebbleKitAuthorization : LibPebbleKoinComponent {
    private suspend fun packages(uuid: Uuid): List<String> {
        val locker = getKoin().getOrNull<Locker>() ?: return emptyList()
        if (locker.getLockerApp(uuid).first() == null) return emptyList()
        return recordedCompanionPackages(getKoin().get<LockerAppPermissionDao>().getByAppUuid(uuid))
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
