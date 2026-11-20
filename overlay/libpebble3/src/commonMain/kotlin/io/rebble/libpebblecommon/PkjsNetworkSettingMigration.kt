package io.rebble.libpebblecommon

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** Remove the obsolete opt-out while retaining every other saved preference. */
internal fun migratePkjsNetworkSetting(stored: JsonElement): JsonElement {
    val root = stored as? JsonObject ?: return stored
    val watch = root["watchConfig"] as? JsonObject ?: return stored
    if ("pkjsRequestsThroughApp" !in watch) return stored
    return JsonObject(root + ("watchConfig" to JsonObject(watch - "pkjsRequestsThroughApp")))
}
