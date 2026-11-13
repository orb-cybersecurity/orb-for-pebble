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
    # Rewritten without Core's cloud speech recognition and on-device engine (see
    # remove_core_speech()).
    "util/src/commonMain/kotlin/coredevices/util/transcription/HybridTranscriptionService.kt":
        "7294e5f0a3835d72c0e7746b477fa6c3d3aec2d3c25cf929c4e7cda88d955ff8",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/STTRouter.kt":
        "f66c6c31a4e0900c0c6f039f47db4deef3c5b616c3d075cb0f830ec600d1be78",
}

# Prebuilt binaries and files only they need, and Core's launcher artwork.
REMOVED = [
    "cactus-native",
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
    # Core's cloud speech recognition and its on-device engine (see remove_core_speech()).
    "cactus",
    "util/src/commonMain/kotlin/coredevices/api/WisprFlowAuth.kt",
    *(f"util/src/commonMain/kotlin/coredevices/util/transcription/{name}.kt" for name in (
        "WisprFlowTranscriptionService", "WisprFlowRESTTranscriptionService",
        "KirinkiTranscriptionService", "CactusTranscriptionService", "CactusModelPathProvider",
        "InferenceBoost")),
    "util/src/androidMain/kotlin/coredevices/util/transcription/CactusTranscriptionService.android.kt",
    "util/src/commonMain/kotlin/coredevices/util/models/ModelManager.kt",
    "util/src/commonMain/kotlin/coredevices/util/models/DownloadJobLiveness.kt",
    "util/src/androidMain/kotlin/coredevices/util/models/ModelManager.android.kt",
    "util/src/androidMain/kotlin/coredevices/util/models/ModelDownloadManager.android.kt",
    "util/src/commonMain/kotlin/coredevices/ui/ModelDownloadDialog.kt",
    "util/src/commonTest/kotlin/coredevices/util/models/DownloadJobLivenessTest.kt",
    "util/src/commonTest/kotlin/coredevices/util/transcription/LocalTimeoutTest.kt",
    "util/src/commonTest/kotlin/coredevices/util/transcription/WarmUpPolicyTest.kt",
    "util/src/commonTest/kotlin/coredevices/util/transcription/ValidateContainsSpeechTest.kt",
    "util/src/androidHostTest/kotlin/coredevices/util/transcription/MemInfoParserTest.kt",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/SttModelUpdatePrompt.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/ModelManagementScreen.kt",
    "pebble/src/commonMain/composeResources/drawable/wispr_flow_logo_black.png",
    "pebble/src/commonMain/composeResources/drawable/wispr_flow_logo_white.png",
    # Screens and dialogs that need a Core account, and Core's web pages about its own app
    # (see remove_core_account_screens()).
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/BatterySettingsScreen.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/ContactDeveloperScreen.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/ContactDeveloperApi.kt",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportsListScreen.kt",
    "util/src/commonMain/kotlin/coredevices/ui/SignInButton.kt",
    "util/src/androidMain/kotlin/coredevices/ui/SignInButton.android.kt",
    "util/src/iosMain/kotlin/coredevices/ui/SignInButton.ios.kt",
    "util/src/commonMain/kotlin/AppUpdateTracker.kt",
    # Stand-ins for Core's noise-suppression library that nothing depends on.
    "krisp-stubs",
    # Core's support chat: push messages, its bug-report API and the ticket viewer
    # (see remove_core_support_chat()).
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/api",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/api",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/api",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/push",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/push",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/push",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/apiModule.kt",
    "util/src/commonMain/kotlin/CommonApiConfig.kt",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/ViewBugReportScreen.kt",
    "composeApp/src/commonTest/kotlin/coredevices/coreapp/ui/screens/ViewBugReportScreenTest.kt",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/BugReportService.kt",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/ui/screens/BugReportProcessor.android.kt",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/ui/screens/BugReportProcessor.ios.kt",
]

# Catalog accessors of dependencies and plugins that must not be referenced at all.
DROPPED_ACCESSORS = (
    r"libs\.(?:firebase\.bom|firebase\.crashlytics(?:\.ndk)?|gms\.auth|identity\.google"
    r"|play\.update(?:\.ktx)?|crashkios|mixpanel\.android|kmpnotifier"
    r"|plugins\.googleServices|plugins\.firebaseCrashlytics)\b"
)


# Settings Orb removes (by title): they need a Core account, Google services, the removed
# on-device speech engine, or Core's telemetry backends. Each must still exist upstream, so a
# rename fails the apply instead of the setting coming back.
REMOVED_SETTINGS = (
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

    # The ring's Notion sign-in callback (voiceapp://) and its label.
    edit("androidApp/src/main/AndroidManifest.xml",
         r'^[ \t]*<intent-filter android:label="@string/intent_filter_notion_login">\n'
         r'(?:(?!</intent-filter>).*\n)*?[ \t]*<data android:scheme="voiceapp" />\n[ \t]*</intent-filter>\n', "")
    edit("androidApp/src/main/res/values/strings.xml",
         r'^[ \t]*<string name="intent_filter_notion_login">Notion Linking</string>\n', "")


def kotlin_bracket_pairs(text: str) -> dict[int, int]:
    """Map each "(" / "{" / "[" offset in Kotlin source to the offset of its closing bracket.

    Skips comments, string and raw-string literals (including ${...} templates) and char
    literals, so brackets inside setting descriptions don't count.
    """
    pairs: dict[int, int] = {}
    stack: list[int] = []
    closers = {")": "(", "}": "{", "]": "["}
    # Each frame: "code", a string kind, or "template:<offset of its ${ brace>".
    modes: list[str] = ["code"]
    i, n = 0, len(text)
    while i < n:
        mode, c = modes[-1], text[i]
        if mode in ('"', '"""'):
            if mode == '"' and c == "\\":
                i += 2
                continue
            if text.startswith(mode, i) and not (mode == '"""' and text.startswith('""""', i)):
                modes.pop()
                i += len(mode)
                continue
            if text.startswith("${", i):
                stack.append(i + 1)
                modes.append(f"template:{i + 1}")
                i += 2
                continue
            i += 1
            continue
        if text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ApplyError("unterminated block comment")
            i = end + 2
            continue
        if text.startswith('"""', i):
            modes.append('"""')
            i += 3
            continue
        if c == '"':
            modes.append('"')
            i += 1
            continue
        if c == "'":
            end = i + 1
            while end < n and text[end] != "'":
                end += 2 if text[end] == "\\" else 1
            i = end + 1
            continue
        if c in "({[":
            stack.append(i)
        elif c in closers:
            if not stack or text[stack[-1]] != closers[c]:
                raise ApplyError(f"unbalanced {c!r} at offset {i}")
            opener = stack.pop()
            pairs[opener] = i
            if mode == f"template:{opener}":
                modes.pop()
        i += 1
    if stack or modes != ["code"]:
        raise ApplyError("unbalanced brackets or unterminated string")
    return pairs


def remove_kotlin_block(path: str, start: str, expect: int = 1) -> None:
    """Remove whole Kotlin blocks: from the line where `start` matches through the line that
    closes the bracket `start` ends on (its last character must be "(" or "{").

    A blank line left doubled by the removal is dropped too.
    """
    file = APP / path
    text = file.read_text()
    matches = list(re.finditer(start, text, re.MULTILINE))
    if len(matches) != expect:
        raise ApplyError(f"{path}: expected {expect} match(es) of {start!r}, found {len(matches)}")
    pairs = kotlin_bracket_pairs(text)
    spans = []
    for m in matches:
        bracket = m.end() - 1
        if text[bracket] not in "({" or bracket not in pairs:
            raise ApplyError(f"{path}: {start!r} must end on an opening bracket")
        close = pairs[bracket]
        # A parameter list followed by a body on the same line: `fun f(…) {`, `x(…) {`.
        body = re.compile(r"\)[^\n{}()=]*\{").match(text, close)
        if text[bracket] == "(" and body:
            close = pairs[body.end() - 1]
        begin = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", close)
        end = len(text) if end < 0 else end + 1
        if text[begin - 2:begin] == "\n\n" and text[end:end + 1] == "\n":
            end += 1
        spans.append((begin, end))
    for begin, end in reversed(spans):
        text = text[:begin] + text[end:]
    file.write_text(text)


SETTING_CALL = re.compile(r"\b(?:basicSettings\w*Item|SettingsItem)\($")


def remove_setting(path: str, title: str) -> None:
    """Remove the settings-list entry titled `title`, whole, from the settings screen.

    The entry is the innermost `basicSettings…Item(` / `SettingsItem(` call around
    `title = "<title>"`, with a `navBarNav?.let { nav -> … }` wrapper if it has one, through
    its trailing comma. Exactly one such entry must exist.
    """
    file = APP / path
    text = file.read_text()
    hits = [m.start() for m in re.finditer(rf'^[ \t]*title = "{re.escape(title)}",$', text, re.MULTILINE)]
    if len(hits) != 1:
        raise ApplyError(f"{path}: expected 1 setting titled {title!r}, found {len(hits)}")
    pairs = kotlin_bracket_pairs(text)
    calls = [o for o, c in pairs.items()
             if text[o] == "(" and o < hits[0] < c and SETTING_CALL.search(text, 0, o + 1)]
    if not calls:
        raise ApplyError(f"{path}: setting {title!r} is not inside a settings item call")
    open_paren = max(calls)
    close = pairs[open_paren]
    start = text.rfind("\n", 0, open_paren) + 1
    line_head = text[start:open_paren + 1]
    wrapped = re.fullmatch(r"[ \t]*navBarNav\?\.let \{ nav -> \w+\(", line_head)
    if not (wrapped or re.fullmatch(r"[ \t]*\w+\(", line_head)):
        raise ApplyError(f"{path}: setting {title!r} starts in an unexpected form: {line_head!r}")
    tail = re.compile(r"\) \},\n" if wrapped else r"\),\n")
    m = tail.match(text, close)
    if not m:
        raise ApplyError(f"{path}: setting {title!r} doesn't end with the expected comma")
    file.write_text(text[:start] + text[m.end():])


def replace_literal(path: str, old: str, new: str, expect: int = 1) -> None:
    """Literal (non-regex) replacement in one file that must match exactly `expect` times."""
    file = APP / path
    text = file.read_text()
    count = text.count(old)
    if count != expect:
        raise ApplyError(f"{path}: expected {expect} occurrence(s) of {old!r}, found {count}")
    file.write_text(text.replace(old, new))


def confirm_external_input() -> None:
    """Links and files from outside the app take effect only after the user confirms them.

    - A custom-boot-config-url link must be https with a plain ASCII host; Orb shows the host
      and switches the Rebble account only once the user allows it.
    - A watchapp (.pbw) or language pack (.pbl) another app sends is installed only once the
      user confirms it by name; a watchapp replacing an installed one says so.
    - One request at a time, each in its own file, so what the user approves is what installs.
    The dialogs for boot configs and language packs are in Orb's WatchHomeScreen.kt overlay.
    """
    # Every file opened from outside gets its own path; a later one can't overwrite it.
    replace_literal(
        "pebble/src/androidMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.android.kt",
        'val fileToWrite = getTempFilePath(appContext, "sideloaded_file")',
        'val fileToWrite = getTempFilePath(appContext, "sideloaded_file_${kotlin.uuid.Uuid.random()}")',
    )

    handler = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt"
    replace_literal(handler, "    val pendingFirmwareSideload: StateFlow<PendingFirmwareSideload?>\n", """\
    val pendingFirmwareSideload: StateFlow<PendingFirmwareSideload?>

    /** A boot-config link waiting for the user to approve its host. */
    val pendingBootConfig: StateFlow<PendingBootConfig?>
    fun confirmPendingBootConfig(expected: PendingBootConfig)
    fun dismissPendingBootConfig()

    /** A language pack from another app waiting for the user to confirm it. */
    val pendingLanguagePack: StateFlow<PendingLanguagePack?>
    fun confirmPendingLanguagePack(expected: PendingLanguagePack)
    fun dismissPendingLanguagePack()
""")
    replace_literal(handler, "data class PendingFirmwareSideload(val file: Path, val fileName: String)\n", """\
data class PendingFirmwareSideload(val file: Path, val fileName: String)
data class PendingBootConfig(val path: String, val token: String, val host: String)
data class PendingLanguagePack(val file: Path, val name: String)

/** A name from a file or package, made safe to show: no control or formatting characters, one short line. */
fun orbDisplayName(raw: String, max: Int = 64): String {
    val cleaned = raw.filter {
        it.category !in setOf(
            CharCategory.CONTROL, CharCategory.FORMAT, CharCategory.LINE_SEPARATOR,
            CharCategory.PARAGRAPH_SEPARATOR, CharCategory.PRIVATE_USE,
        )
    }.replace(Regex("\\\\s+"), " ").trim()
    return if (cleaned.length > max) cleaned.take(max - 1) + "…" else cleaned
}
""")
    replace_literal(handler, "    private var reservedSideloadCount = 0\n", """\
    private var reservedSideloadCount = 0
    private val _pendingBootConfig = MutableStateFlow<PendingBootConfig?>(null)
    override val pendingBootConfig: StateFlow<PendingBootConfig?> = _pendingBootConfig.asStateFlow()

    override fun confirmPendingBootConfig(expected: PendingBootConfig) {
        // Only the request the user was shown.
        if (!_pendingBootConfig.compareAndSet(expected, null)) return
        applyBootConfig(expected.token, expected.path)
    }

    override fun dismissPendingBootConfig() {
        _pendingBootConfig.value = null
    }

    private val _pendingLanguagePack = MutableStateFlow<PendingLanguagePack?>(null)
    override val pendingLanguagePack: StateFlow<PendingLanguagePack?> = _pendingLanguagePack.asStateFlow()

    override fun confirmPendingLanguagePack(expected: PendingLanguagePack) {
        if (!_pendingLanguagePack.compareAndSet(expected, null)) return
        val connectedWatch =
            libPebble.watches.value.filterIsInstance<ConnectedPebble.Language>().firstOrNull()
        if (connectedWatch == null) {
            logger.w { "handleLanguagePack: no connected watch" }
            _snackBarMessages.tryEmit("Failed to load language pack: no connected watch")
            SystemFileSystem.delete(expected.file, mustExist = false)
            return
        }
        _snackBarMessages.tryEmit("Installing language pack...")
        connectedWatch.installLanguagePack(expected.file, expected.name)
    }

    override fun dismissPendingLanguagePack() {
        val pending = _pendingLanguagePack.value ?: return
        _pendingLanguagePack.value = null
        SystemFileSystem.delete(pending.file, mustExist = false)
    }
""")
    # Boot config: validate, then park the link for confirmation (one at a time); what used to
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
         lambda m: m.group(1) + """\
        val host = bootConfigHost(path)
        if (host == null) {
            logger.w("boot config link is not https with a plain host name")
            _snackBarMessages.tryEmit("Ignored a sign-in link: it must use https and a plain server name")
            return false
        }
        if (_pendingBootConfig.value != null) {
            logger.w("boot config link ignored: another one is waiting for the user")
            return false
        }
        _pendingBootConfig.value = PendingBootConfig(path = path, token = token, host = host)
        navigateToTab(PebbleNavBarRoutes.WatchesRoute)
        return true
    }

    private fun applyBootConfig(token: String, path: String) {
""" + m.group(2))
    replace_literal(handler, "        internal fun parseTokenFrom(path: String?): String? {\n", """\
        /**
         * Host (with any explicit port) of a boot-config link's URL. Null unless it is https with
         * no user info and a plain ASCII host name, so the name shown is the one connected to.
         */
        internal fun bootConfigHost(path: String): String? {
            val url = com.eygraber.uri.Uri.parseOrNull(path.removePrefix("/")) ?: return null
            if (!url.scheme.equals("https", ignoreCase = true)) return null
            if (url.encodedUserInfo != null) return null
            if (url.encodedAuthority?.contains('%') != false) return null
            val host = url.host ?: return null
            if (!Regex("[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?").matches(host)) return null
            return if (url.port > 0) "$host:${url.port}" else host
        }

        internal fun parseTokenFrom(path: String?): String? {
""")
    # Language packs: park for confirmation instead of installing at once.
    edit(handler,
         r"^(        val file = writeFile\(context, uri\)\n"
         r"        if \(file == null\) \{\n"
         r"            logger\.w \{ \"handleLanguagePack: couldn't write file\" \}\n"
         r"            _snackBarMessages\.tryEmit\(\"Failed to load language pack file\"\)\n"
         r"            return false\n"
         r"        \}\n)"
         r"        val connectedWatch =\n(?:.*\n)*?        connectedWatch\.installLanguagePack\(file, name\)\n"
         r"        return true\n",
         lambda m: m.group(1) + """\
        if (_pendingLanguagePack.value != null) {
            SystemFileSystem.delete(file, mustExist = false)
            return false
        }
        _pendingLanguagePack.value = PendingLanguagePack(file, orbDisplayName(name))
        navigateToTab(PebbleNavBarRoutes.WatchesRoute)
        return true
""")

    # Watchapps another app sends: confirm by name (and what it replaces) before installing.
    locker = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt"
    replace_literal(locker, "import kotlin.uuid.Uuid\n",
                    "import kotlin.uuid.Uuid\nimport kotlinx.coroutines.flow.first\n")
    replace_literal(locker, "        val pendingAppSideload by deepLinks.pendingAppSideload.collectAsState()\n", """\
        // (file, name or null if unreadable, title of the installed app it replaces)
        var externalSideload by remember { mutableStateOf<Triple<Path, String?, String?>?>(null) }
        externalSideload?.let { (path, name, replaces) ->
            fun discard() {
                externalSideload = null
                SystemFileSystem.delete(path, mustExist = false)
            }
            androidx.compose.material3.AlertDialog(
                onDismissRequest = ::discard,
                title = { Text(if (name != null) "Install watchapp?" else "Can't install this file") },
                text = {
                    Text(
                        when {
                            name == null -> "Another app sent a file that isn't a readable watchapp."
                            replaces != null -> "Another app sent \\"$name\\". Installing it replaces " +
                                "\\"$replaces\\" on your watch, and it keeps that app's permissions and " +
                                "data. Only install watchapps from sources you trust."
                            else -> "Another app sent \\"$name\\". Install it on your watch? Only " +
                                "install watchapps from sources you trust."
                        }
                    )
                },
                confirmButton = {
                    if (name != null) {
                        androidx.compose.material3.TextButton(onClick = {
                            externalSideload = null
                            sideload(path)
                        }) { Text("Install") }
                    } else {
                        androidx.compose.material3.TextButton(onClick = ::discard) { Text("OK") }
                    }
                },
                dismissButton = {
                    if (name != null) {
                        androidx.compose.material3.TextButton(onClick = ::discard) { Text("Cancel") }
                    }
                },
            )
        }
        val pendingAppSideload by deepLinks.pendingAppSideload.collectAsState()
""")
    replace_literal(locker, """\
            pendingAppSideload?.let {
                deepLinks.consumePendingAppSideload()
                sideload(it)
""", """\
            pendingAppSideload?.let {
                deepLinks.consumePendingAppSideload()
                // In the screen's scope: consuming the sideload restarts this effect.
                scope.launch {
                    if (externalSideload != null) {
                        // One at a time; the user is deciding on another file.
                        SystemFileSystem.delete(it, mustExist = false)
                        return@launch
                    }
                    val info = withContext(Dispatchers.IO) {
                        try {
                            PbwApp(it).info
                        } catch (e: Exception) {
                            null
                        }
                    }
                    val name = info?.let { i -> coredevices.pebble.orbDisplayName(i.longName.ifBlank { i.shortName }) }
                        ?.ifBlank { null }
                    val replaces = info?.let { i -> Uuid.parseOrNull(i.uuid) }
                        ?.let { uuid -> libPebble.getLockerApp(uuid).first() }
                        ?.let { app -> coredevices.pebble.orbDisplayName(app.properties.title) }
                    externalSideload = Triple(it, name, replaces)
                }
""")

    # The preview stand-in implements the handler interface too.
    replace_literal("pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt",
        "        override val pendingAppSideload: StateFlow<Path?> = MutableStateFlow(null)\n", """\
        override val pendingAppSideload: StateFlow<Path?> = MutableStateFlow(null)
        override val pendingBootConfig: StateFlow<coredevices.pebble.PendingBootConfig?> = MutableStateFlow(null)
        override fun confirmPendingBootConfig(expected: coredevices.pebble.PendingBootConfig) {}
        override fun dismissPendingBootConfig() {}
        override val pendingLanguagePack: StateFlow<coredevices.pebble.PendingLanguagePack?> = MutableStateFlow(null)
        override fun confirmPendingLanguagePack(expected: coredevices.pebble.PendingLanguagePack) {}
        override fun dismissPendingLanguagePack() {}
""")


def remove_core_speech(settings_screen: str) -> None:
    """Remove Core's cloud speech recognition and its on-device engine.

    Core's cloud recognizers (Wispr Flow, Kirinki) need a Core account. Its on-device engine
    (Cactus) is a prebuilt binary that Orb doesn't ship, and its models came from Hugging Face.
    Dictation goes to the phone's speech recognition service, or to Rebble's if the user chooses
    that. The speech services and router are replaced (REPLACED); the module, models and
    screens are removed (REMOVED); this unhooks the rest. CactusSTTMode stays, because
    settings that are already stored name its values; STTRouter sends every non-Rebble mode
    to the system recognizer.
    """
    # Build wiring: the cactus module.
    edit("settings.gradle.kts", r'^include\(":cactus"\)\n', "")
    for gradle in ("androidApp", "pebble", "util"):
        edit(f"{gradle}/build.gradle.kts", r'^[ \t]*(?:implementation|api|androidTestImplementation)\(project\(":cactus"\)\)\n', "")

    # util: what only the removed services used.
    downloads = "util/src/commonMain/kotlin/coredevices/util/models/ModelDownloadManager.kt"
    remove_kotlin_block(downloads, r"^expect class ModelDownloadManager \{")
    edit(downloads, r"^import kotlinx\.coroutines\.(Deferred|flow\.StateFlow)\n", "", expect=2)
    transcription = "util/src/commonMain/kotlin/coredevices/util/transcription/TranscriptionService.kt"
    remove_kotlin_block(transcription,
                        r"^/\*\* A \[TranscriptionService\] that can run on-device engines.*\n"
                        r"interface LocalTranscriptionService : TranscriptionService \{")
    edit(transcription, r"^import kotlinx\.coroutines\.flow\.SharedFlow\n", "")

    # composeApp: dependency injection, start-up and screens.
    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module,
         r"^import coredevices\.(api\.WisprFlowAuth|util\.models\.ModelManager"
         r"|util\.transcription\.(CactusModelPathProvider|CactusTranscriptionService"
         r"|KirinkiTranscriptionService|LocalTranscriptionService|WisprFlowRESTTranscriptionService))\n",
         "", expect=7)
    edit(util_module, r"^import org\.koin\.dsl\.binds\n", "")
    edit(util_module,
         r"^[ \t]*single \{ ModelManager\(get\(\), get\(\), getOrNull\(\)\) \}\n", "")
    edit(util_module,
         r"^[ \t]*singleOf\(::(WisprFlowAuth|WisprFlowRESTTranscriptionService|KirinkiTranscriptionService)\)\n",
         "", expect=3)
    remove_kotlin_block(util_module, r"^    single \{(?=\n        CactusTranscriptionService\()")
    edit(util_module,
         r"^    single \{\n        HybridTranscriptionService\(.*\n    \} binds arrayOf\(TranscriptionService::class, LocalTranscriptionService::class\)\n",
         "    single { HybridTranscriptionService(get(), get()) } bind TranscriptionService::class\n")
    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module, r"^import coredevices\.util\.models\.ModelDownloadManager\n", "")
    edit(android_module, r"^[ \t]*singleOf\(::ModelDownloadManager\)\n", "")

    delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    remove_kotlin_block(delegate, r"^    private fun initCactus\(\) \{")
    edit(delegate, r"^[ \t]*initCactus\(\)\n", "")
    edit(delegate, r"^internal (?:const )?val STT_\w+ = .*\n", "", expect=4)
    edit(delegate, r"^import coredevices\.util\.transcription\.CactusModelPathProvider\n", "")

    app = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/App.kt"
    edit(app, r"^[ \t]*SttModelUpdatePrompt\(\)\n", "")

    dialog = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/SpeechModelDownloadDialog.kt"
    edit(dialog,
         r"^[ \t]*config\.sttConfig\.mode\.usesLocalCactus\(\) ->\n[ \t]*CactusModelDownloadDialog\(.*\n", "")
    remove_kotlin_block(dialog, r"^@Composable\nprivate fun CactusModelDownloadDialog\(")
    edit(dialog, r"^import coredevices\.util\.models\.(ModelInfo|ModelManager)\n", "", expect=2)

    # pebble: the router's wiring and the offline-models screen.
    watch_module = "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt"
    edit(watch_module,
         r"^(        STTRouter\(\n)            cactus = get\(\),\n            rebble = get\(\),\n"
         r"            cactusService = get\(\),\n            coreConfigFlow = get\(\),\n"
         r"            audioFrameDecoder = get\(\),\n",
         r"\1            system = get(),\n            rebble = get(),\n            coreConfigFlow = get(),\n")
    edit(watch_module, r"^import coredevices\.pebble\.ui\.ModelManagementScreenViewModel\n", "")
    edit(watch_module, r"^[ \t]*viewModelOf\(::ModelManagementScreenViewModel\)\n", "")
    routes = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/PebbleRoutes.kt"
    edit(routes, r"^[ \t]*@Serializable\n[ \t]*data object OfflineModelsRoute : NavBarRoute\n\n", "")
    remove_kotlin_block(routes, r"^[ \t]*composable<PebbleNavBarRoutes\.OfflineModelsRoute> \{")

    # Settings: the state behind the removed speech settings, and the mode picker's checks for
    # cloud sign-in, the on-device engine and its models.
    edit(settings_screen,
         r"^import (com\.cactus\.isCactusSupported|coreapp\.pebble\.generated\.resources\.wispr_flow_logo_\w+"
         r"|coredevices\.util\.models\.(ModelInfo|ModelManager|RecommendedModel))\n",
         "", expect=6)
    remove_kotlin_block(settings_screen, r"^sealed interface RequestedLocalSTTMode \{")
    edit(settings_screen,
         r"^[ \t]*(val modelManager: ModelManager = koinInject\(\)"
         r"|var pendingSTTModeDialog by remember \{ mutableStateOf<CactusSTTMode\?>\(null\) \}"
         r"|val recommendedSTTModel = modelManager\.getRecommendedSTTModel\(\)"
         r"|val modelDownloadState by modelManager\.modelDownloadStatus\.collectAsState\(\)"
         r"|val modelDownloadStatus by modelManager\.modelDownloadStatus\.collectAsState\(\)"
         r"|val cactusSupported = remember \{ isCactusSupported\(\) \})\n",
         "", expect=6)
    remove_kotlin_block(settings_screen, r"^[ \t]*pendingSTTModeDialog\?\.let \{")
    remove_kotlin_block(settings_screen, r"^[ \t]*LaunchedEffect\(modelDownloadStatus\) \{")
    remove_kotlin_block(settings_screen, r"^[ \t]*val hasOfflineModels by produceState\(false\) \{")
    edit(settings_screen,
         r"^([ \t]*)val needsLocal = it == CactusSTTMode\.LocalOnly \|\|\n(?:[ \t]*it == .*\n){3}", "")
    edit(settings_screen,
         r"^[ \t]*\} else if \(it != CactusSTTMode\.RemoteOnly && !isPlatform && !cactusSupported\) \{\n"
         r"[ \t]*snackbarDisplay\.showSnackbar\(.*\n"
         r"[ \t]*\} else if \(it != CactusSTTMode\.LocalOnly && !isPlatform && !isRebble && coreUser == null\) \{\n"
         r"[ \t]*snackbarDisplay\.showSnackbar\(.*\n"
         r"[ \t]*showSignInDialog = true\n"
         r"[ \t]*\} else if \(needsLocal && !hasOfflineModels\) \{\n"
         r"[ \t]*pendingSTTModeDialog = it\n",
         "")
    remove_kotlin_block(settings_screen, r"^[ \t]*extraSupportingContent = \{(?=\n[ \t]*modelDownloadState\.takeIf)")


def remove_core_account_screens(settings_screen: str) -> None:
    """Remove screens and dialogs that only work with a Core account, and Core's web pages
    about its own app.

    - Battery history is a page on Core's server for signed-in accounts. Its entry points were
      already gone (apply() and WatchesScreen.kt); the screen and its route go too.
    - Contact Developer sends messages through Core's app store with a Core sign-in token.
    - The list of submitted bug reports is fetched from Core's support backend for the signed-in
      account. Sharing logs as a file stays.
    - The sign-in dialog offers only Google, Apple and GitHub sign-in to Core's account, all of
      which Orb switches off, so it only ever said that sign-in is disabled.
    - "What's new" opened Core's changelogs for its own app and for PebbleOS, hosted on Notion.
      The badge that pointed at them goes too. The alpha testers' guide had no entry point.
    - The settings screen kept the state of the removed telemetry toggles.

    Core's release builds and Orb's are both QA builds (util/build.gradle.kts defaults QA to
    true), so the routes inside `if (CommonBuildKonfig.QA)` were reachable.
    """
    # Battery.
    routes = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/PebbleRoutes.kt"
    edit(routes, r"^    @Serializable\n    data object BatterySettingsRoute : NavBarRoute\n\n", "")
    remove_kotlin_block(routes,
                        r"^    composableWithAnimations<PebbleNavBarRoutes\.BatterySettingsRoute>\(viewModel\) \{")

    # Contact Developer.
    edit(routes,
         r"^\n    @Serializable\n    data class ContactDeveloperRoute\(\n"
         r"        val appId: String,\n        val appTitle: String,\n    \) : CoreRoute\n", "")
    remove_kotlin_block(routes, r"^    composable<PebbleRoutes\.ContactDeveloperRoute> \{")
    watch_module = "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt"
    edit(watch_module, r"^import coredevices\.pebble\.services\.ContactDeveloperApi\n", "")
    edit(watch_module, r"^[ \t]*singleOf\(::ContactDeveloperApi\)\n", "")
    locker_app = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerAppScreen.kt"
    edit(locker_app, r"^[ \t]*val contactStoreId = entry\.storeId\n", "")
    edit(locker_app,
         r"^( *)\} else if \(\n *commonAppStore\?\.contactable == true &&\n(?:.*\n)*?"
         r" *PebbleRoutes\.ContactDeveloperRoute\(\n(?:.*\n)*?\1\}\n",
         r"\1}\n")

    # Core's web pages and the bug-report list.
    nav_host = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt"
    gone_routes = ("AlphaTestInstructionsRoute", "ViewMyBugReportsRoute", "RoadmapChangelogRoute",
                   "PebbleOsChangelogRoute")
    for route in gone_routes:
        remove_kotlin_block(nav_host, rf"^[ \t]*composable<CommonRoutes\.{route}> \{{")
    edit(nav_host, r"^import coredevices\.coreapp\.ui\.screens\.BugReportsListScreen\n", "")
    edit("util/src/commonMain/kotlin/CommonRoutes.kt",
         rf"^    @Serializable\n    data object (?:{'|'.join(gone_routes)}) : CoreRoute\n\n",
         "", expect=len(gone_routes))
    for title in ("What’s new in the app", "Show badge when app was updated", "What’s new in PebbleOS"):
        remove_setting(settings_screen, title)
    edit(settings_screen,
         r"^    val appUpdateTracker: AppUpdateTracker = koinInject\(\)\n"
         r"    val appWasUpdated by appUpdateTracker\.appWasUpdated\.collectAsState\(\)\n"
         r"    val appUpdated = if \(appWasUpdated && coreConfig\.showAppUpdatedBadge\) 1 else 0\n"
         r"    return permissionBadgeCount \+ updatesAvailable \+ appUpdated\n",
         "    return permissionBadgeCount + updatesAvailable\n")
    edit(settings_screen,
         r"^    val appUpdateTracker: AppUpdateTracker = koinInject\(\)\n"
         r"    val showChangelogBadge = remember \{ appUpdateTracker\.appWasUpdated\.value \}\n", "")
    edit(settings_screen, r"^import AppUpdateTracker\n", "")
    for module, line in (
        ("composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt",
         r"^[ \t]*singleOf\(::AppUpdateTracker\)\n"),
        ("pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt",
         r"^[ \t]*single \{ AppUpdateTracker\(get\(\), get\(\)\) \}\n"),
    ):
        edit(module, line, "")
        edit(module, r"^import AppUpdateTracker\n", "")

    # The sign-in dialog. Choosing Rebble's speech service without a subscription still says so.
    edit(settings_screen, r"^[ \t]*var showSignInDialog by remember \{ mutableStateOf\(false\) \}\n", "")
    remove_kotlin_block(settings_screen, r"^[ \t]*if \(showSignInDialog\) \{")
    edit(settings_screen,
         r'^([ \t]*snackbarDisplay\.showSnackbar\("Rebble speech recognition requires a Rebble subscription"\)\n)'
         r"[ \t]*showSignInDialog = true\n",
         r"\1")
    bug_report = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt"
    edit(bug_report, r"^[ \t]*var showSignInDialog by remember \{ mutableStateOf\(false\) \}\n", "")
    remove_kotlin_block(bug_report, r"^[ \t]*if \(showSignInDialog\) \{")
    for path in (settings_screen, bug_report):
        edit(path, r"^import coredevices\.ui\.SignInDialog\n", "")

    # State left from the removed account and telemetry settings.
    edit(settings_screen,
         r"^    val coreUser by Firebase\.auth\.authStateChanged\.map \{\n"
         r"        it\?\.emailOrNull\n"
         r"    \}\.distinctUntilChanged\(\)\n"
         r"        \.collectAsState\(Firebase\.auth\.currentUser\?\.emailOrNull\)\n", "")
    edit(settings_screen,
         r"^    val (analyticsBackend: AnalyticsBackend|usersDao: UsersDao|coreAnalytics: CoreAnalytics) = koinInject\(\)\n",
         "", expect=3)
    edit(settings_screen,
         r"^    val enable(Firebase|Memfault|Mixpanel) = remember \{ mutableStateOf\(settings\.getBoolean\(KEY_ENABLE_\w+_UPLOADS, true\)\) \}\n",
         "", expect=3)
    edit(settings_screen, r"^            enable(Firebase|Memfault|Mixpanel),\n", "", expect=3)
    edit(settings_screen,
         r"^object SettingsKeys \{\n(?:    const val KEY_ENABLE_\w+_UPLOADS = \"\w+\"\n){3}\}\n\n", "")
    edit(settings_screen,
         r"^import (coredevices\.analytics\.(AnalyticsBackend|CoreAnalytics|setUser)"
         r"|coredevices\.firestore\.UsersDao"
         r"|coredevices\.pebble\.ui\.SettingsKeys\.KEY_ENABLE_\w+_UPLOADS"
         r"|coredevices\.util\.emailOrNull"
         r"|dev\.gitlive\.firebase\.(Firebase|auth\.auth|crashlytics\.crashlytics)"
         r"|kotlinx\.coroutines\.flow\.(distinctUntilChanged|map))\n",
         "", expect=13)

    # Nothing depends on the stand-ins for Core's noise-suppression library (in REMOVED).
    edit("settings.gradle.kts", r'^include\(":krisp-stubs"\)\n', "")


def remove_core_support_chat() -> None:
    """Remove Core's support chat and the push messages that fed it.

    Core uploads bug reports to its support backend for a signed-in Core account and answers
    them in a chat that arrives as push messages (KMPNotifier on Firebase Cloud Messaging) and
    opens in a ticket viewer. Orb has no Core account and no Firebase, so the report is only
    ever shared as a file (BugReportProcessor.kt, replaced); the API, the push handling, the
    viewer and the foreground service that showed upload progress go (REMOVED), and this
    unhooks them. KMPNotifier and Orb's stand-in for it go too: nothing else used them.
    """
    delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    edit(delegate,
         r"^import (com\.mmk\.kmpnotifier\.notification\.NotifierManager"
         r"|coredevices\.coreapp\.api\.BugReports|coredevices\.coreapp\.push\.PushMessaging)\n",
         "", expect=3)
    edit(delegate, r"^    private val (pushMessaging: PushMessaging|bugReports: BugReports),\n", "", expect=2)
    edit(delegate, r"^        (pushMessaging|bugReports)\.init\(\)\n", "", expect=2)

    main_application = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainApplication.kt"
    edit(main_application,
         r"^import (com\.mmk\.kmpnotifier\.notification\.(NotifierManager|configuration\.NotificationPlatformConfiguration)"
         r"|coredevices\.coreapp\.di\.apiModule)\n",
         "", expect=3)
    edit(main_application, r"^[ \t]*apiModule,\n", "")
    remove_kotlin_block(main_application, r"^        NotifierManager\.initialize\(")

    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module, r"^import coredevices\.coreapp\.push\.PushMessaging\n", "")
    edit(util_module, r"^[ \t]*singleOf\(::PushMessaging\)\n", "")

    # The ticket viewer, its route and the deep link that push notifications opened.
    nav_host = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt"
    remove_kotlin_block(nav_host, r"^[ \t]*composable<CommonRoutes\.ViewBugReportRoute>\(")
    edit(nav_host, r"^import coredevices\.coreapp\.ui\.screens\.ViewBugReportScreen\n", "")
    edit("util/src/commonMain/kotlin/CommonRoutes.kt",
         r"^    @Serializable\n    data class ViewBugReportRoute\(\n        val conversationId: String,\n"
         r"    \) : CoreRoute\n\n", "")
    deep_links = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandler.kt"
    edit(deep_links, r"^        private const val (VIEW_BUG_REPORT_PATH|CONVERSATION_ID_QUERY_PARAM) = .*\n", "", expect=2)
    edit(deep_links,
         r"^\n        fun CommonRoutes\.ViewBugReportRoute\.asUri\(\): Uri = Uri\.Builder\(\)\n"
         r"(?:            \..*\n){4}            \.build\(\)\n", "")

    # The bug-report screen asked whether Core's upload service was configured.
    edit("composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt",
         r"^[ \t]*val canSendReports = bugReportProcessor\.canSendReports\(\)\n", "")

    # The upload progress service, and a service entry whose class went with Core's model
    # downloads (remove_core_speech()).
    manifest = "androidApp/src/main/AndroidManifest.xml"
    edit(manifest,
         r'^        <service\n            android:name="\.BugReportService"\n(?:            .*\n){2}'
         r'            android:foregroundServiceType="connectedDevice" />\n', "")
    edit(manifest,
         r'^        <service android:name="coredevices\.util\.models\.ModelDownloadService"\n'
         r'(?:            .*\n){2}        </service>\n', "")


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

    settings_screen = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt"
    for title in REMOVED_SETTINGS:
        remove_setting(settings_screen, title)
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
    remove_core_speech(settings_screen)
    confirm_external_input()
    remove_core_account_screens(settings_screen)
    remove_core_support_chat()

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
