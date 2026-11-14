package coredevices.coreapp

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.w3c.dom.Element

/**
 * Android's backup (Seedvault on GrapheneOS) is how Orb's data reaches a new phone. These tests
 * fail when the backup rules stop matching where the app keeps its data.
 */
class BackupRulesTest {
    // Tests run in mobileapp/composeApp.
    private val app = File("..").canonicalFile
    private val xml = app.resolve("androidApp/src/main/res/xml")

    /** What a restored phone needs: databases (locker, watches, settings), the settings file and sideloaded apps. */
    private val needed = setOf("database:.", "sharedpref:.", "file:pbw/")

    private fun parse(file: File): Element =
        DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
            .newDocumentBuilder().parse(file).documentElement

    private fun Element.children(tag: String): List<Element> {
        val nodes = getElementsByTagName(tag)
        return (0 until nodes.length).map { nodes.item(it) as Element }.filter { it.parentNode == this }
    }

    private fun Element.rules(tag: String) = children(tag).map { "${it.getAttribute("domain")}:${it.getAttribute("path")}" }.toSet()

    @Test
    fun bothBackupKindsCopyWhatARestoreNeeds() {
        val rules = parse(xml.resolve("data_extraction_rules.xml"))
        for (kind in listOf("cloud-backup", "device-transfer")) {
            val section = rules.children(kind).singleOrNull() ?: error("no <$kind> section")
            assertEquals(needed, section.rules("include"), "<$kind> includes")
            assertEquals(emptySet(), section.rules("exclude"), "<$kind> excludes")
        }
        val cloud = rules.children("cloud-backup").single()
        assertEquals("true", cloud.getAttribute("disableIfNoEncryptionCapabilities"),
            "cloud backup must be skipped by services that don't encrypt on the phone")
    }

    @Test
    fun olderAndroidVersionsCopyTheSameEncryptedOnly() {
        val rules = parse(xml.resolve("backup_rules.xml"))
        assertEquals(needed, rules.rules("include"))
        for (include in rules.children("include")) {
            assertTrue("clientSideEncryption" in include.getAttribute("requireFlags").split("|"),
                "${include.getAttribute("domain")}:${include.getAttribute("path")} must require client-side encryption")
        }
    }

    @Test
    fun manifestAllowsBackupWithOrbsRules() {
        val application = parse(app.resolve("androidApp/src/main/AndroidManifest.xml")).children("application").single()
        val android = "http://schemas.android.com/apk/res/android"
        assertEquals("true", application.getAttributeNS(android, "allowBackup"))
        assertEquals("@xml/backup_rules", application.getAttributeNS(android, "fullBackupContent"))
        assertEquals("@xml/data_extraction_rules", application.getAttributeNS(android, "dataExtractionRules"))
    }

    @Test
    fun lockerKeepsSideloadedAppsInTheIncludedDirectory() {
        val locker = app.resolve("libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/locker/Locker.android.kt")
        assertTrue(Regex("""filesDir\.resolve\("pbw"\)""").containsMatchIn(locker.readText()),
            "the locker no longer keeps its files in files/pbw; move the backup rule with it")
    }

    /**
     * Keystore keys never leave the phone that made them, so encrypted values in a backup can't be
     * read after a restore. Each place that stores them must treat such a value as not set.
     * KeystoreSecureStorage drops it and returns null (checked on a device by RestoredDataTest).
     */
    @Test
    fun keystoreEncryptedStorageIsOnlyWhereRestoresAreHandled() {
        val handled = setOf("libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/storage/KeystoreSecureStorage.kt")
        val found = app.walkTopDown()
            .onEnter { it.name != "build" && !it.name.startsWith(".") }
            .filter { it.isFile && it.extension == "kt" && "src/" in it.path && "Test" !in it.parentFile.path }
            .filter { "AndroidKeyStore" in it.readText() }
            .map { it.relativeTo(app).path }
            .toSet()
        val unhandled = found - handled
        assertTrue(unhandled.isEmpty(),
            "Keystore-encrypted data in $unhandled: a backup copies it but a restored phone can't decrypt it. " +
                "Make it read as not set when decryption fails, test that in RestoredDataTest, then list it here.")
        assertEquals(handled, found, "KeystoreSecureStorage moved; update this test")
    }
}
