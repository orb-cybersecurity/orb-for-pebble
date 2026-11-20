package coredevices.pebble.permissions

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.uuid.Uuid

class PermissionAnswerIdentityTest {
    private val app = Uuid.parse("00000000-0000-0000-0000-000000000001")
    @Test fun actionsCannotSubstituteAnotherDisplayedSetOrRequest() {
        fun id(keys: List<String>, request: String = "first", grant: Boolean = true) =
            permissionAnswerIdentity(app, keys, request, grant)
        assertNotEquals(id(listOf("Location")), id(listOf("Location", "GlobalInternet")))
        assertEquals(id(listOf("Location", "GlobalInternet")), id(listOf("GlobalInternet", "Location")))
        assertNotEquals(id(listOf("Location")), id(listOf("Location"), "second"))
        assertNotEquals(id(listOf("Location")), id(listOf("Location"), grant = false))
        assertNotEquals(id(listOf("Internet/a", "b")), id(listOf("Internet", "a/b")))
        assertNotEquals(id(listOf("Location")), permissionAnswerIdentity(Uuid.random(), listOf("Location"), "first", true))
    }

    @Test fun aStalePhoneActionCanAnswerOnlyItsOwnPermissionSnapshot() = kotlinx.coroutines.test.runTest {
        val otherApp = Uuid.random()
        var decisions = emptyMap<String, Boolean>()
        val waiting = listOf(
            io.rebble.libpebblecommon.database.entity.LockerAppPermission(app, "Location", null, 0),
            io.rebble.libpebblecommon.database.entity.LockerAppPermission(app, "GlobalInternet", null, 0),
            io.rebble.libpebblecommon.database.entity.LockerAppPermission(otherApp, "Location", null, 0),
        )
        val lib = object : io.rebble.libpebblecommon.connection.LibPebble by io.rebble.libpebblecommon.connection.FakeLibPebble() {
            override fun activePermissionRequests() = kotlinx.coroutines.flow.flowOf(waiting)
            override suspend fun setPermissionDecisions(appUuid: Uuid, answer: Map<String, Boolean>) {
                assertEquals(app, appUuid)
                decisions = answer
            }
        }
        answerPermissionRequests(lib, app, listOf("Location", "Calendar"), true)
        assertEquals(mapOf("Location" to true), decisions)
    }
}
