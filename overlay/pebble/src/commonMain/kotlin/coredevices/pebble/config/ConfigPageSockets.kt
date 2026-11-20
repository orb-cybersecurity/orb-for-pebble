package coredevices.pebble.config

import io.ktor.client.HttpClient
import io.rebble.libpebblecommon.js.WebSocketManager
import io.rebble.libpebblecommon.js.configPageSocketManager
import io.rebble.libpebblecommon.permissions.DataUsageRecorder
import io.rebble.libpebblecommon.permissions.NetworkAccess
import kotlinx.coroutines.CoroutineScope
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlin.uuid.Uuid

/** Only the origin-checked main-frame bridge can dispatch these non-blocking socket commands. */
internal class ConfigPageSockets private constructor(
    private val eval: (String) -> Unit,
    private val newManager: ((String) -> Unit) -> WebSocketManager,
) : AutoCloseable {
    constructor(scope: CoroutineScope, uuid: Uuid, eval: (String) -> Unit,
                client: HttpClient, network: NetworkAccess, dataUsage: DataUsageRecorder) :
        this(eval, { events -> WebSocketManager(scope, events, client, uuid, network, dataUsage) })

    companion object {
        fun create(scope: CoroutineScope, uuid: Uuid, eval: (String) -> Unit): ConfigPageSockets {
            return ConfigPageSockets(eval) { events -> configPageSocketManager(scope, uuid, events) }
        }
    }
    private var document: String? = null
    private var sockets: WebSocketManager? = null

    fun dispatch(message: JsonElement): String {
        val call = Json.decodeFromJsonElement(Call.serializer(), message)
        require(call.document.length in 1..100)
        require(call.method in listOf("createInstance", "send", "close"))
        if (document != call.document) {
            require(call.method == "createInstance")
            close()
            document = call.document
            val token = Json.encodeToString(call.document)
            sockets = newManager { js ->
                eval("if (window.__orbSocketDocument === $token) { $js; }")
            }
        }
        val args = call.args.map { value ->
            when {
                value is JsonNull -> null
                value.isString -> value.content
                else -> value.booleanOrNull ?: value.doubleOrNull
            }
        }
        sockets!!.dispatch(call.method, args)
        return "null"
    }

    override fun close() {
        sockets?.close()
        sockets = null
        document = null
    }

    @Serializable
    private data class Call(val document: String, val method: String, val args: List<JsonPrimitive>)
}
