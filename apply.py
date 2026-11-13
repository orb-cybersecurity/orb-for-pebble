#!/usr/bin/env python3
"""Turn a pristine checkout of Core's Pebble app (mobileapp/) into Orb for Pebble.

Usage:
    python3 apply.py                     apply the overlay and edits to mobileapp/
    python3 apply.py --reset             first restore mobileapp/ to its pinned commit, then apply
    python3 apply.py --check             verify the pin and the recorded upstream hashes only
    python3 apply.py --extra-abi x86_64  also package native code for this ABI (emulator tests);
                                         combines with --reset

Every edit asserts how many times it matched, and every replaced file is checked against the
hash of the upstream file it was written for, so an upstream change that needs a human look
fails here instead of silently building something else.
"""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "mobileapp"
OVERLAY = ROOT / "overlay"
MARKER = APP / "orb" / ".applied"

APPLICATION_ID = "com.orbcybersecurity.orb"
APP_LABEL = "Orb"

# Upstream files the overlay replaces outright, with the sha256 of the upstream version each
# replacement was written against.
REPLACED = {
    "cactus/src/androidMain/kotlin/com/cactus/Cactus.kt":
        "edd773e1d0f3c9aa8e278d0939d66078a620fb5024fc815fc26f5725372be328",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/auth/GoogleAuthUtil.android.kt":
        "12e9d182c7c9b6b2ae6ff57d52f9fec64dc6abdc136a29e4676bcbb211597f4f",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/auth/OAuthProviderSignIn.android.kt":
        "45c01a6f2ef44b65cda0e97912d04fa1b097bb153d5813a4097d04c0042ba5d5",
    "util/src/androidMain/kotlin/AppUpdate.android.kt":
        "aee44639f643a51315264b1cb1d682bbd994711f3e94f68bcda519be60b856ec",
    "util/src/androidMain/kotlin/coredevices/analytics/Analytics.android.kt":
        "3fedd71bd66e151231851313df2970364e4c2726e065649ea8f007a3b9274ddc",
    "util/src/androidMain/kotlin/coredevices/util/transcription/PlatformSpeechRecognizer.android.kt":
        "4b95f649c8dd2a5e2e3c6e3a19f9c05836d64315d0a75f8aa096201ff5819d36",
    "util/src/commonMain/kotlin/theme/Theme.kt":
        "76f3cfc7ce8722c581eec20a7638b03a92bc666481a41c052c337b5ffe668ceb",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/Memfault.kt":
        "9dda6ccec279bb6501975833de97476fadbdd6f41d0ba93623fafe1ed6ff136b",
    "util/src/androidMain/res/mipmap-anydpi-v26/ic_launcher.xml":
        "9c3a7e0a6515c6e1a7ae834a9ae430311ebc3241f7b2e5e7f0460aa690709a7c",
    "util/src/androidMain/res/values/ic_launcher_background.xml":
        "2b3d92d6e19240c4fc0600e8264074f8f225b309f8bddbf9f320e22c43e07fee",
    "util/src/androidMain/res/drawable/ic_notification.xml":
        "ebbaa2c938c3ec08711ad4321616ec4815993de4d59bd86edf83e5ce8acf8af2",
    # Rewritten without Core's Index 01 ring (see remove_index_ring()); the replacements also
    # carry Orb's other changes to these files.
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/PebbleService.kt":
        "7dfc7d7aaa33da14a10990c688c6e08245f2bcccfa3f724965ed5a364b1b0597",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/PebbleBackgroundManager.kt":
        "3e99e6895ed9efd054313a1dffabbbdceb781f6aceb19b7a057b881868c35534",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportProcessor.kt":
        "2a4e001b8b85921d3228491775e0af10b27648a5c59854cf7f35da5901593ee4",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/OnboardingScreen.kt":
        "751898c0160d2604f7e598356bd61245f637a0f65c179b8147146d8af6d6951f",
    "composeApp/src/commonTest/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandlerTest.kt":
        "cd116f99cce317aa67d5e339cc2769e2c663899333fd7f70b3d4a091c4286e42",
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchHomeScreen.kt":
        "9f2bc23f1f080baa28864052c4d120777935887e6cde74734494114d4d8605e1",
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchesScreen.kt":
        "b577c182d0045ef0040137e4e48b382a9052a2a5a5ad20e234bd6e0d23d8a9ae",
    "pebble/src/commonTest/kotlin/coredevices/pebble/ui/WatchHomeNavTabTest.kt":
        "4e443ba4a8d95781ba58cec133208c521b0d63363fc3346c80373671a3574dae",
}

# Prebuilt binaries and files only they need, and Core's launcher artwork.
REMOVED = [
    "cactus-native",
    "cactus/src/commonMain/resources/ios",
    "models",
    "composeApp/src/androidMain/assets/models/needle-pebble-ft-cq4.zip",
    "androidApp/src/google-services-dummy.json",
    # Core's telemetry uploads: the analytics heartbeat and Memfault diagnostics (see apply()).
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/AnalyticsIngest.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/AnalyticsHeartbeatQueue.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/MemfaultChunkQueue.kt",
    "util/src/androidMain/ic_launcher-playstore.png",
    "composeApp/src/commonMain/composeResources/drawable/pebble-logo.png",
    *(f"util/src/androidMain/res/mipmap-{d}/ic_launcher_foreground.webp"
      for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")),
    # Core's Index 01 ring: its radio library is closed source and Orb has no plans to support
    # the ring. Its modules, and what only they used (see remove_index_ring()).
    "experimental",
    "libindex",
    "index-ai",
    "mcp",
    "resampler",
    "androidApp/src/androidTest",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/ringonboarding",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/plugins",
    "composeApp/src/commonMain/composeResources/drawable/index01_mic.png",
    "util/src/commonMain/composeResources/drawable/ring_wireframe.png",
    "util/src/commonMain/kotlin/coredevices/EnableExperimentalDevices.kt",
    "util/src/commonMain/kotlin/coredevices/pebble/ui/IndexTabBadge.kt",
    "util/src/commonMain/kotlin/coredevices/ui/SecondaryProfileWarningDialog.kt",
    "util/src/commonMain/kotlin/coredevices/util/SecondaryProfileWarning.kt",
    "util/src/commonTest/kotlin/coredevices/util/SecondaryProfileWarningTest.kt",
    "util/src/commonTest/kotlin/coredevices/util/transcription/TranscriptionExceptionErrorTypeTest.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/config/ConfigPageClosedListener.kt",
]

# Catalog accessors of dependencies and plugins that must not be referenced at all.
DROPPED_ACCESSORS = (
    r"libs\.(?:firebase\.bom|firebase\.crashlytics(?:\.ndk)?|gms\.auth|identity\.google"
    r"|play\.update(?:\.ktx)?|crashkios|mixpanel\.android"
    r"|plugins\.googleServices|plugins\.firebaseCrashlytics)\b"
)


# Settings Orb hides (by title): they need a Core account, Google services, the removed
# on-device speech engine, or Core's telemetry backends.
HIDDEN_SETTINGS = (
    "App Update Available",
    "View My Bug Reports",
    "Open Google Fit",
    "Manage Offline Models",
    "Cloud Recognition Provider",
    "Send app crashes",
    "Send watch analytics",
    "Send app analytics",
    "Sign In - Pebble Account",
    "Sign Out - Pebble Account",
)


class ApplyError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_version() -> tuple[str, int]:
    props = dict(
        line.split("=", 1)
        for line in (ROOT / "version.properties").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    name, code = props["versionName"], int(props["versionCode"])
    match = re.fullmatch(r"(\d+(?:\.\d+){0,3})-orb(\d)", name)
    if not match:
        raise ApplyError(f"versionName {name!r} is not <upstream tag>-orb<0-9>")
    parts = [int(p) for p in match.group(1).split(".")]
    upstream_code = sum(scale * part for scale, part in zip((10_000_000, 100_000, 1_000, 1), parts))
    expected = upstream_code * 10 + int(match.group(2))
    if code != expected:
        raise ApplyError(f"versionCode {code} does not match {name!r} (expected {expected})")
    return name, code


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(APP), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def check_pin(version_name: str) -> None:
    """The pinned upstream commit must be the tag the version is named after."""
    if not (APP / ".git").exists():
        return
    tag = version_name.split("-orb")[0]
    try:
        head, tagged = git("rev-parse", "HEAD"), git("rev-parse", f"{tag}^{{commit}}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    if head != tagged:
        raise ApplyError(f"mobileapp is at {head[:9]}, but version.properties names tag {tag} ({tagged[:9]})")


def check_replaced() -> None:
    stale = [
        path for path, digest in REPLACED.items()
        if not (APP / path).is_file() or sha256(APP / path) != digest
    ]
    if stale:
        raise ApplyError(
            "upstream changed files the overlay replaces; review each, update the overlay copy "
            "and its hash in REPLACED:\n  " + "\n  ".join(stale)
        )
    missing = [path for path in REPLACED if not (OVERLAY / path).is_file()]
    if missing:
        raise ApplyError("overlay is missing replacements for:\n  " + "\n  ".join(missing))


def edit(path: str, pattern: str, replacement: str, expect: int | tuple[int, ...] = 1) -> None:
    """Regex substitution in one file that must match exactly `expect` times.

    `expect` may list several acceptable counts, for text that F-Droid's build tooling has
    sometimes already removed by the time this runs.
    """
    allowed = (expect,) if isinstance(expect, int) else expect
    file = APP / path
    text, count = re.subn(pattern, replacement, file.read_text(), flags=re.MULTILINE)
    if count not in allowed:
        raise ApplyError(f"{path}: expected {allowed} match(es) of {pattern!r}, found {count}")
    file.write_text(text)


def delete_lines(paths: list[Path], pattern: str, at_least: int = 1) -> None:
    """Delete every whole line matching `pattern` across files; at least `at_least` in total."""
    regex = re.compile(pattern)
    total = 0
    for file in paths:
        lines = file.read_text().splitlines(keepends=True)
        kept = [line for line in lines if not regex.search(line)]
        if len(kept) != len(lines):
            total += len(lines) - len(kept)
            file.write_text("".join(kept))
    if total < at_least:
        raise ApplyError(f"expected at least {at_least} line(s) matching {pattern!r}, found {total}")


def gradle_files() -> list[Path]:
    return sorted(
        p for p in APP.rglob("*.gradle.kts")
        if "build" not in p.relative_to(APP).parts[:-1] and p.relative_to(APP).parts[0] != "orb"
    )


def remove_index_ring(settings_screen: str) -> None:
    """Remove Core's Index 01 ring.

    The ring's radio library is closed source, and Orb has no plans to support the ring. Its
    modules (experimental, libindex, index-ai, mcp, resampler) are in REMOVED; this
    unhooks everything that reached into them. Files changed too much to edit are replaced
    (REPLACED); the rest are edited here.
    """
    # Build wiring.
    edit("settings.gradle.kts", r'^include\(":(mcp|index-ai|resampler|libindex|experimental)"\)\n', "", expect=5)
    edit("composeApp/build.gradle.kts",
         r'^[ \t]*(implementation|api)\(project\(":(experimental|libindex|index-ai|mcp)"\)\)\n', "", expect=4)
    edit("composeApp/build.gradle.kts", r"^[ \t]*implementation\(libs\.coredevices\.haversine\)\n", "")
    edit("util/build.gradle.kts", r'^[ \t]*(implementation|api)\(project\(":(libindex|index-ai)"\)\)\n', "", expect=2)
    edit("pebble/build.gradle.kts", r'^[ \t]*implementation\(project\(":libindex"\)\)\n', "")
    edit("androidApp/build.gradle.kts",
         r'^[ \t]*androidTestImplementation\(project\(":(experimental|libindex|index-ai|mcp)"\)\)\n', "", expect=4)
    edit("gradle/libs.versions.toml", r"^coredevices-haversine = .*\n", "", expect=2)

    # util: the ring's config, routes and companion-device calls.
    core_config = "util/src/commonMain/kotlin/coredevices/util/CoreConfig.kt"
    edit(core_config, r'listOf\("WatchFaces", "Index", "Watches"\)', 'listOf("WatchFaces", "Watches")')
    edit("util/src/commonTest/kotlin/coredevices/util/CoreConfigTest.kt",
         r'"WatchFaces", "Index", "Watches",', '"WatchFaces", "Watches",', expect=2)
    edit(core_config, r"^[ \t]*val (enableIndex|indexPermissionsConfirmed): Boolean = false,\n", "", expect=2)
    edit(core_config,
         r"^[ \t]*/\*\* Stops the ring scan/sync loop.*\*/\n[ \t]*val disableRingBluetoothSync: Boolean = false,\n", "")
    edit("util/src/commonMain/kotlin/CommonRoutes.kt",
         r"^[ \t]*@Serializable\n[ \t]*data object RingOnboardingRoute : CoreRoute\n\n", "")
    edit("util/src/commonMain/kotlin/CommonRoutes.kt", r"^[ \t]*val recordingPath: String\? = null,\n", "")
    bug_button = "util/src/commonMain/kotlin/BugReportButton.kt"
    edit(bug_button, r"^[ \t]*recordingPath: String\? = null,\n", "")
    edit(bug_button, r"^[ \t]*recordingPath = recordingPath,\n", "")
    edit("util/src/commonMain/kotlin/coredevices/pebble/ui/TopBarParams.kt",
         r"^[ \t]*/\*\* Hide the chrome's TopAppBar.*\n(?:[ \t]*\*.*\n)*?[ \t]*val setHidden: \(Boolean\) -> Unit = \{\},\n", "")
    transcription_exception = "util/src/commonMain/kotlin/coredevices/util/transcription/TranscriptionException.kt"
    edit(transcription_exception, r"^import coredevices\.indexai\.data\.entity\.RecordingEntryErrorType\n\n", "")
    edit(transcription_exception,
         r"^[ \t]*/\*\* How this failure is persisted on the recording entry\. \*/\n[ \t]*abstract val errorType: RecordingEntryErrorType\n\n", "")
    # Each subclass then has an empty body.
    edit(transcription_exception,
         r" \{\n[ \t]*override val errorType = RecordingEntryErrorType\.[a-z_]+\n[ \t]*\}\n", "\n", expect=7)
    companion = "util/src/commonMain/kotlin/coredevices/util/CompanionDevice.kt"
    edit(companion, r"^import coredevices\.libindex\.device\.IndexIdentifier\n", "")
    edit(companion, r"^[ \t]*(suspend )?fun [a-zA-Z]+\(identifier: IndexIdentifier[^\n]*\n", "", expect=4)
    android_companion = "util/src/androidMain/kotlin/coredevices/util/AndroidCompanionDevice.kt"
    edit(android_companion, r"^import coredevices\.libindex\.device\.IndexIdentifier\n", "")
    edit(android_companion, r"^import android\.companion\.BluetoothDeviceFilter\n", "")
    edit(android_companion, r"^import android\.annotation\.SuppressLint\n", "")
    edit(android_companion,
         r"^    override suspend fun registerDevice\(\n[ \t]*identifier: IndexIdentifier,\n(?:.*\n)*?    \}\n\n", "")
    edit(android_companion,
         r"^    override fun hasApprovedDevice\(identifier: IndexIdentifier\): Boolean \{\n(?:.*\n)*?    \}\n\n", "")
    edit(android_companion,
         r"^    private fun bondRemovableAssociation\(identifier: IndexIdentifier\)(?:.*\n)*?"
         r"            false\n        \}\n    \}\n\n", "")
    edit(android_companion, r",\n[ \t]*useClassicAssociation: Boolean = false\n", "\n")
    edit(android_companion,
         r"^([ \t]*)val filter = if \(useClassicAssociation\) \{\n(?:.*\n)*?[ \t]*\} else \{\n"
         r"([ \t]*)BluetoothLeDeviceFilter\.Builder\(\)\n"
         r"[ \t]*\.setScanFilter\(ScanFilter\.Builder\(\)\.setDeviceAddress\(macAddress\)\.build\(\)\)\n"
         r"[ \t]*\.build\(\)\n[ \t]*\}\n",
         r"\1val filter = BluetoothLeDeviceFilter.Builder()" "\n"
         r"\1    .setScanFilter(ScanFilter.Builder().setDeviceAddress(macAddress).build())" "\n"
         r"\1    .build()" "\n")

    # composeApp: startup, DI, navigation and the bug report.
    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module, r"^import coredevices\.ring\.RingDelegate\n", "")
    edit(android_module, r"^import coredevices\.util\.CoreConfigFlow\n", "")
    edit(android_module, r"^import kotlinx\.coroutines\.flow\.(combine|map)\n", "", expect=2)
    edit(android_module,
         r"^    single \{\n        val pebbleDelegate = get<PebbleAndroidDelegate>\(\)\n(?:.*\n)*?        \)\n    \}\n",
         "    single { RequiredPermissions(get<PebbleAndroidDelegate>().requiredPermissions) }\n")
    main_application = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainApplication.kt"
    edit(main_application, r"^import coredevices\.(ExperimentalDevices|experimentalModule)\n", "", expect=2)
    edit(main_application, r"^[ \t]*private val experimentalDevices: ExperimentalDevices by inject\(\)\n", "")
    edit(main_application, r"^[ \t]*experimentalModule,\n", "")
    edit(main_application, r"^[ \t]*experimentalDevices\.appInit\(\)\n", "")
    main_activity = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainActivity.kt"
    edit(main_activity, r"^import coredevices\.ExperimentalDevices\n", "")
    edit(main_activity, r"^[ \t]*private val experimentalDevices: ExperimentalDevices by inject\(\)\n", "")
    edit(main_activity, r"^[ \t]*experimentalDevices\.handleDeepLink\(it\)\n", "")
    app_delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    edit(app_delegate, r"^import coredevices\.ExperimentalDevices\n", "")
    edit(app_delegate, r"^[ \t]*private val experimentalDevices: ExperimentalDevices,\n", "")
    edit(app_delegate, r"^import kotlinx\.coroutines\.withContext\n", "")
    edit(app_delegate,
         r"^([ \t]*)weatherFetcher\.init\(\)\n[ \t]*withContext\(Dispatchers\.Main\) \{\n"
         r"[ \t]*experimentalDevices\.init\(\)\n[ \t]*\}\n",
         r"\1weatherFetcher.init()" "\n")
    edit(app_delegate,
         r"^[ \t]*// Use the background runtime window even if the sync intervals below haven't elapsed\n"
         r"[ \t]*experimentalDevices\.onBackgroundSync\(\)\n", "")
    logging = "composeApp/src/commonMain/kotlin/coredevices/coreapp/util/logging.kt"
    edit(logging, r"^import coredevices\.ExperimentalDevices\n", "")
    edit(logging,
         r"^suspend fun generateDeviceSummary\(experimentalDevices: ExperimentalDevices\): String \{\n(?:.*\n)*?\}\n\n",
         "")
    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module,
         r"^import coredevices\.(EnableExperimentalDevices|coreapp\.plugins\.AppstorePluginStore"
         r"|pebble\.config\.ConfigPageClosedListener|ring\.agent\.integrations\.providers\.DefaultDestinationPrompter"
         r"|ring\.agent\.pebble_plugin\.PluginStore|util\.SecondaryProfileWarning)\n", "", expect=6)
    edit(util_module, r"^[ \t]*singleOf\(::EnableExperimentalDevices\)\n", "")
    edit(util_module, r"^[ \t]*single \{ SecondaryProfileWarning\(.*\n", "")
    edit(util_module, r"^[ \t]*singleOf\(::AppstorePluginStore\) bind PluginStore::class\n", "")
    edit(util_module, r"^[ \t]*single \{ ConfigPageClosedListener\(.*\n", "")
    # Core's on-device model provider lived in the ring module. Orb has no Cactus engine, so
    # there are never models to find; screens that ask get an empty answer.
    edit(util_module,
         r"^([ \t]*)getOrNull<CactusModelPathProvider>\(\) \?: object : CactusModelPathProvider \{\n"
         r"((?:[ \t]*override .*\n){8})[ \t]*\},\n",
         r"\1get(),\n")
    edit(util_module,
         r"^    single \{\n        CactusTranscriptionService\(\n",
         "    single<CactusModelPathProvider> {\n"
         "        object : CactusModelPathProvider {\n"
         '            override suspend fun getSTTModelPath(modelName: String, version: String): String = throw IllegalStateException("No on-device speech models in this build")\n'
         '            override suspend fun getLMModelPath(): String = throw IllegalStateException("No on-device speech models in this build")\n'
         "            override fun isModelDownloaded(modelName: String): Boolean = false\n"
         "            override fun getDownloadedModels(): List<String> = emptyList()\n"
         "            override fun getIncompatibleModels(): List<String> = emptyList()\n"
         "            override fun deleteModel(modelName: String) {}\n"
         "            override fun getModelSizeBytes(modelName: String): Long = 0L\n"
         "            override fun initTelemetry() {}\n"
         "        }\n"
         "    }\n"
         "    single {\n"
         "        CactusTranscriptionService(\n")
    edit("composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/App.kt",
         r"^import coredevices\.ring\.ui\.screens\.settings\.DefaultDestinationPromptHost\n", "")
    edit("composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/App.kt",
         r"^[ \t]*DefaultDestinationPromptHost\(\)\n", "")
    nav_host = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt"
    edit(nav_host,
         r"^import coredevices\.(ring\.ui\.navigation\.RingRoute|coreapp\.ui\.screens\.ringonboarding\.RingOnboardingScreen"
         r"|ring\.ui\.navigation\.addRingRoutes|ring\.ui\.screens\.IndexScreen|ring\.ui\.theme\.IndexThemeHost)\n",
         "", expect=5)
    edit(nav_host,
         r"^    NavHost\(navController, startDestination = startDestination\) \{\n"
         r"        addRingRoutes\(coreNav\)\n"
         r"        addPebbleRoutes\(\n(?:.*\n)*?        \)\n",
         "    NavHost(navController, startDestination = startDestination) {\n"
         "        addPebbleRoutes(coreNav)\n")
    edit(nav_host,
         r"^[ \t]*composable<CommonRoutes\.RingOnboardingRoute> \{\n[ \t]*IndexThemeHost \{\n"
         r"[ \t]*RingOnboardingScreen\(\n[ \t]*coreNav = coreNav,\n[ \t]*\)\n[ \t]*\}\n[ \t]*\}\n", "")
    edit(nav_host, r"^[ \t]*recordingPath = route\.recordingPath,\n", "")
    deep_links = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandler.kt"
    edit(deep_links, r"^import coredevices\.ring\.ui\.navigation\.RingRoutes\n", "")
    edit(deep_links, r"^[ \t]*RingRoutes\.[A-Z_]+_DEEP_LINK_PATH -> .*\n", "", expect=4)
    edit(deep_links, r"RingRoutes\.OBJECT_DEEP_LINK_HOST", '"deep-link"')
    edit(deep_links, r"^[ \t]*private const val ID_PARAM = RingRoutes\.OBJECT_DEEP_LINK_ID_PARAM\n", "")
    edit(deep_links, r"^[ \t]*val id = uri\.getQueryParameter\(ID_PARAM\).*\n", "")
    edit("composeApp/src/androidMain/kotlin/coredevices/coreapp/ui/screens/BugReport.android.kt",
         r"\nactual fun getExperimentalDebugInfoDirectory\(\): String \{\n(?:.*\n)*?\}\n", "")
    edit("composeApp/src/androidMain/kotlin/coredevices/coreapp/ui/screens/BugReport.android.kt",
         r"^import java\.io\.File\n", "")
    bug_report = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt"
    edit(bug_report, r"^expect fun getExperimentalDebugInfoDirectory\(\): String\n", "")
    edit(bug_report, r"^import androidx\.compose\.material3\.FilterChip\n", "")
    edit(bug_report, r"^import coredevices\.util\.CoreConfigFlow\n", "")
    edit(bug_report, r"^[ \t]*recordingPath: String\?,\n", "")
    edit(bug_report,
         r"^([ \t]*)// Default to an Index bug report when there are no watches stored in libpebble\.\n",
         r"\1// Watch logs and screenshots only apply when a watch is stored.\n")
    edit(bug_report, r"^[ \t]*val coreConfigFlow: CoreConfigFlow = koinInject\(\)\n[ \t]*val coreConfig by coreConfigFlow\.flow\.collectAsState\(\)\n", "")
    edit(bug_report, r"^[ \t]*val \((sendRecording, setSendRecording|sendRecentRecordings, setSendRecentRecordings)\) = remember \{ .*\n", "", expect=2)
    edit(bug_report, r"^[ \t]*(sendRecording = sendRecording|sendRecentRecordings = .*|expOutputPath = recordingPath|includeExperimentalDebugInfo = !isWatch),\n", "", expect=4)
    edit(bug_report,
         r"^[ \t]*if \(coreConfig\.enableIndex\) \{\n[ \t]*Text\(\"This is a:\".*\n(?:.*\n)*?"
         r"[ \t]*label = \{ Text\(\"Watch bug\"\) \}\n[ \t]*\)\n[ \t]*\}\n[ \t]*\}\n", "")
    edit(bug_report,
         r"^[ \t]*if \(recordingPath != null\) \{\n(?:.*\n)*?[ \t]*\"Include recording\",\n(?:.*\n)*?[ \t]*\}\n[ \t]*\}\n", "")
    edit(bug_report,
         r"^[ \t]*if \(coreConfig\.enableIndex && !isWatch\) \{\n(?:.*\n)*?[ \t]*\"Include recent recordings\",\n(?:.*\n)*?[ \t]*\}\n[ \t]*\}\n", "")

    # pebble: the Index tab and routes, deep links, the locker's ring default, previews.
    routes = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/PebbleRoutes.kt"
    edit(routes,
         r"^[ \t]*indexScreen: @Composable \(TopBarParams, NavBarNav, CoreNav\) -> Unit,\n"
         r"[ \t]*/\*\* A CoreNav scoped to the inner controller so RingRoute navigations\n"
         r"[ \t]*\*  stay inside the bottom-nav chrome\. Forwarded to \[indexScreen\]\. \*/\n"
         r"[ \t]*scopedCoreNav: CoreNav,\n", "")
    edit(routes,
         r"^[ \t]*composableWithAnimations<PebbleNavBarRoutes\.IndexRoute>\(viewModel\) \{\n"
         r"[ \t]*indexScreen\(topBarParams, nav, scopedCoreNav\)\n[ \t]*\}\n", "")
    edit(routes, r"^[ \t]*@Serializable\n[ \t]*data object IndexRoute : NavBarRoute\n\n", "")
    edit(routes,
         r"^    coreNav: CoreNav,\n    indexScreen: @Composable \(TopBarParams, NavBarNav, CoreNav\) -> Unit,\n"
         r"(?:[ \t]*(?:/\*\*|\*).*\n|[ \t]*(?:addExperimentalRoutes|isInnerScopedRoute): .*\n)+\) \{\n",
         "    coreNav: CoreNav,\n) {\n")
    edit(routes,
         r"WatchHomeScreen\(coreNav, indexScreen, addExperimentalRoutes, isInnerScopedRoute\)",
         "WatchHomeScreen(coreNav)")
    deep_link = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt"
    edit(deep_link, r"^import coredevices\.libindex\.device\.(IndexPlatformBluetoothAssociations|REQUEST_URI_HOST)\n",
         "", expect=2)
    edit(deep_link,
         r"^    /\*\*\n     \* Set when the user taps the \"Index 01 background access limited\" notification\.(?:.*\n)*?"
         r"    val requestIndexCompanion: StateFlow<Boolean>\n", "")
    edit(deep_link, r"^[ \t]*fun consumeRequestIndexCompanion\(\)\n\n?", "")
    edit(deep_link,
         r"^[ \t]*private val _requestIndexCompanion = MutableStateFlow\(false\)\n"
         r"[ \t]*override val requestIndexCompanion: StateFlow<Boolean> = .*\n", "")
    edit(deep_link,
         r"^    override fun consumeRequestIndexCompanion\(\) \{\n        _requestIndexCompanion\.value = false\n    \}\n\n", "")
    edit(deep_link, r"^[ \t]*NAVBAR_URL -> handleNavbar\(uri\.path\)\n", "")
    edit(deep_link, r"^[ \t]*REGISTER_INDEX_COMPANION_HOST -> handleRegisterIndexCompanion\(\)\n", "")
    edit(deep_link,
         r"^    // Show the Watches tab and ask it to \(re-\)register the paired ring as a companion device\.\n"
         r"    private fun handleRegisterIndexCompanion\(\): Boolean \{\n(?:.*\n)*?    \}\n\n", "")
    edit(deep_link, r"^    private fun handleNavbar\(path: String\?\): Boolean \{\n(?:.*\n)*?    \}\n\n", "")
    edit(deep_link, r'^[ \t]*private const val NAVBAR_URL: String = "navbar"\n', "")
    edit(deep_link, r"^[ \t]*private val REGISTER_INDEX_COMPANION_HOST = .*\n", "")
    edit(deep_link, r"^[ \t]*val NOTIFICATION_INTENT_URI_REGISTER_INDEX_COMPANION = .*\n", "")
    locker = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt"
    edit(locker, r"^import coredevices\.libindex\.(LibIndex|device\.KnownIndexDevice)\n", "", expect=2)
    # Core opened the locker on plugins for people with a ring and no watch.
    edit(locker,
         r"^[ \t]*val rings by koinInject<LibIndex>\(\)\.rings\.collectAsState\(\)\n"
         r"[ \t]*val watches by libPebble\.watches\.collectAsState\(\)\n"
         r"[ \t]*val defaultType = if \(\n(?:.*\n)*?[ \t]*\) AppType\.Plugin else AppType\.Watchface\n"
         r"[ \t]*LaunchedEffect\(defaultType\) \{\n(?:.*\n)*?        \}\n", "")
    edit(locker, r"^([ \t]*)var defaultType = AppType\.Watchface\n", r"\1val defaultType = AppType.Watchface\n")
    intro = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/PermissionsIntro.kt"
    edit(intro, r"^import coredevices\.util\.CoreConfigHolder\n", "")
    edit(intro, r"^import org\.koin\.compose\.koinInject\n", "")
    edit(intro,
         r"^[ \t]*val indexEnabled = .*\n[ \t]*val askers = when \{\n(?:.*\n)*?[ \t]*else -> (\"Watchfaces, watchapps and plugins\")\n[ \t]*\}\n",
         r"    val askers = \1" "\n")
    edit("pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt",
         r"^import coredevices\.pebble\.config\.ConfigPageClosedListener\n", "")
    edit("pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt",
         r"^[ \t]*val closedListener: ConfigPageClosedListener = koinInject\(\)\n", "")
    edit("pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt",
         r"^[ \t]*runCatching \{ Uuid\.parse\(uuid\) \}\.getOrNull\(\)\?\.let\(closedListener::onConfigPageClosed\)\n", "")
    edit("pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt",
         r"^([ \t]*)// Opened from outside the locker \(a plugin picked as an Index destination\), nothing is cached\.\n",
         r"\1// Opened from outside the locker, nothing is cached.\n")
    watches_android = "pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchesScreen.android.kt"
    edit(watches_android,
         r"^import (androidx\.compose\.material\.icons\.Icons|androidx\.compose\.material\.icons\.outlined\.Delete"
         r"|androidx\.compose\.material3\.(DropdownMenuItem|Icon|Text)|androidx\.compose\.runtime\.(Composable|remember)"
         r"|androidx\.compose\.ui\.platform\.LocalContext|coredevices\.libindex\.device\.KnownIndexDevice"
         r"|coredevices\.util\.CompanionDevice|org\.koin\.compose\.koinInject)\n", "", expect=11)
    edit(watches_android, r"\n@Composable\nactual fun RemovePairingMenuItem\(\n(?:.*\n)*?\}\n", "")
    preview = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt"
    edit(preview, r"^import coredevices\.libindex\..*\n", "", expect=3)
    edit(preview, r"^import coredevices\.util\.SecondaryProfileWarning\n", "")
    edit(preview, r"^[ \t]*single \{ SecondaryProfileWarning\(.*\n", "")
    edit(preview, r"^    single<LibIndex> \{\n        object : LibIndex \{\n(?:.*\n)*?        \}\n    \}\n", "")
    edit(preview, r"^[ \t]*override val requestIndexCompanion: StateFlow<Boolean> = .*\n", "")
    edit(preview, r"^[ \t]*override fun consumeRequestIndexCompanion\(\) \{\}\n", "")
    edit(preview,
         r"^        override suspend fun registerDevice\(\n            identifier: IndexIdentifier,\n(?:.*\n)*?        \}\n\n", "")
    edit(preview,
         r"^        override fun (hasApprovedDevice|canRemoveBond|removeBond)\(identifier: IndexIdentifier\): Boolean \{\n"
         r"[ \t]*return (true|false)\n        \}\n\n", "", expect=3)
    edit(settings_screen, r"^import coredevices\.EnableExperimentalDevices\n", "")
    edit(settings_screen,
         r"^[ \t]*val enableExperimentalDevices: EnableExperimentalDevices = koinInject\(\)\n"
         r"[ \t]*val experimentalDevices by enableExperimentalDevices\.enabled\.collectAsState\(\)\n", "")
    edit(settings_screen, r"^[ \t]*experimentalDevices,\n", "")
    edit(settings_screen, r'keywords = "tabs navigation health notifications devices apps index"',
         'keywords = "tabs navigation health notifications devices apps"')
    edit(settings_screen,
         r'^[ \t]*basicSettingsToggleItem\(\n[ \t]*title = "Enable Index Feed",\n(?:.*\n)*?[ \t]*\),\n(?=[ \t]*basicSettingsToggleItem\(\n[ \t]*title = "Notify when watch fully charged")',
         "")
    edit(settings_screen,
         r'^[ \t]*navBarNav\?\.let \{basicSettingsActionItem\(\n[ \t]*title = "Show Ring Onboarding",\n(?:.*\n)*?[ \t]*\) \},\n', "")


def confirm_external_input() -> None:
    """Links and files from outside the app take effect only after the user confirms them.

    The boot-config confirmation dialog itself is in Orb's WatchHomeScreen.kt overlay.
    """
    handler = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt"
    edit(handler,
         r"^(    val pendingFirmwareSideload: StateFlow<PendingFirmwareSideload\?>\n)",
         r"\1\n"
         "    /** A boot-config link waiting for the user to approve its host. */\n"
         "    val pendingBootConfig: StateFlow<PendingBootConfig?>\n"
         "    fun confirmPendingBootConfig()\n"
         "    fun dismissPendingBootConfig()\n")
    edit(handler,
         r"^(data class PendingFirmwareSideload\(val file: Path, val fileName: String\)\n)",
         r"\1" "data class PendingBootConfig(val path: String, val token: String, val host: String)\n")
    edit(handler,
         r"^(    private var reservedSideloadCount = 0\n)",
         r"\1"
         "    private val _pendingBootConfig = MutableStateFlow<PendingBootConfig?>(null)\n"
         "    override val pendingBootConfig: StateFlow<PendingBootConfig?> = _pendingBootConfig.asStateFlow()\n"
         "\n"
         "    override fun confirmPendingBootConfig() {\n"
         "        val pending = _pendingBootConfig.value ?: return\n"
         "        _pendingBootConfig.value = null\n"
         "        applyBootConfig(pending.token, pending.path)\n"
         "    }\n"
         "\n"
         "    override fun dismissPendingBootConfig() {\n"
         "        _pendingBootConfig.value = null\n"
         "    }\n")
    # handleBootConfig: validate, then park the link for confirmation; the body that used to
    # run at once becomes applyBootConfig, called only from confirmPendingBootConfig.
    edit(handler,
         r"^(    private fun handleBootConfig\(path: String\?\): Boolean \{\n"
         r"        logger\.d \{ \"handleBootConfig\(\)\" \}\n"
         r"        val token = parseTokenFrom\(path\)\n"
         r"        if \(path == null \|\| token == null\) \{\n"
         r"            logger\.w\(\"couldn't find token\"\)\n"
         r"            return false\n"
         r"        \}\n)"
         r"(        GlobalScope\.launch \{\n"
         r"            pebbleAccount\.setToken\(token = token, bootUrl = path\)\n"
         r"(?:            .*\n)*?"
         r"        \}\n)"
         r"        return true\n",
         r"\1"
         "        val host = bootConfigHost(path)\n"
         "        if (host == null) {\n"
         "            logger.w(\"boot config link is not an https URL with a host\")\n"
         "            _snackBarMessages.tryEmit(\"Ignored a sign-in link that doesn't use https\")\n"
         "            return false\n"
         "        }\n"
         "        _pendingBootConfig.value = PendingBootConfig(path = path, token = token, host = host)\n"
         "        navigateToTab(PebbleNavBarRoutes.WatchesRoute)\n"
         "        return true\n"
         "    }\n"
         "\n"
         "    private fun applyBootConfig(token: String, path: String) {\n"
         r"\2")
    edit(handler,
         r"^(        internal fun parseTokenFrom\(path: String\?\): String\? \{\n)",
         "        /** Host (with any explicit port) of a boot-config link's URL; null unless it is https. */\n"
         "        internal fun bootConfigHost(path: String): String? {\n"
         "            val url = com.eygraber.uri.Uri.parseOrNull(path.removePrefix(\"/\")) ?: return null\n"
         "            if (!url.scheme.equals(\"https\", ignoreCase = true)) return null\n"
         "            val host = url.host?.takeIf { it.isNotBlank() } ?: return null\n"
         "            return if (url.port > 0) \"$host:${url.port}\" else host\n"
         "        }\n"
         "\n"
         r"\1")

    # A watchapp file sent by another app: confirm, naming it, before anything is installed.
    locker = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt"
    edit(locker,
         r"^(        val pendingAppSideload by deepLinks\.pendingAppSideload\.collectAsState\(\)\n)",
         "        var externalSideload by remember { mutableStateOf<Pair<Path, String?>?>(null) }\n"
         "        externalSideload?.let { (path, name) ->\n"
         "            fun discard() {\n"
         "                externalSideload = null\n"
         "                SystemFileSystem.delete(path, mustExist = false)\n"
         "            }\n"
         "            androidx.compose.material3.AlertDialog(\n"
         "                onDismissRequest = ::discard,\n"
         "                title = { Text(if (name != null) \"Install watchapp?\" else \"Can't install this file\") },\n"
         "                text = {\n"
         "                    Text(\n"
         "                        if (name != null) {\n"
         "                            \"Another app sent \\\"$name\\\". Install it on your watch? Only \" +\n"
         "                                \"install watchapps from sources you trust.\"\n"
         "                        } else {\n"
         "                            \"Another app sent a file that isn't a readable watchapp.\"\n"
         "                        }\n"
         "                    )\n"
         "                },\n"
         "                confirmButton = {\n"
         "                    if (name != null) {\n"
         "                        androidx.compose.material3.TextButton(onClick = {\n"
         "                            externalSideload = null\n"
         "                            sideload(path)\n"
         "                        }) { Text(\"Install\") }\n"
         "                    } else {\n"
         "                        androidx.compose.material3.TextButton(onClick = ::discard) { Text(\"OK\") }\n"
         "                    }\n"
         "                },\n"
         "                dismissButton = {\n"
         "                    if (name != null) {\n"
         "                        androidx.compose.material3.TextButton(onClick = ::discard) { Text(\"Cancel\") }\n"
         "                    }\n"
         "                },\n"
         "            )\n"
         "        }\n"
         r"\1")
    edit(locker,
         r"^(            pendingAppSideload\?\.let \{\n"
         r"                deepLinks\.consumePendingAppSideload\(\)\n)"
         r"                sideload\(it\)\n",
         r"\1"
         "                // In the screen's scope: consuming the sideload restarts this effect.\n"
         "                scope.launch {\n"
         "                    val name = withContext(Dispatchers.IO) {\n"
         "                        try {\n"
         "                            PbwApp(it).info.let { info -> info.longName.ifBlank { info.shortName } }\n"
         "                                .ifBlank { null }\n"
         "                        } catch (e: Exception) {\n"
         "                            null\n"
         "                        }\n"
         "                    }\n"
         "                    externalSideload = it to name\n"
         "                }\n")

    # The preview stand-in implements the handler interface too.
    edit("pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt",
         r"^(        override val pendingAppSideload: StateFlow<Path\?> = MutableStateFlow\(null\)\n)",
         r"\1"
         "        override val pendingBootConfig: StateFlow<coredevices.pebble.PendingBootConfig?> = MutableStateFlow(null)\n"
         "        override fun confirmPendingBootConfig() {}\n"
         "        override fun dismissPendingBootConfig() {}\n")


def apply(extra_abis: list[str]) -> None:
    version_name, version_code = read_version()
    check_pin(version_name)
    check_replaced()
    if MARKER.exists():
        raise ApplyError("mobileapp/ already has Orb applied; run with --reset")

    for path in REMOVED:
        target = APP / path
        # is_symlink covers links whose target was removed earlier in this loop.
        if not (target.exists() or target.is_symlink()):
            raise ApplyError(f"{path}: expected to remove it, but it is not there")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()

    shutil.copytree(OVERLAY, APP, dirs_exist_ok=True)

    # Build wiring.
    edit("settings.gradle.kts", r'^include\(":cactus-native"\)\n', "")
    with (APP / "settings.gradle.kts").open("a") as settings:
        settings.write('\napply(from = "orb/orb.settings.gradle.kts")\n')
    # Nothing in the build comes from JitPack or the local Maven cache. Leaving them in would
    # let a dependency change, or whatever is in the builder's ~/.m2, slip into the APK.
    edit("settings.gradle.kts", r'^[ \t]*maven\b.*"https://jitpack\.io".*\n', "", expect=2)
    edit(
        "settings.gradle.kts",
        r'^[ \t]*if \(properties\.getProperty\("USE_MAVEN_LOCAL"\) == "true"\) \{\n[ \t]*mavenLocal\(\)\n[ \t]*\}\n',
        "",
    )
    edit("settings.gradle.kts", r"^[ \t]*mavenLocal\(\)\n", "")
    delete_lines(gradle_files(), DROPPED_ACCESSORS, at_least=10)
    edit("cactus/build.gradle.kts", r'^\s*api\(project\(":cactus-native"\)\)\n', "")
    edit(
        "libpebble3/build.gradle.kts",
        r"^publishing \{\n(?:(?!\}\n).*\n)*\}\n\n",
        "",
    )

    # The build must not depend on which JDKs the machine can provision: drop the toolchain
    # pins and state the bytecode target wherever the pin was the only thing setting it.
    edit(
        "blobdbgen/build.gradle.kts",
        r"^kotlin \{\n\s*jvmToolchain\(.*\)\n\}\n",
        "kotlin {\n"
        "    compilerOptions {\n"
        "        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)\n"
        "    }\n"
        "}\n\n"
        "java {\n"
        "    sourceCompatibility = JavaVersion.VERSION_17\n"
        "    targetCompatibility = JavaVersion.VERSION_17\n"
        "}\n",
    )
    edit(
        "blobannotations/build.gradle.kts",
        r"^    jvm\(\)\n",
        "    jvm {\n"
        "        compilerOptions {\n"
        "            jvmTarget.set(JvmTarget.JVM_17)\n"
        "        }\n"
        "    }\n",
    )
    delete_lines(gradle_files(), r"^\s*jvmToolchain\(", at_least=2)

    # App identity and version.
    edit(
        "androidApp/build.gradle.kts",
        r"\n[ \t]*configure<com\.google\.firebase\.crashlytics\.buildtools\.gradle\.CrashlyticsExtension> \{"
        r"\n[ \t]*mappingFileUploadEnabled = false\n[ \t]*\}",
        "",
        expect=2,
    )
    edit(
        "androidApp/build.gradle.kts",
        r'applicationId = "coredevices\.coreapp"',
        f'applicationId = "{APPLICATION_ID}"',
    )
    edit(
        "androidApp/build.gradle.kts",
        r"it\.versionCode\.set\(gitVersionCode\)",
        f"it.versionCode.set({version_code})",
    )
    edit(
        "androidApp/build.gradle.kts",
        r"it\.versionName\.set\(gitVersionName\)",
        f'it.versionName.set("{version_name}")',
    )
    edit(
        "androidApp/src/main/AndroidManifest.xml",
        r'\n[ \t]*<meta-data\n[ \t]*android:name="firebase_crashlytics_collection_enabled"\n[ \t]*android:value="true" />',
        "",
    )
    # Permissions that Core's libraries declare but nothing in Orb uses. Each was checked against
    # the release dex: no watch feature calls an API that needs it. WAKE_LOCK stays because
    # WorkManager takes wake locks itself. (The ring module declared more; it is removed whole.)
    unused_permissions = (
        "android.permission.BLUETOOTH_ADVERTISE",
        "android.permission.REQUEST_OBSERVE_COMPANION_DEVICE_PRESENCE",
        "android.permission.RUN_USER_INITIATED_JOBS",
        "android.permission.USE_BIOMETRIC",
        "android.permission.USE_FINGERPRINT",
    )
    edit(
        "androidApp/src/main/AndroidManifest.xml",
        r'^    <!-- Mixpanel -->\n    <uses-permission android:name="android\.permission\.ACCESS_NETWORK_STATE" />\n',
        '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n'
        + "".join(
            f'    <uses-permission android:name="{name}" tools:node="remove" />\n'
            for name in unused_permissions
        ),
    )
    # The system speech recognizer checks its caller's microphone permission even when the caller
    # supplies the audio, so Orb's dictation needs RECORD_AUDIO. Core declared it only in the
    # ring module's manifest, which Orb removes.
    edit(
        "util/src/androidMain/AndroidManifest.xml",
        r"^    <uses-permission android:name=\"android\.permission\.RUN_USER_INITIATED_JOBS\" />\n",
        '    <uses-permission android:name="android.permission.RUN_USER_INITIATED_JOBS" />\n'
        "    <!-- Orb: dictation hands the watch's audio to the system speech recognizer, which still\n"
        "         checks the caller's microphone permission. -->\n"
        '    <uses-permission android:name="android.permission.RECORD_AUDIO" />\n',
    )
    edit(
        "androidApp/src/main/res/values/strings.xml",
        r'<string name="app_name">Pebble</string>',
        f'<string name="app_name">{APP_LABEL}</string>',
    )
    # A checkout without a keystore packages the release unsigned, for stores that sign.
    # F-Droid's tooling deletes the signing lines itself before this script runs.
    edit(
        "androidApp/build.gradle.kts",
        r'signingConfig = signingConfigs\.getByName\("release"\)',
        'signingConfig = signingConfigs.getByName("release").takeIf { it.storeFile?.exists() == true }',
        expect=(0, 1),
    )
    # Ship prebuilt native libraries as their AARs have them. Stripping uses whatever NDK the
    # machine has (F-Droid's build server has none), which would make the APK differ by machine
    # and rule out a reproducible, developer-signed release.
    edit(
        "androidApp/build.gradle.kts",
        r"^    packaging \{\n",
        "    packaging {\n"
        "        jniLibs {\n"
        '            keepDebugSymbols += "**/*.so"\n'
        "        }\n",
    )
    # The Gradle plugin otherwise embeds a dependency list encrypted to a Google key.
    edit(
        "androidApp/build.gradle.kts",
        r"^android \{\n",
        "android {\n"
        "    dependenciesInfo {\n"
        "        includeInApk = false\n"
        "        includeInBundle = false\n"
        "    }\n",
    )
    edit(
        "androidApp/build.gradle.kts",
        r'"proguard-rules\.pro"\)',
        '"proguard-rules.pro", "../orb/orb-proguard-rules.pro")',
    )

    # Core's telemetry: the watch's analytics heartbeats and Memfault diagnostic chunks, queued
    # in the database and uploaded to Core and to Memfault. Orb builds have no endpoint or key
    # for either, so the code could never send anything; it is removed rather than left inert.
    # The upload classes are in REMOVED and Memfault.kt is replaced by its serial helper. The
    # watch still hands the data over through libpebble3's WebServices; Orb drops it there.
    # The heartbeat table stays in Core's database so its schema needs no migration.
    services = "pebble/src/commonMain/kotlin/coredevices/pebble/services"
    edit(watch_module_path := "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt",
         r"^import coredevices\.pebble\.services\.(Memfault|AnalyticsHeartbeatQueue|AnalyticsIngest|MemfaultChunkQueue)\n",
         "", expect=4)
    edit(watch_module_path,
         r"^[ \t]*singleOf\(::(Memfault|MemfaultChunkQueue|AnalyticsIngest|AnalyticsHeartbeatQueue)\)\n",
         "", expect=4)
    firmware_check = "pebble/src/commonMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateCheck.kt"
    edit(firmware_check, r"^import coredevices\.pebble\.services\.Memfault\n", "")
    edit(firmware_check, r"^[ \t]*private val memfault: Memfault,\n", "")
    delegate = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleAppDelegate.kt"
    edit(delegate, r"^import coredevices\.pebble\.services\.(AnalyticsHeartbeatQueue|MemfaultChunkQueue)\n",
         "", expect=2)
    edit(delegate, r"^[ \t]*private val (memfaultChunkQueue: MemfaultChunkQueue|analyticsHeartbeatQueue: AnalyticsHeartbeatQueue),\n",
         "", expect=2)
    edit(delegate, r"^[ \t]*(memfaultChunkQueue|analyticsHeartbeatQueue)\.startProcessing\(GlobalScope\)\n",
         "", expect=2)
    edit(delegate,
         r"^[ \t]*scope\.launch \{\n[ \t]*(memfaultChunkQueue|analyticsHeartbeatQueue)\.uploadPendingFromDb\(\)\n[ \t]*\},\n",
         "", expect=2)
    web_services = f"{services}/PebbleWebServices.kt"
    edit(web_services, r"^import coredevices\.pebble\.services\.Memfault\.Companion\.serialForMemfault\n", "")
    edit(web_services, r"^[ \t]*private val (memfaultChunkQueue: MemfaultChunkQueue|analyticsHeartbeatQueue: AnalyticsHeartbeatQueue),\n",
         "", expect=2)
    edit(web_services,
         r"(override fun uploadMemfaultChunk\(chunk: ByteArray, watchInfo: WatchInfo\) \{\n)"
         r"[ \t]*memfaultChunkQueue\.enqueue\(watchInfo\.serialForMemfault\(\), chunk\)\n",
         r"\1        // Orb: Core's telemetry is removed; the watch's diagnostics are dropped here.\n")
    edit(web_services,
         r"(override fun uploadAnalyticsHeartbeat\(payload: ByteArray, watchInfo: WatchInfo\) \{\n)"
         r"[ \t]*analyticsHeartbeatQueue\.enqueue\(\n(?:[ \t]*[a-zA-Z]+ = [^\n]*\n){3}[ \t]*\)\n",
         r"\1        // Orb: Core's telemetry is removed; the watch's analytics are dropped here.\n")

    # The health library falls back to Google Fit, which needs Google Play services, on phones
    # without Health Connect. Switch the fallback off and drop its activity.
    watch_module = "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt"
    edit(
        watch_module,
        r"^import com\.viktormykhailiv\.kmp\.health\.HealthManagerFactory\n",
        "import com.viktormykhailiv.kmp.health.HealthManagerFactory\n"
        "import com.viktormykhailiv.kmp.health.HealthManagerFactoryOptions\n",
    )
    edit(
        watch_module,
        r"HealthManagerFactory\(\)\.createManager\(\)",
        "HealthManagerFactory().createManager(HealthManagerFactoryOptions(useGoogleFit = false))",
    )
    edit(
        "androidApp/src/main/AndroidManifest.xml",
        r"^    </application>\n",
        '        <activity\n'
        '            android:name="com.viktormykhailiv.kmp.health.legacy.GoogleFitPermissionActivity"\n'
        '            tools:node="remove" />\n'
        "    </application>\n",
    )
    # Core names these after its own package; they have to follow the application ID.
    edit(
        "pebble/src/androidMain/AndroidManifest.xml",
        r'android:authorities="coredevices\.coreapp\.pebblekit"',
        'android:authorities="${applicationId}.pebblekit"',
    )
    edit(
        "libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationHandler.kt",
        r'packageName == "coredevices\.coreapp" &&',
        f'packageName == "{APPLICATION_ID}" &&',
    )
    for provider in ("google", "apple", "github"):
        edit("gradle.properties", rf"^{provider}AuthEnabled=true$", f"{provider}AuthEnabled=false")

    # Call sites of Google code in files that change too often upstream to replace whole.
    main_application = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainApplication.kt"
    edit(main_application, r"^import com\.google\.firebase\.Firebase\n", "")
    edit(main_application, r"^import com\.google\.firebase\.crashlytics\.crashlytics\n", "")
    edit(
        main_application,
        r"^[ \t]*if \(AppContext\(this\)\.isDebugBuild\(\)\) \{\n"
        r"[ \t]*Firebase\.crashlytics\.setCrashlyticsCollectionEnabled\(false\)\n"
        r"[ \t]*\}\n",
        "",
    )
    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module, r"^import com\.google\.android\.play\.core\.appupdate\.AppUpdateManagerFactory\n", "")
    edit(android_module, r"^[ \t]*factory \{ AppUpdateManagerFactory\.create\(get\(\)\) \}\n", "")

    # Onboarding (replaced: OnboardingScreen.kt) goes straight from the welcome page to the
    # permissions; Orb supports watches only and has no account to sign in to. Core's trademark
    # rules leave "Pebble" only for saying which watches the app is for, so the welcome page
    # shows Orb's name, not the Pebble logo. The notification texts of the background service
    # (replaced: PebbleService.kt) name Orb and the watch, not Pebble.

    # Core defaults to cloud speech recognition, which needs a Core account.
    edit(
        "util/src/commonMain/kotlin/coredevices/util/CoreConfig.kt",
        r"val mode: CactusSTTMode = CactusSTTMode\.RemoteOnly,",
        "val mode: CactusSTTMode = CactusSTTMode.PlatformOnly,",
    )

    # Core stamps the build with `git describe`, which reports a modified checkout here and
    # goes out in the User-Agent. Use the Orb version, so servers can tell the builds apart.
    edit(
        "util/build.gradle.kts",
        r"^val headSha by lazy \{\n"
        r"[ \t]*project\.providers\.exec \{\n"
        r'[ \t]*commandLine\("git", "describe", "--always", "--dirty"\)\n'
        r"[ \t]*\}\.standardOutput\.asText\.get\(\)\.trim\(\)\n"
        r"\}\n",
        f'val headSha = "{version_name}"\n',
    )

    # Core's "System" speech mode asks for this permission when selected. Android's speech
    # recognition service requires the microphone permission of its caller.
    edit(
        "util/src/androidMain/kotlin/coredevices/util/AndroidPermissionRequester.kt",
        r'Permission\.SpeechRecognizer -> throw IllegalArgumentException\("SpeechRecognizer not needed on Android"\)',
        "Permission.SpeechRecognizer -> listOf(Manifest.permission.RECORD_AUDIO)",
    )

    # Settings that lead only to a Core account, Google services or Core's telemetry backends,
    # none of which Orb has. Filtered by title, so an upstream reorder doesn't matter; each
    # title has to still exist, so a rename upstream fails here instead of reappearing.
    settings_screen = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt"
    settings_text = (APP / settings_screen).read_text()
    for title in HIDDEN_SETTINGS:
        if f'title = "{title}"' not in settings_text:
            raise ApplyError(f"{settings_screen}: no setting titled {title!r} to hide")
    (APP / "pebble/src/commonMain/kotlin/coredevices/pebble/ui/OrbHiddenSettings.kt").write_text(
        "package coredevices.pebble.ui\n\n"
        "// Generated by Orb's apply.py.\n"
        "internal val orbHiddenSettings: Set<String> = setOf(\n"
        + "".join(f'    "{title}",\n' for title in HIDDEN_SETTINGS)
        + ")\n"
    )
    edit(
        settings_screen,
        r"^(\s*)rawSettingsItems = rawSettingsItems,\n",
        r"\1rawSettingsItems = rawSettingsItems.filterNot { it.title in orbHiddenSettings },\n",
    )
    # Of the speech modes, only the system recognizer and Rebble's service work without Core's
    # cloud or the removed on-device engine.
    edit(
        settings_screen,
        r"^(\s*)CactusSTTMode\.RebbleOnly,\n"
        r"\s*CactusSTTMode\.RebbleFirst,\n"
        r"\s*CactusSTTMode\.RebbleFallback -> rebbleVoiceAvailable\n"
        r"(\s*)CactusSTTMode\.PlatformOnly -> platformSttAvailable\n"
        r"\s*else -> true\n",
        r"\1CactusSTTMode.RebbleOnly -> rebbleVoiceAvailable\n"
        r"\2CactusSTTMode.PlatformOnly -> platformSttAvailable\n"
        r"\2else -> false\n",
    )
    edit(
        settings_screen,
        r'(title = "New Bug Report",\n\s*description = )"Please report a bug if anything went wrong!"',
        r'\1"Share the app and watch logs, e.g. with an issue report"',
    )
    edit(
        settings_screen,
        r'title = "New Bug Report"',
        'title = "Share Logs"',
    )

    # Core's update server answers only signed-in accounts; take Core's watches' firmware from
    # Core's GitHub releases instead (overlay: pebble/.../firmware/GitHubFirmware.kt).
    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module, r"^import coredevices\.api\.EngDashOtaApiImpl\n",
         "import coredevices.pebble.firmware.GitHubFirmwareApi\n")
    edit(util_module, r"single \{ EngDashOtaApiImpl\(\) \} bind EngDashOtaApi::class",
         "single { GitHubFirmwareApi(get(), get()) } bind EngDashOtaApi::class")
    edit(settings_screen, r"^(\s*)\) \+ watchPrefs\n", r"\1) + watchPrefs + orbPinnedFirmwareSetting()\n")
    # GitHubFirmwareApi puts the SHA-256 it verified in the URL fragment. Check the download that
    # gets installed against it, so only the bytes Orb checked can reach the watch.
    downloader = "libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/web/FirmwareDownloader.kt"
    edit(downloader, r"^import kotlinx\.io\.files\.SystemFileSystem\n",
         "import kotlinx.io.buffered\n"
         "import kotlinx.io.files.SystemFileSystem\n"
         "import kotlinx.io.readByteArray\n"
         "import okio.ByteString.Companion.toByteString\n")
    edit(downloader, r"httpClient\.get\(url\)", 'httpClient.get(url.substringBefore("#orb-sha256="))')
    edit(
        downloader,
        r'^([ \t]*)logger\.v \{ "Downloaded firmware to \$path" \}\n',
        r'\1val orbSha256 = url.substringAfter("#orb-sha256=", "").substringBefore("&")' "\n"
        r"\1if (orbSha256.isNotEmpty()) {" "\n"
        r"\1    val actual = SystemFileSystem.source(path).buffered().use { it.readByteArray() }.toByteString().sha256().hex()" "\n"
        r"\1    if (actual != orbSha256) {" "\n"
        r'\1        logger.w { "Downloaded firmware is not the bundle Orb verified; discarding it" }' "\n"
        r"\1        SystemFileSystem.delete(path)" "\n"
        r"\1        return@withTimeoutOr null" "\n"
        r"\1    }" "\n"
        r"\1}" "\n"
        r'\1logger.v { "Downloaded firmware to $path" }' "\n",
    )
    # A pinned version is the user's explicit choice, possibly a downgrade: offer it, never
    # install it unattended.
    edit(
        "pebble/src/commonMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateUiTracker.kt",
        r"^([ \t]*)update\.installsDirectly &&\n",
        r"\1update.installsDirectly &&" "\n" r'\1!update.url.contains("&orb-pinned") &&' "\n",
    )

    # Battery history is a page on Core's server for signed-in accounts.
    edit(
        settings_screen,
        r"^\s*Section\.Battery -> PebbleNavBarRoutes\.BatterySettingsRoute\n",
        "",
    )
    # The Watches screen's "Battery Life" menu item is removed in its replacement
    # (WatchesScreen.kt).

    # The bug-report screen can only submit to Core when signed in, but sharing the report
    # as a file works. Make sharing the main action.
    bug_report = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt"
    edit(
        bug_report,
        r"enabled = !sending && !showSuccess && !screenshotLoading && user != null && canSendReports,",
        "enabled = !sending && !showSuccess && !screenshotLoading,",
    )
    edit(bug_report, r"sendLogs\(shareLocally = false\)", "sendLogs(shareLocally = true)")
    edit(bug_report, r'Text\("Send Report"\)', 'Text("Share Logs")')
    edit(
        bug_report,
        r"^[ \t]*if \(user == null\) \{\n"
        r"[ \t]*Text\(\n"
        r'[ \t]*"You must sign in to submit a bug report",\n'
        r"(?:.*\n)*?"
        r"[ \t]*Spacer\(Modifier\.height\(8\.dp\)\)\n"
        r"[ \t]*\}\n",
        "",
    )
    # Core's bug-filing guide, its changelog, and its list of submitted reports.
    edit(
        bug_report,
        r"^[ \t]*PebbleElevatedButton\(\n"
        r"[ \t]*onClick = \{\n"
        r"[ \t]*scope\.launch \{\n"
        r'[ \t]*platform\.openUrl\("https://pbl\.zip/bugs"\)\n'
        r"(?:.*\n)*?"
        r'[ \t]*platform\.openUrl\("https://ndocs\.repebble\.com/changelog"\)\n'
        r"(?:.*\n)*?"
        r"[ \t]*fontWeight = FontWeight\.Bold\n"
        r"[ \t]*\)\n",
        "",
    )
    edit(
        bug_report,
        r'"Please note that logs \+ device info will be sent with this report"',
        '"The file holds logs and device info. Check what is in it before posting it publicly."',
    )
    edit(
        bug_report,
        r"^[ \t]*ElevatedCard\(\n"
        r"(?:(?![ \t]*ElevatedCard\().*\n)*?"
        r"[ \t]*coreNav\.navigateTo\(CommonRoutes\.ViewMyBugReportsRoute\)\n"
        r"(?:.*\n)*?"
        r'[ \t]*text = "My Bug Reports",\n'
        r"[ \t]*fontSize = 14\.sp,\n"
        r"[ \t]*\)\n"
        r"[ \t]*\}\n"
        r"[ \t]*\}\n"
        r"[ \t]*\}\n",
        "",
    )
    edit(
        bug_report,
        r'label = \{ Text\("Please describe the bug"\) \}',
        'label = { Text("Describe the problem (goes into the file)") }',
    )

    remove_index_ring(settings_screen)
    confirm_external_input()

    if extra_abis:
        edit(
            "androidApp/build.gradle.kts",
            r'abiFilters \+= setOf\("armeabi-v7a", "arm64-v8a"\)',
            "abiFilters += setOf("
            + ", ".join(f'"{abi}"' for abi in ["armeabi-v7a", "arm64-v8a", *extra_abis])
            + ")",
        )

    MARKER.write_text(f"{version_name}\n")
    print(f"Applied Orb {version_name} ({version_code}) to {APP.relative_to(ROOT)}/")


def reset() -> None:
    git("checkout", "-f", "HEAD")
    # Untracked files only; ignored build output stays so rebuilds remain incremental.
    git("clean", "-fd")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--extra-abi", action="append", default=[], metavar="ABI")
    args = parser.parse_args()
    try:
        if args.check:
            check_pin(read_version()[0])
            check_replaced()
            print("Pin and replaced-file hashes are current.")
        else:
            if args.reset:
                reset()
            apply(args.extra_abi)
    except ApplyError as error:
        print(f"apply.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
