package coredevices.pebble.config

import io.rebble.libpebblecommon.permissions.AppPermissionStatus
import io.rebble.libpebblecommon.permissions.PermissionStatus
import io.rebble.libpebblecommon.permissions.permissionOf
import io.rebble.libpebblecommon.plugin.PluginPermissions
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/** CSP blocks every browser socket, including fresh frame realms. Native sockets check live. */
internal fun configPageCsp(domains: List<String>?, expectedUrl: String): String {
    val sources = domains?.flatMap { domain ->
        listOf("https", "http").flatMap { scheme -> listOf("$scheme://$domain", "$scheme://*.$domain") }
    } ?: listOf("https:", "http:")
    val resources = (sources + listOfNotNull(configPageOrigin(expectedUrl))).distinct().joinToString(" ")
    val connect = sources.ifEmpty { listOf("'none'") }.joinToString(" ")
    return "default-src $resources 'unsafe-inline' 'unsafe-eval' data: blob:; connect-src $connect; " +
        "frame-src ${resources.ifEmpty { "'none'" }}; worker-src 'none'; object-src 'none'; " +
        "form-action ${resources.ifEmpty { "'none'" }} pebblejs:"
}

internal fun configPageNetworkRevoked(before: List<AppPermissionStatus>, after: List<AppPermissionStatus>?): Boolean {
    val network = setOf(PluginPermissions.INTERNET, PluginPermissions.GLOBAL_INTERNET, PluginPermissions.LOCAL_NETWORK)
    fun granted(status: PermissionStatus) = status == PermissionStatus.Granted || status == PermissionStatus.AllowedAutomatically
    return before.any { old ->
        permissionOf(old.permission) in network && granted(old.status) &&
            after.orEmpty().none { it.permission == old.permission && granted(it.status) }
    }
}

/** Usage timestamps and new permission requests don't close a page; losing a grant does. */
internal fun configPageNetworkRevocations(statuses: Flow<List<AppPermissionStatus>?>): Flow<Unit> = flow {
    var previous = emptyList<AppPermissionStatus>()
    statuses.collect { current ->
        if (configPageNetworkRevoked(previous, current)) emit(Unit)
        previous = current.orEmpty()
    }
}
