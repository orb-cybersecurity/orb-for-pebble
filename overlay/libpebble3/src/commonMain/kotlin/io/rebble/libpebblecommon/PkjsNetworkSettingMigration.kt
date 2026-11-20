package io.rebble.libpebblecommon

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** Remove retired watch settings while retaining every other saved preference. */
internal fun migrateRemovedWatchSettings(stored: JsonElement): JsonElement {
    val root = stored as? JsonObject ?: return stored
    val watch = root["watchConfig"] as? JsonObject ?: return stored
    val retained = watch - setOf("pkjsRequestsThroughApp", "enableLegacyPebbleKit")
    if (retained.size == watch.size) return stored
    return JsonObject(root + ("watchConfig" to JsonObject(retained)))
}
