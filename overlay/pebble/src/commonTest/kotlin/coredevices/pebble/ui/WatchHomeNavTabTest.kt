package coredevices.pebble.ui

import coredevices.pebble.ui.WatchHomeNavTab.Health
import coredevices.pebble.ui.WatchHomeNavTab.Notifications
import coredevices.pebble.ui.WatchHomeNavTab.Settings
import coredevices.pebble.ui.WatchHomeNavTab.WatchFaces
import coredevices.pebble.ui.WatchHomeNavTab.Watches
import coredevices.util.CoreConfig
import kotlin.test.Test
import kotlin.test.assertEquals

class WatchHomeNavTabTest {
    private val migrated = listOf("WatchFaces", "Watches", "Health", "Notifications", "Settings")

    private fun bar(config: CoreConfig, healthEnabled: Boolean) =
        WatchHomeNavTab.barTabs(config, WatchHomeNavTab.availableTabs(config, healthEnabled))

    @Test
    fun migratedBarMatchesLegacyBarWhenEverythingFits() {
        for (health in listOf(false, true)) {
            val legacy = buildList {
                add(WatchFaces)
                add(Watches)
                if (health) add(Health)
                add(Notifications)
                add(Settings)
            }
            assertEquals(legacy, bar(CoreConfig(navBarTabs = migrated), health), "health=$health")
        }
    }

    @Test
    fun overflowLeavesASlotForMore() {
        val config = CoreConfig(navBarTabs = migrated, navBarSlots = 4)
        assertEquals(listOf(WatchFaces, Watches, Health), bar(config, healthEnabled = true))
    }

    @Test
    fun slotsAreCappedToBarCapacity() {
        assertEquals(WatchHomeNavTab.MAX_BAR_SLOTS, WatchHomeNavTab.barSlots(CoreConfig(navBarSlots = 12)))
        assertEquals(2, WatchHomeNavTab.barSlots(CoreConfig(navBarSlots = 0)))
    }

    @Test
    fun fewerSlotsMovesTabsUnderMore() {
        val config = CoreConfig(navBarTabs = migrated, navBarSlots = 3)
        assertEquals(listOf(WatchFaces, Watches), bar(config, healthEnabled = false))
    }

    // "Index" is the tab of Core's Index 01 ring, which Orb doesn't have; configs saved by
    // Core's app may still name it.
    @Test
    fun orderSkipsUnknownNamesAndAppendsMissingTabs() {
        val config = CoreConfig(navBarTabs = listOf("Settings", "Index", "Gone", "Watches"))
        assertEquals(
            listOf(Settings, Watches, WatchFaces, Health, Notifications),
            WatchHomeNavTab.availableTabs(config, healthEnabled = true),
        )
    }

    @Test
    fun orderedTabsKeepsUnavailableTabsInPlace() {
        val config = CoreConfig(navBarTabs = listOf("Settings", "Health", "Watches"))
        assertEquals(listOf(Settings, Health, Watches, WatchFaces, Notifications), WatchHomeNavTab.orderedTabs(config))
    }
}
