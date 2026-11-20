package coredevices.coreapp.ui.screens

import DocumentAttachment
import java.nio.file.Files
import java.util.zip.ZipFile
import kotlinx.coroutines.runBlocking
import kotlinx.io.Buffer
import kotlinx.io.files.Path
import kotlin.test.Test
import kotlin.test.assertEquals

class BugReportArchiveTest {
    @Test fun descriptionAndLogsSurviveTheArchive() = runBlocking {
        val description = "Watch froze after café ☕\nSteps to reproduce:\n1. Open settings\n2. Dictate a reply\n"
        val logs = "local watch log\n"
        val file = Files.createTempFile("orb-report-", ".zip").toFile()
        try {
            writeBugReportZip(Path(file.path), description, listOf(DocumentAttachment(
                fileName = "watch-logs.txt",
                mimeType = "text/plain",
                source = Buffer().apply { write(logs.encodeToByteArray()) },
                size = logs.encodeToByteArray().size.toLong(),
            )))
            ZipFile(file).use { zip ->
                assertEquals(setOf("problem-description.txt", "watch-logs.txt"), zip.entries().asSequence().map { it.name }.toSet())
                assertEquals(description, zip.getInputStream(zip.getEntry("problem-description.txt")).reader(Charsets.UTF_8).use { it.readText() })
                assertEquals(logs, zip.getInputStream(zip.getEntry("watch-logs.txt")).reader(Charsets.UTF_8).use { it.readText() })
            }
        } finally { file.delete() }
    }

    @Test fun emptyDescriptionStillProducesAShareableArchive() = runBlocking {
        val file = Files.createTempFile("orb-report-", ".zip").toFile()
        try {
            writeBugReportZip(Path(file.path), "", emptyList())
            ZipFile(file).use { zip ->
                assertEquals("", zip.getInputStream(zip.getEntry("problem-description.txt")).reader().use { it.readText() })
            }
        } finally { file.delete() }
    }
}
