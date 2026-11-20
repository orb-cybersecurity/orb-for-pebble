package io.rebble.libpebblecommon.js

import io.ktor.http.decodeURLPart
import io.ktor.http.parseQueryString

data class ConfigCloseCallback(val data: String, val state: String?)

private const val CLOSE_PREFIX = "pebblejs://close"

private fun closeUrl(raw: String): String? = runCatching {
    val url = if (raw.startsWith(CLOSE_PREFIX)) raw else raw.decodeURLPart()
    url.takeIf {
        it.startsWith(CLOSE_PREFIX) &&
            (it.length == CLOSE_PREFIX.length || it[CLOSE_PREFIX.length] in "#?/")
    }
}.getOrNull()

fun isConfigCloseUrl(raw: String): Boolean = closeUrl(raw) != null

/** Decode the payload once, preserving the query-style callbacks accepted by older pages. */
fun parseConfigCloseUrl(raw: String): ConfigCloseCallback? = runCatching {
    var suffix = (closeUrl(raw) ?: return null).removePrefix(CLOSE_PREFIX)
    if (suffix.startsWith('/')) suffix = suffix.drop(1)
    val query = if (suffix.startsWith('?')) suffix.drop(1).substringBefore('#') else ""
    val states = parseQueryString(query).getAll("orb_state")
    if (states != null && (states.size != 1 || states.single().isEmpty())) return null
    val state = states?.single()
    val payload = when {
        suffix.startsWith('#') -> suffix.drop(1)
        suffix.startsWith('?') && '#' in suffix -> suffix.substringAfter('#')
        suffix.startsWith('?') && state == null -> suffix.drop(1)
        suffix.startsWith('?') -> return null // A state is not a settings payload.
        else -> suffix
    }
    ConfigCloseCallback(payload.decodeURLPart(), state)
}.getOrNull()
