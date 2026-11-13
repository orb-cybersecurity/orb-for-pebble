package coredevices.pebble.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ListItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.russhwolf.settings.Settings
import coredevices.pebble.firmware.GitHubFirmwareApi.Companion.PINNED_FIRMWARE_KEY
import coredevices.pebble.firmware.ReleaseVersion
import org.koin.compose.koinInject

/** Orb: a debug setting to pin the PebbleOS release offered to Core's watches. */
internal fun orbPinnedFirmwareSetting(): SettingsItem = SettingsItem(
    title = PINNED_FIRMWARE_TITLE,
    topLevelType = TopLevelType.Phone,
    section = Section.Debug,
    keywords = "firmware pebbleos version pin override downgrade",
    isDebugSetting = true,
    item = { PinnedFirmwareItem() },
)

private const val PINNED_FIRMWARE_TITLE = "PebbleOS version for Core watches"

@Composable
private fun PinnedFirmwareItem() {
    val settings: Settings = koinInject()
    var pinned by remember { mutableStateOf(settings.getStringOrNull(PINNED_FIRMWARE_KEY).orEmpty()) }
    var editing by remember { mutableStateOf(false) }
    ListItem(
        headlineContent = { Text(PINNED_FIRMWARE_TITLE) },
        supportingContent = {
            Text(
                if (pinned.isBlank()) "Newest release that passes Orb's checks"
                else "Pinned to v${pinned.removePrefix("v")}"
            )
        },
        modifier = Modifier.clickable { editing = true },
    )
    if (editing) {
        var text by remember { mutableStateOf(pinned) }
        AlertDialog(
            onDismissRequest = { editing = false },
            title = { Text("PebbleOS version") },
            text = {
                Column {
                    Text(
                        "Enter a tag from Core's PebbleOS releases on GitHub, e.g. v4.44.4, to offer " +
                            "that version to your watch, even if it is older than the one it runs. " +
                            "Leave empty to follow the newest release that passes Orb's checks."
                    )
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it.trim() },
                        singleLine = true,
                        placeholder = { Text("v4.44.4") },
                        modifier = Modifier.padding(top = 12.dp),
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = text.isBlank() || ReleaseVersion.parse(text) != null,
                    onClick = {
                        if (text.isBlank()) settings.remove(PINNED_FIRMWARE_KEY)
                        else settings.putString(PINNED_FIRMWARE_KEY, text)
                        pinned = text
                        editing = false
                    },
                ) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = { editing = false }) { Text("Cancel") }
            },
        )
    }
}
