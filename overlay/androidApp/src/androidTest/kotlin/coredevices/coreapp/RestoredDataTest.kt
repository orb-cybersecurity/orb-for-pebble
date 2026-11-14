package coredevices.coreapp

import android.content.Context
import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.SQLiteConnection
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import androidx.sqlite.execSQL
import androidx.test.platform.app.InstrumentationRegistry
import coredevices.database.CoreDatabase
import coredevices.database.CoreDatabaseConstructor
import coredevices.database.DropCoreTelemetryTables
import io.rebble.libpebblecommon.storage.KeystoreSecureStorage
import java.security.KeyStore
import org.junit.After
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlinx.coroutines.runBlocking

/**
 * What a phone restored from Android's backup sees: data written by an older Orb, and encrypted
 * values whose key stayed on the old phone. Runs on a device: the Keystore and Room's SQLite
 * aren't available to host tests.
 */
class RestoredDataTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context: Context = instrumentation.targetContext
    private val name = "orb_restored_data_test"

    @After
    fun cleanUp() {
        runBlocking { KeystoreSecureStorage(context, keyAlias = name, prefsName = name).destroy() }
        context.getDatabasePath("$name.db").delete()
    }

    @Test
    fun secretFromAnotherPhoneReadsAsNotSet() = runBlocking {
        val storage = KeystoreSecureStorage(context, keyAlias = name, prefsName = name)
        storage.set("token", "secret")
        assertEquals("secret", storage.get("token"))

        // A restore brings back the encrypted value but not the key.
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(name)
        assertNull(storage.get("token"))
        assertFalse(context.getSharedPreferences(name, Context.MODE_PRIVATE).contains("token"),
            "an unreadable value must be dropped, not retried on every read")

        // Storage still works afterwards, under a new key.
        storage.set("token", "new")
        assertEquals("new", storage.get("token"))
    }

    @Test
    fun damagedValueReadsAsNotSet() = runBlocking {
        context.getSharedPreferences(name, Context.MODE_PRIVATE).edit().putString("token", "not a stored value").commit()
        assertNull(KeystoreSecureStorage(context, keyAlias = name, prefsName = name).get("token"))
    }

    @Test
    fun backupFromCoreSchemaUpgradesAndKeepsStores() {
        val helper = MigrationTestHelper(
            instrumentation = instrumentation,
            file = context.getDatabasePath("$name.db"),
            driver = BundledSQLiteDriver(),
            databaseClass = CoreDatabase::class,
            databaseFactory = { CoreDatabaseConstructor.initialize() },
            autoMigrationSpecs = listOf(DropCoreTelemetryTables()),
        )
        // Version 11: Core's schema and Orb's up to 1.18.0.1-orb2.
        helper.createDatabase(11).apply {
            execSQL("INSERT INTO AppstoreSource (url, title) VALUES ('https://example.org/feed', 'Example')")
            execSQL("INSERT INTO memfault_chunks (serial, chunkData, createdAt) VALUES ('X', x'00', 0)")
            close()
        }
        helper.runMigrationsAndValidate(12).apply {
            val tables = query("SELECT name FROM sqlite_master WHERE type = 'table'")
            for (dropped in listOf("HeartbeatStateEntity", "memfault_chunks", "analytics_heartbeats", "sync_tasks")) {
                assertFalse(dropped in tables, "$dropped should be gone")
            }
            assertEquals(listOf("https://example.org/feed"), query("SELECT url FROM AppstoreSource"))
            close()
        }
    }

    private fun SQLiteConnection.query(sql: String): List<String> = prepare(sql).use { statement ->
        buildList { while (statement.step()) add(statement.getText(0)) }
    }
}
