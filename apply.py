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
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
    "util/src/commonMain/kotlin/coredevices/util/transcription/PlatformSpeechRecognizer.kt":
        "34e5738df81313cfe342cf74abea14241993a6c667fb4e2f20a8f6d774babae2",
    "util/src/commonMain/kotlin/coredevices/util/transcription/SpeechModelAvailability.kt":
        "eb27d582a32869f2bd415c3934ca0efef12de314d0943d55e4c46da39d4aefac",
    'pebble/src/androidMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.android.kt': '0feeaeb7072ca4bd3856a3febf3547af9a53340889666ede463497ad1fd2df87',
    'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/classic/io/rebble/libpebblecommon/pebblekit/classic/PebbleKitClassicStartListeners.kt': '247f94341bb8d647a375a213ae732ad5b59ed0c1f053ebae3155ae7382b14d07',
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/web/FirmwareDownloader.kt': '44fba7bd14972ed37e170b1456b1435235cc99b9383d3560fe2257585594455b',
    "util/src/androidMain/kotlin/coredevices/util/transcription/PlatformSpeechRecognizer.android.kt":
        "4b95f649c8dd2a5e2e3c6e3a19f9c05836d64315d0a75f8aa096201ff5819d36",
    "util/src/commonMain/kotlin/theme/Theme.kt":
        "76f3cfc7ce8722c581eec20a7638b03a92bc666481a41c052c337b5ffe668ceb",
    "util/src/androidMain/res/mipmap-anydpi-v26/ic_launcher.xml":
        "9c3a7e0a6515c6e1a7ae834a9ae430311ebc3241f7b2e5e7f0460aa690709a7c",
    "util/src/androidMain/res/values/ic_launcher_background.xml":
        "2b3d92d6e19240c4fc0600e8264074f8f225b309f8bddbf9f320e22c43e07fee",
    "util/src/androidMain/res/drawable/ic_notification.xml":
        "ebbaa2c938c3ec08711ad4321616ec4815993de4d59bd86edf83e5ce8acf8af2",
    # Rewritten without Core's Index 01 ring (see remove_index_ring()); the replacements also
    # carry Orb's other changes to these files.
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/PebbleService.kt":
        "5b92fcfea72d91cfde43c67a5ff99284824b767091f2b139ca30134f1ed86376",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/PebbleBackgroundManager.kt":
        "3e99e6895ed9efd054313a1dffabbbdceb781f6aceb19b7a057b881868c35534",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportProcessor.kt":
        "0e66a2604b8c9e08d5f6970d23743dfee771e8b03b143485854cd3d74581a532",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/OnboardingScreen.kt":
        "751898c0160d2604f7e598356bd61245f637a0f65c179b8147146d8af6d6951f",
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchHomeScreen.kt":
        "9f809f82a8a7f34275ff9960fef49d15df5913cb33e83c3b51dd5907e9c180d7",
    "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchesScreen.kt":
        "75b3647760614324f93f6005e1dad7d32d56f3dfbdf2a7202c5f1d5ded66dada",
    "pebble/src/commonTest/kotlin/coredevices/pebble/ui/WatchHomeNavTabTest.kt":
        "4e443ba4a8d95781ba58cec133208c521b0d63363fc3346c80373671a3574dae",
    # Rewritten without Core's cloud speech recognition and on-device engine (see
    # remove_core_speech()).
    "util/src/commonMain/kotlin/coredevices/util/transcription/HybridTranscriptionService.kt":
        "7294e5f0a3835d72c0e7746b477fa6c3d3aec2d3c25cf929c4e7cda88d955ff8",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/STTRouter.kt":
        "f66c6c31a4e0900c0c6f039f47db4deef3c5b616c3d075cb0f830ec600d1be78",
    # Orb's on-phone list of store apps in place of Core's cloud locker (see remove_cloud_locker()).
    "pebble/src/commonMain/kotlin/coredevices/pebble/account/FirestoreLocker.kt":
        "c23f89a47c3da5e07aa942979ca59bcc7b74ec92338ff48a47986fe4a933d749",
    # Orb's backup rules in place of Core's, which only excluded Firebase sign-in files (see
    # set_backup_rules()).
    "androidApp/src/main/res/xml/backup_rules.xml":
        "31731add4334f11a7fa5a4e4d6479bfd43f71c079023ddb8ea9a4f4b0a7de97e",
    "androidApp/src/main/res/xml/data_extraction_rules.xml":
        "c315d40bf10aa1ee14de35ffee01b39bc90adf68df80aebb10f7ab71e3a14783",
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
    # Used only to generate the removed ring's tool schemas.
    "toolschemagen",
    "toolschemaannotations",
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
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/ui/screens/BugReport.android.kt",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/ui/screens/BugReport.ios.kt",
    # Core's cloud locker's helpers: permission decisions uploaded to it, and a one-off move of
    # copies the official app once sideloaded (see remove_cloud_locker()).
    "pebble/src/commonMain/kotlin/coredevices/pebble/account/PermissionDecisionSync.kt",
    "pebble/src/commonTest/kotlin/coredevices/pebble/account/PermissionDecisionSyncTest.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/BundledAppMigration.kt",
    # Core's account: its user record in Firestore, what synced with it, and the sign-in
    # providers, all switched off (see remove_core_account()).
    "util/src/commonMain/kotlin/coredevices/firestore",
    "util/src/commonTest/kotlin/coredevices/firestore",
    "util/src/commonMain/kotlin/coredevices/database/UserConfigDao.kt",
    "util/src/commonMain/kotlin/coredevices/util/auth",
    "util/src/commonMain/kotlin/coredevices/util/FirebaseAuth.kt",
    "composeApp/src/commonMain/kotlin/coredevices/coreapp/auth",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/auth",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/auth",
    "pebble/src/commonMain/kotlin/coredevices/pebble/account/FirestoreKnownWatchesDao.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/account/FirestoreKnownWatchesSync.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/account/PermissionSettingsSync.kt",
    "pebble/src/commonTest/kotlin/coredevices/pebble/account/PermissionSettingsSyncTest.kt",
    # The last code that needed a Core sign-in token (see remove_firebase()).
    "util/src/commonMain/kotlin/coredevices/api/ApiClient.kt",
    "util/src/commonMain/kotlin/coredevices/api/ApiAuthException.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/plugin/HostedPluginOAuthApi.kt",
    # Core's app analytics, which had no backend in Orb (see remove_analytics()).
    "util/src/commonMain/kotlin/coredevices/analytics",
    "util/src/androidMain/kotlin/coredevices/analytics",
    "util/src/iosMain/kotlin/coredevices/analytics",
    "util/src/commonTest/kotlin/coredevices/analytics",
    "util/src/commonMain/kotlin/coredevices/util/transcription/TranscriptionAnalytics.kt",
    "util/src/commonTest/kotlin/coredevices/util/transcription/TranscriptionAnalyticsTest.kt",
    "libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/LibPebbleAnalytics.kt",
    *(f"libpebble3/src/{source}/kotlin/io/rebble/libpebblecommon/connection/{name}.kt"
      for source, name in (
          ("commonMain", "ConnectionFailureHandler"),
          ("androidMain", "ConnectionFailureHandler.android"),
          ("iosMain", "ConnectionFailureHandler.ios"))),
    # Orb ships an Android app. Core's native iOS host still wires accounts, push and telemetry;
    # remove that unused host and its DI, retaining shared library platform implementations.
    "iosApp",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/IOSDelegate.kt",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/MetricKitExitReporter.kt",
    "composeApp/src/iosMain/kotlin/coredevices/coreapp/di/iosDefaultModule.kt",
    # Core's queue of background sync tasks, which nothing in Orb uses (see remove_sync_manager()).
    "util/src/commonMain/kotlin/coredevices/util/sync",
    "util/src/androidMain/kotlin/coredevices/util/sync",
    "util/src/iosMain/kotlin/coredevices/util/sync",
    "util/src/commonTest/kotlin/coredevices/util/sync",
    # Code left with nothing to call it once its features were removed
    # (see remove_dead_leftovers()).
    "util/src/commonMain/kotlin/coredevices/api/WisprFlow.kt",
    "util/src/commonMain/kotlin/coredevices/util/integrations",
    "util/src/androidMain/kotlin/coredevices/util/integrations",
    "util/src/iosMain/kotlin/coredevices/util/integrations",
    "util/src/commonMain/kotlin/coredevices/util/OAuthRedirectHandler.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/services/OAuthService.kt",
    "util/src/commonMain/kotlin/coredevices/util/queue",
    "util/src/commonTest/kotlin/coredevices/util/queue",
    "util/src/commonMain/kotlin/coredevices/util/transcription/NullTranscriptionService.kt",
    "pebble/src/commonMain/kotlin/coredevices/pebble/account/FirestoreKnownWatch.kt",
    "util/src/commonMain/kotlin/coredevices/database/UserConfig.kt",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/PermissionRequestHandler.kt",
    # The in-app web page viewer, last used for Core's help site (see remove_help_page()).
    "util/src/commonMain/kotlin/coredevices/ui/GenericWebViewScreen.kt",
    # Core's test hooks for adb, and a Bluetooth pairing logger (see remove_debug_receivers()).
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/debug",
    "composeApp/src/androidMain/kotlin/coredevices/coreapp/util/BluetoothPairingDebugLogger.kt",
    # Tables of Core's telemetry uploads and sync queue (see drop_core_telemetry_tables()).
    *(f"util/src/commonMain/kotlin/coredevices/database/{name}.kt" for name in (
        "HeartbeatEntity", "MemfaultChunkEntity", "AnalyticsHeartbeatEntity", "SyncTaskEntity")),
    # Inert permissions, phone-app updates, and speech model management.
    'util/src/iosMain/kotlin/coredevices/util/clock/NativeAlarmKitBridge.kt',
    'util/src/commonMain/kotlin/AppUpdate.kt',
    'util/src/androidMain/kotlin/AppUpdate.android.kt',
    'util/src/iosMain/kotlin/AppUpdate.ios.kt',
    'composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/SpeechModelDownloadDialog.kt',
    'util/src/commonMain/kotlin/coredevices/util/models/ModelDownloadManager.kt',
    'util/src/iosMain/kotlin/coredevices/util/models/ModelDownloadManager.ios.kt',
    'util/src/commonTest/kotlin/coredevices/util/transcription/PlatformModelStateTest.kt',
    'util/src/commonTest/kotlin/coredevices/util/transcription/SpeechModelPromptTest.kt',
    'pebble/src/androidMain/kotlin/coredevices/pebble/services/CactusTranscription.android.kt',
    'pebble/src/iosMain/kotlin/coredevices/pebble/services/CactusTranscription.ios.kt',
    # Cloud developer transport and hosted plugin sign-ins.
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/devconnection/DevConnectionCloudpebbleProxy.kt',
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/plugin/PluginOAuthApi.kt',
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/plugin/PluginOAuthJsBridge.kt',
    # Android already forwards the real phone notifications.
    'util/src/commonMain/kotlin/coredevices/util/WatchNotifications.kt',
    'util/src/iosMain/kotlin/coredevices/util/IosWatchNotifier.kt',
    # Unreferenced providers, platform helpers, resources, and their obsolete tests.
    'pebble/src/commonMain/kotlin/coredevices/pebble/services/NullTranscriptionProvider.kt',
    'util/src/iosMain/kotlin/coredevices/util/transcription/CactusTranscriptionService.ios.kt',
    'util/src/commonMain/kotlin/coredevices/ui/PebbleWebview.kt',
    'util/src/androidMain/kotlin/coredevices/ui/PebbleWebview.android.kt',
    'util/src/iosMain/kotlin/coredevices/ui/PebbleWebview.ios.kt',
    'util/src/commonMain/kotlin/coredevices/util/PlatformBondingListener.kt',
    'util/src/androidMain/kotlin/coredevices/util/PlatformBondingListener.android.kt',
    'util/src/iosMain/kotlin/coredevices/util/PlatformBondingListener.ios.kt',
    'util/src/commonMain/kotlin/coredevices/util/flow/StateFlowExt.kt',
    'util/src/commonMain/kotlin/coredevices/util/flow/FlowExt.kt',
    'util/src/commonTest/kotlin/coredevices/util/flow/FlowExtTest.kt',
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/services/AppLogService.kt',
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/util/LazyLock.kt',
    'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/util/SerializationUtil.kt',
    'pebble/src/commonMain/kotlin/coredevices/pebble/services/Memfault.kt',
    'util/src/commonMain/kotlin/CoreIcons.kt',
    'util/src/commonMain/composeResources/drawable/core.xml',
    'util/src/commonMain/composeResources/drawable/notes.xml',
    'util/src/commonMain/composeResources/drawable/assistant.xml',
    'util/src/commonMain/composeResources/drawable/waveform.xml',
    'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/health/HealthParsingTest.kt',
    'pebble/src/commonTest/kotlin/coredevices/pebble/services/MemfaultTest.kt',
]

# Catalog accessors of dependencies and plugins that must not be referenced at all.
DROPPED_ACCESSORS = (
    r"libs\.(?:firebase\.bom|firebase\.crashlytics(?:\.ndk)?|gms\.(?:auth|location)|identity\.google"
    r"|play\.update(?:\.ktx)?|crashkios|mixpanel\.android|kmpnotifier"
    r"|firebase\.(?:auth|firestore|storage|common\.internal)"
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
    edit(core_config, r"^    val showIndexBatteryLife: Boolean = true,\n", "")
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
    ios_companion = "util/src/iosMain/kotlin/coredevices/util/IosCompanionDevice.kt"
    edit(ios_companion, r"^import coredevices\.libindex\.device\.IndexIdentifier\n", "")
    remove_kotlin_block(ios_companion,
                        r"^    override suspend fun registerDevice\(\n        identifier: IndexIdentifier,\n"
                        r"        uiContext: PlatformUiContext,\n        useClassicAssociation: Boolean\n    \) \{")
    remove_kotlin_block(ios_companion,
                        r"^    override fun (?:hasApprovedDevice|canRemoveBond|removeBond)\(identifier: IndexIdentifier\): Boolean \{", expect=3)
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
    watches_ios = "pebble/src/iosMain/kotlin/coredevices/pebble/ui/WatchesScreen.ios.kt"
    remove_kotlin_block(watches_ios, r"^@Composable\nactual fun RemovePairingMenuItem\(")
    edit(watches_ios,
         r"^import (androidx\.compose\.material\.icons\.(Icons|outlined\.Delete)"
         r"|androidx\.compose\.material3\.(DropdownMenuItem|Icon|Text)|androidx\.compose\.runtime\.Composable"
         r"|coredevices\.libindex\.device\.KnownIndexDevice)\n", "", expect=7)
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

    # These permissions belonged only to removed ring features.

    android_permission_requester = 'util/src/androidMain/kotlin/coredevices/util/AndroidPermissionRequester.kt'
    ios_permission_requester = 'util/src/iosMain/kotlin/coredevices/util/IosPermissionRequester.kt'

    edit('util/src/commonMain/kotlin/coredevices/util/Permission.kt',
         r"^    (?:SetAlarms|BatteryOptimization|Beeper|Reminders|AlarmKit),\n", '', expect=5)
    edit('util/src/commonMain/kotlin/coredevices/util/PermissionRequester.kt',
         r"^    Permission\.(?:SetAlarms|BatteryOptimization|Beeper|Reminders|AlarmKit) -> .*\n", '', expect=10)
    edit(android_permission_requester,
         r"^            Permission\.(?:SetAlarms|BatteryOptimization) -> .*\n", '', expect=4)
    edit(android_permission_requester,
         r"^    Permission\.(?:SetAlarms|BatteryOptimization|Reminders|AlarmKit) -> .*\n", '', expect=4)
    edit(android_permission_requester, r"^    Permission\.Beeper -> listOf\(\n(?:.*\n){2}    \)\n", '')

    remove_kotlin_block(android_permission_requester, r"^    private (?:suspend )?fun hasAlarmPermission\(")
    remove_kotlin_block(android_permission_requester, r"^    private (?:suspend )?fun requestAlarmPermission\(")

    remove_kotlin_block(android_permission_requester,
                    r"^    private (?:suspend )?fun batteryOptimizationsAreDisabled\(")
    remove_kotlin_block(android_permission_requester,
                    r"^    private (?:suspend )?fun requestBatteryOptimizationDisable\(")
    edit(android_permission_requester,
         r"^import (?:android\.app\.AlarmManager|android\.os\.PowerManager|androidx\.core\.content\.getSystemService|androidx\.core\.net\.toUri)\n", '', expect=4)
    edit(ios_permission_requester,
         r"^        (?:    )?Permission\.(?:SetAlarms|BatteryOptimization|Beeper|Reminders|AlarmKit) -> .*\n", '', expect=10)
    replace_literal(ios_permission_requester, 'import coredevices.util.clock.NativeAlarmKitBridge\n', '')

    replace_literal(ios_permission_requester, '    private var remindersGrantedThisSession = false\n', '')
    edit(ios_permission_requester,
         r"^    private fun hasRemindersPermission\(\): Boolean = remindersGrantedThisSession \|\|\n(?:.*\n){3}", '')
    remove_kotlin_block(ios_permission_requester, r"^    private (?:suspend )?fun requestRemindersPermission\(")

    remove_kotlin_block(ios_permission_requester, r"^    private (?:suspend )?fun hasAlarmKitPermission\(")
    remove_kotlin_block(ios_permission_requester, r"^    private (?:suspend )?fun requestAlarmKitPermission\(")

    replace_literal('pebble/src/commonMain/composeResources/values/strings.xml',
                    '    <string name="index">Index</string>\n', '')


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


def unwrap_kotlin_block(path: str, head: str) -> None:
    """Replace the block that the line `head` opens with its body, one level less indented.

    `head` is the whole opening line, ending in "{\n"; the block must have no else branch.
    """
    file = APP / path
    text = file.read_text()
    if text.count(head) != 1:
        raise ApplyError(f"{path}: expected one {head.strip()!r}")
    start = text.index(head)
    close = kotlin_bracket_pairs(text)[start + len(head) - 2]
    body = text[start + len(head):text.rfind("\n", 0, close) + 1]
    indent = len(head) - len(head.lstrip()) + 4
    body = "".join(line[4:] if line.startswith(" " * indent) else line for line in body.splitlines(True))
    end = text.index("\n", close) + 1
    if text[close + 1:end].strip():
        raise ApplyError(f"{path}: {head.strip()!r} has an else branch")
    file.write_text(text[:start] + body + text[end:])


def confirm_external_input() -> None:
    """Links and files from outside the app take effect only after the user confirms them.

    - A custom-boot-config-url link must be https with a plain ASCII host; Orb shows the host
      and switches the Rebble account only once the user allows it.
    - A watchapp (.pbw) or language pack (.pbl) another app sends is installed only once the
      user confirms it by name; a watchapp replacing an installed one says so.
    - One request at a time, each in its own file, so what the user approves is what installs.
    The dialogs for boot configs and language packs are in Orb's WatchHomeScreen.kt overlay.
    """
    handler = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt"
    replace_literal(handler, "    val pendingFirmwareSideload: StateFlow<PendingFirmwareSideload?>\n", """\
    val pendingFirmwareSideload: StateFlow<PendingFirmwareSideload?>

    /** A language pack from another app waiting for the user to confirm it. */
    val pendingLanguagePack: StateFlow<PendingLanguagePack?>
    fun confirmPendingLanguagePack(expected: PendingLanguagePack)
    fun dismissPendingLanguagePack()
""")
    replace_literal(handler, "data class PendingFirmwareSideload(val file: Path, val fileName: String)\n", """\
data class PendingFirmwareSideload(val file: Path, val fileName: String)
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
    # Keep Core's pending state and parser, with Orb's stricter host validation and a
    # confirmation bound to the displayed request. A second link cannot replace that request.
    replace_literal(handler, "    fun confirmPendingBootConfig()\n",
                    "    fun confirmPendingBootConfig(expected: PendingBootConfig)\n")
    replace_literal(handler, "        _pendingBootConfig.value = pending\n", """\
        if (!_pendingBootConfig.compareAndSet(null, pending)) {
            logger.w("boot config link ignored: another one is waiting for the user")
            return false
        }
""")
    replace_literal(handler, """\
    override fun confirmPendingBootConfig() {
        val pending = _pendingBootConfig.value ?: return
        _pendingBootConfig.value = null
""", """\
    override fun confirmPendingBootConfig(expected: PendingBootConfig) {
        if (!_pendingBootConfig.compareAndSet(expected, null)) return
        val pending = expected
""")
    replace_literal(handler, """\
            val url = Uri.parseOrNull(path.removePrefix("/")) ?: return null
            if (url.scheme != "https") return null
            val host = url.host?.takeIf { it.isNotBlank() } ?: return null
""", """\
            val host = bootConfigHost(path) ?: return null
""")
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
        override val pendingLanguagePack: StateFlow<coredevices.pebble.PendingLanguagePack?> = MutableStateFlow(null)
        override fun confirmPendingLanguagePack(expected: coredevices.pebble.PendingLanguagePack) {}
        override fun dismissPendingLanguagePack() {}
""")
    replace_literal("pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt",
                    "        override fun confirmPendingBootConfig() {}\n",
                    "        override fun confirmPendingBootConfig(expected: coredevices.pebble.PendingBootConfig) {}\n")


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

    # The system recognizer consumes audio and language, with the watch timeout outside it.

    hybrid_transcription = 'pebble/src/commonMain/kotlin/coredevices/pebble/services/HybridTranscription.kt'
    notification_dao = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/database/dao/NotificationDao.kt'
    app_nav_host = 'composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt'
    platform_speech_recognizer_ios = 'util/src/iosMain/kotlin/coredevices/util/transcription/PlatformSpeechRecognizer.ios.kt'
    core_config = 'util/src/commonMain/kotlin/coredevices/util/CoreConfig.kt'

    edit(hybrid_transcription,
         r"^import (?:io\.rebble\.libpebblecommon\.connection\.LibPebble|kotlinx\.io\.files\.Path)\n", '', expect=2)
    replace_literal(hybrid_transcription, 'internal expect fun tempTranscriptionDirectory(): Path\n', '')

    replace_literal(hybrid_transcription, '    private val libPebbleLazy: Lazy<LibPebble>,\n', '')
    replace_literal(hybrid_transcription, '        service.earlyInit()\n', '')

    edit(hybrid_transcription,
         r"^            val recentContacts = if \(isNotificationReply\) \{\n(?:.*\n)*?            \} else null\n", '')
    edit(hybrid_transcription,
         r"^                    (?:contentContext|dictionaryContext|encoding|totalTimeout) = .*\n", '', expect=4)
    replace_literal(watch_module, '            lazy { get<LibPebble3>() },\n', '')

    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/LibPebble.kt',
                    '    fun mostRecentNotificationParticipants(limit: Int): Flow<List<String>>\n', '')
    remove_kotlin_block('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/FakeLibPebble.kt',
                    r"^    override fun mostRecentNotificationParticipants\(")
    edit('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/notification/PlatformNotificationListener.kt',
         r"^    override fun mostRecentNotificationParticipants\(limit: Int\): Flow<List<String>> =\n        notificationsDao\.mostRecentParticipants\(limit\)\.map \{ row -> row\.flatMap \{ it\.people \} \}\n", '')
    edit(notification_dao,
         r'^    @Query\("SELECT DISTINCT people FROM NotificationEntity.*\n    fun mostRecentParticipants\(.*\n', '')
    remove_kotlin_block(notification_dao, r"^data class PeopleList\(")

    remove_kotlin_block(transcription,
                    r"^    /\*\*\n     \* Begin initialization of transcription service in the background\.\n     \*/\n    fun earlyInit\(")
    edit(transcription, r"^    val onInitialized: Channel<Boolean>\n", '')

    edit(transcription,
         r"^import (?:kotlin\.time\.Duration|kotlinx\.coroutines\.channels\.Channel|coredevices\.util\.AudioEncoding)\n", '', expect=3)
    edit(transcription,
         r"^        (?:conversationContext|dictionaryContext|contentContext|encoding|initialTimeout|totalTimeout): .*\n", '', expect=6)
    edit(transcription, r"^     \* @param (?:initialTimeout|totalTimeout).*\n", '', expect=2)

    remove_kotlin_block(transcription, r"^data class STTConversationMessage\(")
    remove_kotlin_block(transcription, r"^data class STTConversationContext\(")

    remove_kotlin_block(transcription, r"^enum class STTConvoRole \{")

    # Android recognizers manage their own models; there is no Orb download action.

    edit(settings_screen,
         r"^import coredevices\.util\.(?:models\.ModelDownloadStatus|transcription\.(?:SpeechModelAvailability|platformModelNeedsDownload|platformModelState))\n", '', expect=4)
    replace_literal(settings_screen,
                    '    val platformDownloadStatus by platformSpeechRecognizer.downloadStatus.collectAsState()\n', '')
    remove_kotlin_block(settings_screen, r"^    val platformModelAvailability by produceState\(")

    replace_literal(settings_screen,
                    '    val platformNeedsDownload = platformModelNeedsDownload(platformModelAvailability, platformDownloadStatus)\n', '')
    replace_literal(settings_screen, '                platformSpeechRecognizer.releaseUnusedModels(code)\n', '')

    remove_kotlin_block(settings_screen,
                    r"^                if \(coreConfig\.sttConfig\.mode == CactusSTTMode\.PlatformOnly\) \{")
    remove_kotlin_block(settings_screen,
                    r"^                            if \(isPlatform && platformNeedsDownload\) \{")
    remove_kotlin_block(settings_screen,
                    r'^                navBarNav\?\.let \{(?= nav -> basicSettingsActionItem\(\n                    title = "System Speech Model",)')
    edit('util/src/commonMain/kotlin/CommonRoutes.kt',
         r"^    /\*\* Dialog offering to download.*\n     \*  Routed.*\*/\n    @Serializable\n    data object SpeechModelDownloadDialog : CoreRoute\n\n    const val SPEECH_MODEL_DOWNLOAD_DEEP_LINK_PATH = .*\n    const val SPEECH_MODEL_DOWNLOAD_DEEP_LINK = .*\n", '')
    replace_literal(app_nav_host, 'import coredevices.coreapp.ui.SpeechModelDownloadDialog\n', '')

    remove_kotlin_block(app_nav_host, r"^        dialog<CommonRoutes\.SpeechModelDownloadDialog> \{")
    replace_literal('composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandler.kt',
                    '            CommonRoutes.SPEECH_MODEL_DOWNLOAD_DEEP_LINK_PATH -> CommonRoutes.SpeechModelDownloadDialog\n', '')

    edit(platform_speech_recognizer_ios,
         r"^import (?:coredevices\.util\.models\.(?:ModelDownloadStatus|inProgress)|kotlinx\.coroutines\.flow\.asStateFlow)\n", '', expect=3)
    replace_literal(platform_speech_recognizer_ios,
                    '    private val _downloadStatus = MutableStateFlow<ModelDownloadStatus>(ModelDownloadStatus.Idle)\n', '')
    replace_literal(platform_speech_recognizer_ios,
                    '    actual val downloadStatus: StateFlow<ModelDownloadStatus> = _downloadStatus.asStateFlow()\n', '')
    replace_literal(platform_speech_recognizer_ios,
                    '    actual suspend fun modelAvailability', '    private suspend fun modelAvailability')
    replace_literal(platform_speech_recognizer_ios,
                    '        if (_downloadStatus.value.inProgress) return SpeechModelAvailability.Downloading\n', '')
    remove_kotlin_block(platform_speech_recognizer_ios, r"^    actual fun downloadModel\(")

    remove_kotlin_block(platform_speech_recognizer_ios, r"^    actual fun releaseUnusedModels\(")
    edit(platform_speech_recognizer_ios,
         r"^    /\*\* Progress is 0\.\.1;.*\*/\n    @Volatile\n    var downloadAssets:.*\n\n    @Volatile\n    var releaseUnusedReservations:.*\n", '')
    replace_literal(platform_speech_recognizer_ios,
                    '    private val logger = Logger.withTag("PlatformSpeechRecognizer")\n', '')
    replace_literal(platform_speech_recognizer_ios, 'import co.touchlab.kermit.Logger\n', '')

    replace_literal(watch_module, 'import coredevices.pebble.services.NullTranscriptionProvider\n', '')

    replace_literal(watch_module,
                    '    factoryOf(::NullTranscriptionProvider) bind TranscriptionProvider::class\n', '')
    replace_literal(core_config, '    val modelName: String? = null,\n', '')

    replace_literal(core_config, '        val model = settings.getStringOrNull("cactus_stt_model")\n', '')
    replace_literal(core_config, '                    modelName = model,\n', '')

    replace_literal(core_config, 'mode=$mode, model=$model', 'mode=$mode')

    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt',
                    'import coredevices.util.models.inProgress\n',
                    '')


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

    # Delete the empty phone-app update integration after removing its consumers.

    common_app_delegate = 'composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt'
    preview_util = 'pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt'
    android_default_module = 'composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt'

    edit(common_app_delegate, r"^import coredevices\.coreapp\.util\.AppUpdate\n", '')
    replace_literal(common_app_delegate, '    private val appUpdate: AppUpdate,\n', '')

    replace_literal(common_app_delegate,
                    '                    add(scope.launch {\n                        appUpdate.updateAvailable.value\n                    })\n', '')
    edit(settings_screen, r"^import coredevices\.coreapp\.util\.AppUpdate(?:State)?\n", '', expect=2)

    replace_literal(settings_screen,
                    '    val appUpdate: AppUpdate = koinInject()\n    val updateState by appUpdate.updateAvailable.collectAsState()\n', '', expect=2)
    remove_kotlin_block(settings_screen, r"^    val updatesAvailable = when \(updateState\) \{")

    replace_literal(settings_screen, 'return permissionBadgeCount + updatesAvailable', 'return permissionBadgeCount')
    remove_kotlin_block(preview_util, r"^    single \{ object : AppUpdate \{")

    edit(preview_util, r"^import coredevices\.coreapp\.util\.AppUpdate(?:PlatformContent|State)?\n", '', expect=3)
    edit(android_default_module, r"^import coredevices\.coreapp\.util\.(?:AndroidAppUpdate|AppUpdate)\n", '', expect=2)

    replace_literal(android_default_module, '    singleOf(::AndroidAppUpdate) bind AppUpdate::class\n', '')
    replace_literal('util/src/commonMain/kotlin/coredevices/util/CoreConfig.kt',
                    '    val showAppUpdatedBadge: Boolean = true,\n', '')

    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt',
                    '            updateState,\n',
                    '')


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

    # Sharing is the only report path. Keep attachment capture and failures.

    bug_report_screen = 'composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt'

    remove_kotlin_block(bug_report_screen, r"^data class UserProps\(")


    replace_literal(bug_report_screen,
                    '        val (showSuccess, setShowSuccess) = remember { mutableStateOf(false) }\n', '')
    replace_literal(bug_report_screen,
                    '        val (sendingProgress, setSendingProgress) = remember { mutableStateOf<Double?>(null) }\n', '')
    replace_literal(bug_report_screen, 'fun sendLogs(shareLocally: Boolean)', 'fun sendLogs()')

    replace_literal(bug_report_screen, 'sendLogs(shareLocally = true)', 'sendLogs()', expect=2)
    replace_literal(bug_report_screen,
                    '            // Check if user is signed in before proceeding\n            if (user == null && !shareLocally) {\n                setStatus("Please sign in before submitting a bug report")\n                return\n            }\n\n', '')
    replace_literal(bug_report_screen,
                    '                // Extract Google ID token from current user\n                val currentUser = user\n                if (currentUser == null && !shareLocally) {\n                    setStatus("Please sign in before submitting a bug report")\n                    setSending(false)\n                    return@launch\n                }\n\n', '')
    edit(bug_report_screen,
         r"^                    (?:userName = currentUser\?\.userName,|userEmail = currentUser\?\.userEmail,|shareLocally = shareLocally,)\n", '', expect=3)
    replace_literal(bug_report_screen,
                    '                        is BugReportState.BugReportResult.Success -> Unit\n', '')
    replace_literal(bug_report_screen, '                        BugReportState.UploadingAttachments -> Unit\n', '')

    replace_literal(bug_report_screen, 'BugReportState.BugReportResult.Failed', 'BugReportState.Failed')
    edit(bug_report_screen, r"^                            setSendingProgress\(null\)\n", '', expect=2)

    replace_literal(bug_report_screen,
                    '                            if (!shareLocally) {\n                                coreNav.goBack()\n                            } else {\n                                setStatus("Gathering Watch Logs")\n                            }', '                            setStatus("Gathering Watch Logs")')
    replace_literal(bug_report_screen,
                    '!sending && !showSuccess && !screenshotLoading', '!sending && !screenshotLoading')
    remove_kotlin_block(bug_report_screen, r"^                                showSuccess -> \{")

    remove_kotlin_block(bug_report_screen,
                    r"^                if \(sending\) \{(?=\n                    CoreLinearProgressIndicator)")
    replace_literal(bug_report_screen, 'import coredevices.ui.CoreLinearProgressIndicator\n', '')

    replace_literal('composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt',
                    '                            status.contains("error", ignoreCase = true) ||\n                            status.contains("authentication", ignoreCase = true)',
                    '                            status.contains("error", ignoreCase = true)', expect=2)


def remove_crashlytics() -> None:
    """Remove the calls into Crashlytics, Google's crash reporting.

    Orb has no Firebase, and the stand-in Crashlytics drops everything, so a log writer that
    forwarded every log line and the crash-context keys the app set were inert. The file log
    (FileLogWriter) is unchanged; Share Logs still includes it.
    """
    logging = "composeApp/src/commonMain/kotlin/coredevices/coreapp/util/logging.kt"
    remove_kotlin_block(logging, r"^    Logger\.addLogWriter\(object : LogWriter\(\) \{")
    edit(logging,
         r"^    try \{\n        // Cactus logging is handled natively in the vendored SDK\n"
         r"    \} catch \(e: Exception\) \{\n        Logger\.e\(e\) \{ \"Failed to initialize Cactus logging\" \}\n    \}\n",
         "")
    edit(logging, r"^import dev\.gitlive\.firebase\.(Firebase|crashlytics\.crashlytics)\n", "", expect=2)

    delegate = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleAppDelegate.kt"
    remove_kotlin_block(delegate,
                        r"^            GlobalScope\.launch \{(?=\n                libPebble\.watches\.mapNotNull \{ watches ->\n"
                        r"                    watches\.maxByOrNull)")
    edit(delegate, r'^[ \t]*Firebase\.crashlytics\.setCustomKey\("active_pkjs_sessions", activeSessions\.size\)\n', "")
    edit(delegate, r"^[ \t]*Firebase\.crashlytics\.setCustomKey\(\n(?:[ \t]+.*\n){2}[ \t]*\)\n", "", expect=3)
    edit(delegate, r"^import dev\.gitlive\.firebase\.(Firebase|crashlytics\.crashlytics)\n", "", expect=(1, 2))


def remove_cloud_locker() -> None:
    """Keep the list of the user's store apps on the phone instead of in Core's cloud.

    Core's locker list lives in Firestore under a Core account. In Orb nobody is ever signed in,
    so that list never loaded: locker sync returned nothing (a Rebble account's locker never came
    in), and the check for which store an installed app came from never finished. Orb's
    FirestoreLocker.kt (replaced) keeps the list in the app's settings and syncs from the stores
    directly. What only fed the cloud list goes: uploading permission decisions to it, and moving
    the official app's old sideloaded copies into it, which nothing in Orb ever marks for moving.
    """
    watch_module = "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt"
    edit(watch_module, r"^import coredevices\.pebble\.account\.(FirestoreLockerDao|PermissionDecisionSync)\n", "", expect=2)
    edit(watch_module, r"^import coredevices\.pebble\.services\.BundledAppMigration\n", "")
    edit(watch_module, r"^import coredevices\.pebble\.account\.RealFirestoreLocker\n",
         "import coredevices.pebble.account.LocalLocker\n")
    edit(watch_module, r"^[ \t]*single \{ FirestoreLockerDao \{ get\(\) \} \}\n", "")
    edit(watch_module, r"^[ \t]*singleOf\(::(PermissionDecisionSync|BundledAppMigration)\)\n", "", expect=2)
    edit(watch_module, r"singleOf\(::RealFirestoreLocker\) bind FirestoreLocker::class",
         "singleOf(::LocalLocker) bind FirestoreLocker::class")

    delegate = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleAppDelegate.kt"
    edit(delegate, r"^import coredevices\.pebble\.services\.BundledAppMigration\n", "")
    edit(delegate, r"^    private val bundledAppMigration: BundledAppMigration,\n", "")
    edit(delegate, r"^[ \t]*bundledAppMigration\.init\(\)\n", "")

    app_delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    edit(app_delegate, r"^import coredevices\.pebble\.account\.(FirestoreLocker|PermissionDecisionSync)\n", "", expect=2)
    edit(app_delegate,
         r"^    private val (firestoreLocker: FirestoreLocker|permissionDecisionSync: PermissionDecisionSync),\n",
         "", expect=2)
    edit(app_delegate, r"^        (firestoreLocker|permissionDecisionSync)\.init\(\)\n", "", expect=2)

    edit("pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt",
         r"(override suspend fun removeApp\(uuid: Uuid\): Boolean = true\n)[ \t]*override fun init\(\) \{\}\n",
         r"\1")


def remove_core_account() -> None:
    """Remove Core's account: its user record, what synced with it, and the sign-in providers.

    Orb switches every sign-in provider off and has no Firebase, so nobody is ever signed in: the
    user record never loads, nothing is written to it, and the sign-in providers only ever
    answer "no". Their code goes (REMOVED), including Orb's two stand-ins for the Google sign-in
    files, and this unhooks it. Where the record decided something, Orb's answer is what it
    always was: the developer connection needs its LAN setting, the developer token is the
    Rebble one, requests that wanted a Core token go without, and Core's own store reports
    signed out.
    """
    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module, r"^import coredevices\.(database\.UserConfigDao|firestore\.UsersDao|firestore\.UsersDaoImpl)\n",
         "", expect=3)
    edit(util_module, r"^    single \{ UserConfigDao \{ get\(\) \} \}\n", "")
    edit(util_module, r"^    single<UsersDao> \{ UsersDaoImpl\(.*\) \}\n", "")

    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module,
         r"^import coredevices\.(coreapp\.auth\.Real(Apple|Github|Google)AuthUtil"
         r"|util\.auth\.(AppleAuthUtil|GoogleAuthUtil|GitHubAuthUtil|SilentSignIn))\n",
         "", expect=7)
    edit(android_module, r"^    singleOf\(::Real(Google|Apple|Github)AuthUtil\) binds? .*\n", "", expect=3)

    app_delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    edit(app_delegate,
         r"^import (coredevices\.firestore\.UsersDao|coredevices\.pebble\.account\.(FirestoreKnownWatchesSync|PermissionSettingsSync)"
         r"|coredevices\.util\.emailOrNull|dev\.gitlive\.firebase\.(Firebase|auth\.auth))\n",
         "", expect=6)
    edit(app_delegate,
         r"^    private val (usersDao: UsersDao|firestoreKnownWatchesSync: FirestoreKnownWatchesSync"
         r"|permissionSettingsSync: PermissionSettingsSync),\n",
         "", expect=3)
    edit(app_delegate,
         r"^        usersDao\.init\(\)\n"
         r"        GlobalScope\.launch\(Dispatchers\.Default\) \{\n"
         r"            usersDao\.initUserDevToken\(.*\)\n        \}\n"
         r"        GlobalScope\.launch\(Dispatchers\.Default\) \{\n"
         r"            Firebase\.auth\.currentUser\?\.emailOrNull\?\.let \{\n"
         r"                analyticsBackend\.setUser\(email = it\)\n            \}\n        \}\n",
         "")
    edit(app_delegate, r"^        (firestoreKnownWatchesSync|permissionSettingsSync)\.init\(\)\n", "", expect=2)

    account = "pebble/src/commonMain/kotlin/coredevices/pebble/account/PebbleAccount.kt"
    edit(account, r"^import coredevices\.firestore\.UsersDao\n", "")
    edit(account, r"^    private val usersDao: UsersDao,\n", "", expect=2)
    edit(account, r"^        usersDao\.initUserDevToken\(devPortalId\)\n", "")
    edit(account,
         r"(    override suspend fun getDevToken\(\): String\? \{\n)"
         r"        val userConfig = usersDao\.user\.firstOrNull\(\)\n"
         r"        return userConfig\?\.user\?\.rebbleUserToken \?: userConfig\?\.user\?\.pebbleUserToken \?: "
         r"(pebbleAccount\.devToken\.value)\n",
         r"\1        return \2\n")

    pebble_delegate = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleAppDelegate.kt"
    edit(pebble_delegate, r"^import coredevices\.firestore\.UsersDao\n", "")
    edit(pebble_delegate, r"^    private val usersDao: UsersDao,\n", "")
    remove_kotlin_block(pebble_delegate, r"^            GlobalScope\.launch \{(?=\n                usersDao\.loginEvents\.collect \{)")
    edit(pebble_delegate, r"^[ \t]*usersDao\.updateLastConnectedWatch\(watch\.serial\)\n", "")

    watches = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchesScreen.kt"
    edit(watches, r"^import coredevices\.firestore\.UsersDao\n", "")
    edit(watches,
         r"^                val usersDao: UsersDao = koinInject\(\)\n"
         r"                val user by usersDao\.user\.collectAsState\(null\)\n", "")
    edit(watches, r"val canUseDevConnection = user\?\.isAnonymousUser == false \|\| config\.watchConfig\.lanDevConnection",
         "val canUseDevConnection = config.watchConfig.lanDevConnection")

    preview = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt"
    edit(preview, r"^import coredevices\.firestore\.(PebbleUser|UsersDao)\n", "", expect=2)
    remove_kotlin_block(preview, r"^    val usersDao = object : UsersDao \{")
    edit(preview, r"^    single \{ usersDao \} bind UsersDao::class\n", "")

    watch_module = "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt"
    edit(watch_module,
         r"^import coredevices\.pebble\.account\.(FirestoreKnownWatchesDao|FirestoreKnownWatchesSync"
         r"|RealFirestoreKnownWatchesSync|PermissionSettingsSync)\n",
         "", expect=4)
    edit(watch_module, r"^    single \{ FirestoreKnownWatchesDao \{ get\(\) \} \}\n", "")
    edit(watch_module, r"^    singleOf\(::RealFirestoreKnownWatchesSync\) bind FirestoreKnownWatchesSync::class\n", "")
    edit(watch_module, r"^    singleOf\(::PermissionSettingsSync\)\n", "")

    web_services = "pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt"
    edit(web_services, r"^import dev\.gitlive\.firebase\.(Firebase|auth\.auth)\n", "", expect=2)
    edit(web_services,
         r"HttpClientAuthType\.Core -> try \{\n"
         r"                Firebase\.auth\.currentUser\?\.getIdToken\(false\)\n"
         r"            \} catch \(e: Exception\) \{\n"
         r'                logger\.e\(e\) \{ "Network error fetching Firebase token" \}\n'
         r"                null\n            \}\n",
         "HttpClientAuthType.Core -> null\n")
    appstore = "pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt"
    edit(appstore, r"^import dev\.gitlive\.firebase\.(Firebase|auth\.auth)\n", "", expect=2)
    edit(appstore, r"(            PEBBLE_FEED_URL -> )\{\n                Firebase\.auth\.currentUser != null\n            \}\n",
         r"\1false\n")

    bug_report = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt"
    edit(bug_report, r"^import (coredevices\.util\.emailOrNull|dev\.gitlive\.firebase\.(Firebase|auth\.FirebaseUser|auth\.auth))\n",
         "", expect=(3, 4))
    remove_kotlin_block(bug_report, r"^fun FirebaseUser\?\.toUserProps\(\): UserProps\? =\n    this\?\.let \{")
    edit(bug_report,
         r"^        val user by Firebase\.auth\.authStateChanged\.map \{\n(?:.*\n){3}"
         r"            \.collectAsState\(Firebase\.auth\.currentUser\.toUserProps\(\)\)\n",
         "")

    # Only Rebble supports account hearts; Core store browsing stays public.

    replace_literal(web_services,
                    'getAllSources(enabledOnly = true).forEach { source ->', 'getAllSources(enabledOnly = true).filter { it.isRebbleFeed() }.forEach { source ->')
    edit(web_services,
         r"^    (?:suspend fun fetchUsersMeCore\(\): CoreUsersMe\?|override suspend fun fetchUsersMeCore\(\): CoreUsersMe\? = .*|Core,)\n", '', expect=3)
    replace_literal(web_services,
                    'HttpClientAuthType.Pebble, HttpClientAuthType.Core -> true', 'HttpClientAuthType.Pebble -> true')
    edit(web_services, r"^            HttpClientAuthType\.Core -> null\n", '')

    remove_kotlin_block(web_services, r"^@Serializable\ndata class CoreUsersMe\(")
    edit(appstore,
         r"^            PEBBLE_FEED_URL -> \{\n                (?:pebbleHttpClient\.(?:post|delete)\(.*|pebbleWebServices\.fetchUsersMeCore\(\)\?\.votedIds)\n            \}\n", '', expect=3)
    replace_literal(appstore, 'import coredevices.pebble.services.PebbleHttpClient.Companion.delete\n', '')

    replace_literal(preview, 'import coredevices.pebble.services.CoreUsersMe\n', '')
    replace_literal(preview, '        override suspend fun fetchUsersMeCore(): CoreUsersMe? = null\n', '')


def remove_firebase() -> None:
    """Remove the last uses of Firebase, so Orb builds without it or a stand-in for it.

    What was left needed a signed-in Core user, and there never is one: the Firestore setup
    nothing reads any more, the sign-in token libpebble was handed (always empty), Core's hosted
    OAuth broker for phone plugins (every call failed for want of a user) and an unused client
    for Core's firmware server. The Firebase libraries leave the build (DROPPED_ACCESSORS), and
    Orb's stand-in module for them is gone.
    """
    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    remove_kotlin_block(util_module, r"^    single<FirebaseFirestore> \{")
    edit(util_module,
         r"^import dev\.gitlive\.firebase\.(Firebase|firestore\.(FirebaseFirestore|FirebaseFirestoreSettings"
         r"|firestore|firestoreSettings|persistentCacheSettings))\n",
         "", expect=6)

    watch_module = "pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt"
    # libpebble's sign-in token for Core's services: always empty without a Core user. The
    # plugin OAuth broker is left out, so plugins see no OAuth bridge instead of a failing one.
    edit(watch_module,
         r"flow \{ emitAll\(Firebase\.auth\.idTokenChanged\) \}\n"
         r"[ \t]*\.map \{ try \{ it\?\.getIdToken\(false\) \}.*\n"
         r"[ \t]*\.stateIn\(GlobalScope, started = SharingStarted\.Lazily, initialValue = null\),\n"
         r"([ \t]*get\(\),\n[ \t]*get\(\),\n)[ \t]*get\(\),\n",
         r"\1")
    edit(watch_module, r"^    singleOf\(::HostedPluginOAuthApi\) bind PluginOAuthApi::class\n", "")
    edit(watch_module,
         r"^import (coredevices\.pebble\.plugin\.HostedPluginOAuthApi|dev\.gitlive\.firebase\.(Firebase|auth\.auth)"
         r"|io\.rebble\.libpebblecommon\.plugin\.PluginOAuthApi)\n",
         "", expect=4)

    remove_kotlin_block(
        "util/src/commonMain/kotlin/coredevices/api/EngDashOtaApi.kt",
        r"^class EngDashOtaApiImpl\(\n    private val baseUrl: String = BASE_URL,\n"
        r"\) : ApiClient\(CommonBuildKonfig\.USER_AGENT_VERSION\), EngDashOtaApi \{")

    # There is only the opt-in LAN transport; disabling it cancels the active server.

    lib_pebble_module = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/di/LibPebbleModule.kt'
    lib_pebble = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/LibPebble.kt'
    dev_connection_manager = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/devconnection/DevConnectionManager.kt'
    pebble_device = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/PebbleDevice.kt'
    packets = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/devconnection/packets.kt'
    js_plugin_factory = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/plugin/JsPluginFactory.kt'
    js_plugin = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/plugin/JsPlugin.kt'
    plugin_manifest = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/plugin/PluginManifest.kt'
    eng_dash_ota = 'pebble/src/commonMain/kotlin/coredevices/pebble/services/EngDashOta.kt'

    edit(lib_pebble_module, r"^import io\.rebble\.libpebblecommon\.plugin\.PluginOAuthApi\n", '')
    edit(lib_pebble_module,
         r"^    (?:        )?(?:proxyTokenProvider: StateFlow<String\?>,|pluginOAuthApi: PluginOAuthApi\? = null,)\n", '', expect=2)
    edit(lib_pebble, r"^import io\.rebble\.libpebblecommon\.plugin\.PluginOAuthApi\n", '')

    edit(lib_pebble,
         r"^    (?:        )?(?:proxyTokenProvider: StateFlow<String\?>,|pluginOAuthApi: PluginOAuthApi\? = null,)\n", '', expect=2)
    replace_literal(lib_pebble, ', proxyTokenProvider, transcriptionProvider', ', transcriptionProvider')

    replace_literal(lib_pebble, ', injectedPKJSHttpInterceptors, pluginOAuthApi)', ', injectedPKJSHttpInterceptors)')
    replace_literal(lib_pebble_module,
                    'import io.rebble.libpebblecommon.connection.devconnection.DevConnectionCloudpebbleProxy\n', '')
    remove_kotlin_block(lib_pebble_module,
                    r"^                single \{(?=\n                    DevConnectionCloudpebbleProxy\()")
    replace_literal(lib_pebble_module,
                    '                                    get<DevConnectionCloudpebbleProxy>()', '                                    null')
    replace_literal(lib_pebble_module, ', pluginOAuthApi) }', ') }')

    replace_literal(dev_connection_manager, 'Flow<DevConnectionTransport>,', 'Flow<DevConnectionTransport?>,')
    replace_literal(dev_connection_manager, '    private val lanServer: DevConnectionServer,\n', '')

    replace_literal(lib_pebble_module, '                            lanServer = get<DevConnectionServer>(),\n', '')
    replace_literal(dev_connection_manager,
                    '/** Watches with an active dev connection (value = forceLan), resumed on reconnection. */', '/** Watches with an active LAN developer connection, resumed on reconnection. */')
    replace_literal(dev_connection_manager,
                    'MutableStateFlow<Map<PebbleIdentifier, Boolean>>(emptyMap())', 'MutableStateFlow<Set<PebbleIdentifier>>(emptySet())')
    replace_literal(dev_connection_manager,
                    '        val forceLan = resumer.active.value[identifier] ?: return\n        start(forceLan)', '        if (identifier in resumer.active.value) start()')
    replace_literal(dev_connection_manager, 'startDevConnection(forceLan: Boolean)', 'startDevConnection()')

    replace_literal(dev_connection_manager, 'it + (identifier to forceLan)', 'it + identifier')
    replace_literal(dev_connection_manager, '        start(forceLan)', '        start()')

    replace_literal(dev_connection_manager, 'private fun start(forceLan: Boolean)', 'private fun start()')
    replace_literal(dev_connection_manager,
                    '        // Must never complete: onCompletion below stops the transport, so a finite flow would\n        // tear the server down as soon as it emitted.\n        val transport = if (forceLan) MutableStateFlow(lanServer) else transport\n', '')
    replace_literal(dev_connection_manager,
                    '                    last = it\n                    it.start',
                    '                    last = it\n'
                    '                    if (it == null) {\n'
                    '                        resumer.active.update { active -> active - identifier }\n'
                    '                        return@collectLatest\n'
                    '                    }\n'
                    '                    it.start')
    replace_literal(dev_connection_manager,
                    '                transport.onCompletion {\n                    last?.stop()\n                }.collectLatest {', '                transport.collectLatest {')
    replace_literal(dev_connection_manager, 'import kotlinx.coroutines.flow.onCompletion\n', '')

    replace_literal(pebble_device,
                    '        /** [forceLan] ignores the lanDevConnection config and always uses the LAN server. */\n', '')
    replace_literal(pebble_device, 'startDevConnection(forceLan: Boolean = false)', 'startDevConnection()')

    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/FakeLibPebble.kt',
                    'startDevConnection(forceLan: Boolean)', 'startDevConnection()', expect=2)
    remove_kotlin_block(packets, r"^class ProxyAuthenticationMessage\(\n    token: String\n\): StructMappable\(\) \{")

    remove_kotlin_block(packets,
                    r"^class ProxyAuthenticationMessageV2\(\n    token: String\n\): StructMappable\(\) \{")
    edit(packets, r"^import io\.rebble\.libpebblecommon\.structmapper\.S(?:LongString|String)\n", '', expect=2)

    edit('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/devconnection/ServerMessageType.kt',
         r"^    ProxyAuthentication(?:V2)?\(.*\n", '', expect=2)
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/devconnection/ClientMessageType.kt',
                    '    //ProxyAuthenticationRequest(0x09),\n', '')
    replace_literal(js_plugin_factory, '    private val oauthApi: PluginOAuthApi? = null,\n', '')

    replace_literal(js_plugin, '    private val oauthApi: PluginOAuthApi? = null,\n', '')
    replace_literal(js_plugin_factory, '        oauthApi = oauthApi,\n', '')

    replace_literal(js_plugin,
                    '    /** Host-side hosted OAuth, when available. Only reachable by plugins that declare a connector. */\n', '')
    replace_literal(js_plugin,
                    '    /** Wired only when the plugin declares an `oauth` connector and the host has an OAuth API. */\n    private val oauth = oauthApi?.takeIf { manifest.oauth.isNotEmpty() }\n', '')
    remove_kotlin_block(js_plugin, r"^        val oauthBridge = oauth\?\.let \{")

    replace_literal(js_plugin, ', oauthBridge,', ',', expect=2)
    replace_literal(js_plugin, '        private val oauthBridge: PluginOAuthJsBridge?,\n', '')

    replace_literal(js_plugin, '            oauthBridge?.let { engine.eval(PluginOAuthJsBridge.INSTALL_JS) }\n', '')
    replace_literal(js_plugin, '            oauthBridge?.close()\n', '')

    edit(plugin_manifest,
         r"^    /\*\*\n     \* Hosted OAuth connectors.*\n(?:     \*.*\n)*?     \*/\n    val oauth: Map<String, OAuthConnector> = emptyMap\(\),\n", '')
    edit(plugin_manifest,
         r"^/\*\*\n \* A declared hosted-OAuth connector.*\n(?: \*.*\n)*? \*/\n@Serializable\nclass OAuthConnector\n", '')
    replace_literal(eng_dash_ota, 'import coredevices.pebble.services.Memfault.Companion.serialForMemfault\n', '')

    replace_literal(eng_dash_ota, '                deviceSerial = watch.serialForMemfault(),\n', '')
    edit(eng_dash_ota,
         r"^/\*\*\n \* OTA update check against eng-dash.*\n \* Core devices.*\n \*/", "/** Adapts Orb's firmware source to the watch update checker. */")
    replace_literal(eng_dash_ota, 'Error checking for updates from eng-dash:', 'Error checking for firmware updates:')

    edit('util/src/commonMain/kotlin/coredevices/api/EngDashOtaApi.kt',
         r"^        (?:deviceSerial: String,|deviceMac: String\? = null)\n", '', expect=2)
    replace_literal(dev_connection_manager,
                    'import kotlinx.coroutines.flow.collectLatest\n', 'import kotlinx.coroutines.flow.collectLatest\nimport kotlinx.coroutines.flow.transformWhile\n')
    replace_literal(dev_connection_manager,
                    '                transport.collectLatest {', '                transport.transformWhile { next ->\n                    emit(next)\n                    next != null\n                }.collectLatest {')
    replace_literal(lib_pebble_module,
                    'import io.rebble.libpebblecommon.connection.devconnection.CloudpebbleProxyProtocolVersion\n', '')


def remove_analytics() -> None:
    """Remove Core's app analytics.

    Events, heartbeat counters and watch-connection states were recorded and summarised for an
    analytics backend Orb never had (its Android backend was Orb's do-nothing stand-in), so the
    work only filled the phone's database. The analytics code goes (REMOVED), with Orb's
    stand-in, and so do the database accessors of the three telemetry tables, whose tables
    drop_core_telemetry_tables() deletes.
    """
    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module, r"^import coredevices\.analytics\.createAndroidAnalytics\n", "")
    edit(android_module, r"^    single \{ createAndroidAnalytics\(get\(\)\) \}\n", "")

    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module, r"^import coredevices\.analytics\.(CoreAnalytics|HeartbeatMetricsSource|RealCoreAnalytics)\n", "", expect=3)
    edit(util_module, r"^    single \{ RealCoreAnalytics\(.*\) \} bind CoreAnalytics::class\n", "")
    edit(util_module,
         r"^    single \{ get<CoreDatabase>\(\)\.(analyticsDao|memfaultChunkDao|analyticsHeartbeatDao)\(\) \}\n", "", expect=3)

    database = "util/src/commonMain/kotlin/coredevices/database"
    edit(f"{database}/CoreDatabase.kt",
         r"^    abstract fun (analyticsDao\(\): HeartbeatStateDao|memfaultChunkDao\(\): MemfaultChunkDao"
         r"|analyticsHeartbeatDao\(\): AnalyticsHeartbeatDao)\n",
         "", expect=3)

    app_delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    edit(app_delegate, r"^import coredevices\.analytics\.(AnalyticsBackend|CoreAnalytics|setUser)\n", "", expect=3)
    edit(app_delegate, r"^    private val (analyticsBackend: AnalyticsBackend|coreAnalytics: CoreAnalytics),\n", "", expect=2)
    edit(app_delegate,
         r"^                    add\(scope\.launch \{\n                        coreAnalytics\.processHeartbeat\(\)\n"
         r"                    \}\)\n", "")

    firmware_check = "pebble/src/commonMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateCheck.kt"
    edit(firmware_check, r"^import coredevices\.analytics\.CoreAnalytics\n", "")
    edit(firmware_check, r"^    private val coreAnalytics: CoreAnalytics,\n", "")

    asr = "pebble/src/commonMain/kotlin/coredevices/pebble/services/RebbleAsrTranscription.kt"
    edit(asr,
         r"^import coredevices\.(analytics\.CoreAnalytics|util\.transcription\.logTranscription(Failure|Success))\n",
         "", expect=3)
    edit(asr, r"^    private val analytics: CoreAnalytics,\n", "")
    edit(asr,
         r"^        val result = transcribeInner\(encoderInfo, audioFrames\)\n"
         r"        if \(result is TranscriptionResult\.Success && result\.words\.isNotEmpty\(\)\) \{\n"
         r"(?:.*\n){3}        \}\n        return result\n",
         "        return transcribeInner(encoderInfo, audioFrames)\n")
    remove_kotlin_block(asr, r"^private fun TranscriptionResult\.failureReason\(\): String = when \(this\) \{")

    deep_links = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt"
    edit(deep_links, r"^import coredevices\.analytics\.CoreAnalytics\n", "")
    edit(deep_links, r"^    private val analytics: CoreAnalytics,\n", "")
    edit(deep_links, r'^[ \t]*analytics\.logEvent\("rebble\.logged-in"\)\n', "")

    delegate = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleAppDelegate.kt"
    edit(delegate,
         r"^import coredevices\.analytics\.(CoreAnalytics|heartbeatWatchConnectGoalName|heartbeatWatchConnectedName)\n",
         "", expect=3)
    edit(delegate, r"^    private val analytics: CoreAnalytics,\n", "")
    for flow in ("analyticsEvents", "heartbeatCounterIncrements"):
        remove_kotlin_block(delegate, rf"^            GlobalScope\.launch \{{(?=\n                libPebble\.{flow}\.collect \{{)")
    remove_kotlin_block(delegate,
                        r"^                    watches\.groupBy \{ it\.watchType\(\) \}\.forEach \{(?= \(watchType, watches\) ->)")
    remove_kotlin_block(delegate,
                        r"^            GlobalScope\.launch \{(?=\n                libPebble\.watches\.collect \{ watches ->\n"
                        r"                    val connected = watches\.filterIsInstance<CommonConnectedDevice>\(\)\.firstOrNull\(\))")


def remove_sync_manager() -> None:
    """Remove Core's queue of background sync tasks.

    It retries queued work through WorkManager, but in Orb no task type has a handler and nothing
    queues a task, so it only ever resumed an empty queue. The queue code goes (REMOVED), with its
    database accessor; drop_core_telemetry_tables() deletes its table. Core's periodic
    background sync (SyncWorker) is separate and unchanged.
    """
    edit("util/src/commonMain/kotlin/coredevices/database/CoreDatabase.kt",
         r"^    abstract fun syncTaskDao\(\): SyncTaskDao\n", "")

    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module, r"^import coredevices\.(database\.SyncTaskDao|util\.sync\.SyncHandler|util\.sync\.SyncManager)\n",
         "", expect=3)
    edit(util_module, r"^    single \{ get<CoreDatabase>\(\)\.syncTaskDao\(\) \}\n", "")
    edit(util_module, r"^    single \{ SyncManager\(.*\n", "")

    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module, r"^import coredevices\.util\.sync\.(AndroidSyncScheduler|SyncManager|SyncScheduler)\n", "", expect=3)
    edit(android_module, r"^    single<SyncScheduler> \{ AndroidSyncScheduler\(.*\n", "")

    app_delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    edit(app_delegate, r"^import coredevices\.util\.sync\.SyncManager\n", "")
    edit(app_delegate, r"^    private val syncManager: SyncManager,\n", "")
    edit(app_delegate,
         r"^        GlobalScope\.launch\(Dispatchers\.Default\) \{\n            syncManager\.resume\(\)\n        \}\n", "")


def remove_release_additions() -> None:
    """Unhook 2.0.0's account linkage, exit reporting and voice report upload.

    Keep local exit logging and Core's startup/exception fixes. Crash classification served
    only the removed persistent queue, so its platform API goes rather than returning a stub.
    """
    app = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainApplication.kt"
    remove_kotlin_block(app, r"^                if \(info\.timestamp > lastReported && info\.processName == packageName\) \{")
    edit(app, r"^            // First run: only report the most recent exit, not the whole history\.\n"
         r"            val lastReported = .*\n(?:                \?: .*\n){2}", "")
    edit(app, r"^            reasons\.maxOfOrNull.*KEY_LAST_REPORTED_EXIT_TIMESTAMP.*\n", "")
    edit(app, r"^private const val KEY_LAST_REPORTED_EXIT_TIMESTAMP = .*\n", "")
    edit(app, r"^    private val (coreAnalytics: CoreAnalytics|settings: Settings) by inject\(\)\n", "", expect=2)
    edit(app, r"^import (coredevices\.analytics\.CoreAnalytics|com\.russhwolf\.settings\.(Settings|set))\n", "", expect=3)
    edit(app, r"^        // Cactus telemetry is initialized via CommonAppDelegate\.initCactus\(\)\n", "")

    delegate = "composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt"
    remove_kotlin_block(delegate, r"^        GlobalScope\.launch\(Dispatchers\.Default\) \{(?=\n            Firebase\.auth\.authStateChanged\.collect)")
    edit(delegate, r"^import coredevices\.analytics\.PROP_FIREBASE_UID\n", "")
    module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(module, r"^import coredevices\.ring\.agent\.builtin_servlets\.bugreport\.BugReporter\n", "")
    edit(module, r"^    single \{ BugReporter\(get<BugReportProcessor>\(\)::newVoiceBugReport\) \}\n", "")
    edit("util/src/commonMain/kotlin/coredevices/api/EngDashOtaApi.kt",
         r"^import (coredevices\.util\.CommonBuildKonfig|io\.ktor\..*|kotlinx\.io\.IOException)\n", "", expect=8)
    screen = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/BugReportScreen.kt"
    edit(screen, r"^expect fun isThirdPartyTest\(\): Boolean\n", "")
    edit(screen, r"^            if \(isThirdPartyTest\(\)\) return\n", "")

    platform = "util/src/commonMain/kotlin/coredevices/util/Platform.kt"
    edit(platform, r"^    /\*\* Whether the previous run of the app ended in a crash, as opposed to being killed by the user or the OS\. \*/\n"
         r"    val previousRunCrashed: Boolean get\(\) = false\n", "")
    android = "util/src/androidMain/kotlin/coredevices/util/Platform.android.kt"
    remove_kotlin_block(android, r"^    override val previousRunCrashed: Boolean\n        get\(\) \{")
    edit(android, r"^import (android\.app\.(ActivityManager|ApplicationExitInfo)|dev\.gitlive\.firebase\.(Firebase|crashlytics\.crashlytics))\n", "", expect=4)
    ios = "util/src/iosMain/kotlin/coredevices/util/Platform.ios.kt"
    edit(ios, r"^    override val previousRunCrashed: Boolean\n        get\(\) = Firebase\.crashlytics\.didCrashOnPreviousExecution\(\)\n", "")
    edit(ios, r"^import dev\.gitlive\.firebase\.(Firebase|crashlytics\.crashlytics)\n", "", expect=2)
    edit("androidApp/src/main/AndroidManifest.xml",
         r'^        <meta-data\n            android:name="com\.google\.android\.geo\.API_KEY"\n            android:value="[^"]+" />\n', "")

    edit("settings.gradle.kts", r'^include\(":toolschema(?:gen|annotations)"\)\n', "", expect=2)
    # Remove native host build wiring as well as its source (REMOVED).
    gradle = "composeApp/build.gradle.kts"
    edit(gradle, r"^    alias\(libs\.plugins\.nativeCocoaPods\)\n", "")
    remove_kotlin_block(gradle, r'^    tasks\.register\("fixXcodeProject"\) \{')
    remove_kotlin_block(gradle, r'^    tasks\.named\("podInstall"\) \{')
    remove_kotlin_block(gradle, r"^    cocoapods \{")
    edit(gradle, r"^    // Make xcode invoke gradle from the right place\n", "")
    edit(gradle, r"^            // The binary FirebaseFirestoreInternal is static, so its C deps must be linked into\n"
         r"            // every binary that pulls in Firestore, not just the pod framework\.\n"
         r'            val grpcSlice = if \(target\.konanTarget\.name\.contains\("simulator"\)\) \{\n'
         r'                "ios-arm64_x86_64-simulator"\n            \} else \{\n'
         r'                "ios-arm64"\n            \}\n', "")
    remove_kotlin_block(gradle, r"^            listOf\(\n                \"FirebaseFirestoreGRPCCoreBinary/[^\n]*\n"
                        r"(?:.*\n){3}            \)\.forEach \{")

    # Drop dormant endpoint/credential configuration and catalog entries after their users go.
    gradle = "util/build.gradle.kts"
    edit(gradle, r'^        buildConfigField\(FieldSpec\.Type\.(?:STRING|BOOLEAN), "(?:BUG_URL|TOKEN_URL|MIXPANEL_TOKEN|WISPR_AUTH_URL|KIRINKI_URL|MEMFAULT_TOKEN|GOOGLE_\w+|APPLE_\w+|GITHUB_\w+|CACTUS_\w+)"[^\n]*\n', "", expect=17)
    remove_kotlin_block(gradle, r"^val properties = Properties\(\)\.apply \{")
    remove_kotlin_block(gradle, r"^fun gradleStringPropOrNull\(")
    edit(gradle, r"^fun gradleBooleanProp\(name: String, default: Boolean\): Boolean =\n    gradleStringPropOrNull\(name\)\?\.let \{ it == \"true\" \} \?: default\n", "")
    edit(gradle, r"^import java\.util\.Properties\n", "")
    delete_lines(gradle_files(), r"// gitlive's compile variant declares com\.google\.firebase:", at_least=2)
    edit("androidApp/build.gradle.kts", r"^ +// Crashlytics regenerates a mapping-id resource every build\n", "")
    edit("gradle.properties", r"^(?:bugUrl|tokenUrl|githubClientId|githubClientSecret|mixpanelToken|wisprAuthUrl|kirinkiUrl|memfaultToken|googleClientId|googleAuthEnabled|appleAuthEnabled|githubAuthEnabled|cactusProKey)=[^\n]*(?:\n|$)", "", expect=13)
    catalog = "gradle/libs.versions.toml"
    edit(catalog, r"^(?:googleServices|firebase[\w-]*|gms-(?:auth|location)|googleId|play-update(?:-ktx)?|crashkios|kmpnotifier|mixpanel-android|identity-google) = .*\n", "", expect=28)
    edit(catalog, r"^# (?:22\.x removed GoogleSignIn.*|Ahead of the BOM firebase-kotlin.*|NEVER downgrade below 34\.x.*|2\.x pulls firebase-ios-sdk.*)\n", "", expect=4)

    # CalendarProvider is a platform API. Keep its ownership check without a provider preference.
    calendar = "libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/calendar/AndroidSystemCalendar.kt"
    edit(calendar, r'^private const val GOOGLE_ACCOUNT_TYPE = "com\.google"\n', "")
    replace_literal(calendar, "The account's own primary calendar (ownerAccount == accountName), preferring a Google one:\n     * Samsung's local \"My calendar\" also matches the ownership rule and has the lowest _ID.",
                    "The first account-owned primary calendar (ownerAccount == accountName).")
    edit(calendar, r"^                    val type = cursor\.getNullableColumnIndex\(CalendarContract\.Calendars\.ACCOUNT_TYPE\)\n                        \?\.let \{ cursor\.getString\(it\) \}\n                    if \(type == GOOGLE_ACCOUNT_TYPE\) return@use id\n", "")
    replace_literal("pebble/src/commonMain/kotlin/coredevices/pebble/ui/CalendarScreen.kt",
                    "Is sharing enabled in the Google Calendar app? See: Settings -> General -> Share Google Calendar data with other apps",
                    "Check that your calendar app allows other apps to read its calendars.")
    replace_literal('composeApp/build.gradle.kts', '            implementation(libs.androidx.credentials)\n', '')

    edit(catalog,
         r"^(?:androidx-credentials|mcp|glance|kmpMaps|modelcontextprotocol-(?:client|core|server)|androidx-glance(?:-material3)?|swmansion-kmpMaps-core|cactus-lm-weights) = .*\n", '', expect=12)
    replace_literal(catalog, '# Cactus model checkpoints\n', '')

    replace_literal('composeApp/build.gradle.kts',
                    '        commonTest.dependencies {\n            implementation(libs.kotlin.test)\n',
                    '        commonTest.dependencies {\n            implementation(libs.kotlin.test)\n            implementation(libs.settings.test)\n')


def remove_library_telemetry() -> None:
    """Remove libpebble's unused event bus and plugin heartbeat counters.

    Per-app network usage and action history are local user-visible features and stay.
    System data logging still acknowledges watch batches, discarding non-health data.
    """
    base = "libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon"
    plugin = f"{base}/plugin/PluginClient.kt"
    edit(plugin, r"^import io\.rebble\.libpebblecommon\.LibPebbleAnalytics\n", "")
    remove_kotlin_block(plugin, r"^object PluginHeartbeatCounters \{")
    remove_kotlin_block(plugin, r"^    private fun count\(")
    edit(plugin, r"^    private val analytics: LibPebbleAnalytics,\n", "")
    edit(plugin, r"^        count\(caller, target\.pluginUuid, PluginHeartbeatCounters\..*\n", "", expect=2)
    replace_literal(plugin, "never prompts, isn't counted.", "never prompts.")

    module = f"{base}/di/LibPebbleModule.kt"
    edit(module, r"^import io\.rebble\.libpebblecommon\.(LibPebbleAnalytics|RealLibPebbleAnalytics|connection\.(AnalyticsEvents|ConnectionFailureHandler|RealConnectionFailureHandler))\n", "", expect=5)
    remove_kotlin_block(module, r"^interface ConnectionAnalyticsLogger \{")
    remove_kotlin_block(module, r"^class RealConnectionAnalyticsLogger\(")
    remove_kotlin_block(module, r"^fun LibPebbleAnalytics\.logWatchEvent\(")
    edit(module, r"^    (?:override )?val analyticsLogger: ConnectionAnalyticsLogger.*\n", "", expect=2)
    edit(module, r"^                singleOf\(::RealConnectionFailureHandler\) bind ConnectionFailureHandler::class\n", "")
    edit(module, r"^                    scopedOf\(::RealConnectionAnalyticsLogger\) bind ConnectionAnalyticsLogger::class\n", "")
    edit(module, r"^                singleOf\(::RealLibPebbleAnalytics\) binds arrayOf\(\n(?:.*\n){2}                \)\n", "")
    # LibPebble3 loses its analytics parameter below, so its positional call loses one get().
    edit(module, r"^(                    LibPebble3\(\n)                        get\(\),\n", r"\1")

    lib = f"{base}/connection/LibPebble.kt"
    replace_literal(lib, "Contacts, AnalyticsEvents, HealthApi", "Contacts, HealthApi")
    edit(lib, r"^data class AnalyticsEvent\(\n(?:    .*\n){2}\)\n", "")
    remove_kotlin_block(lib, r"^interface AnalyticsEvents \{")
    edit(lib, r"^    private val analytics: AnalyticsEvents,\n", "")
    replace_literal(lib, "Contacts by contacts, AnalyticsEvents by analytics,", "Contacts by contacts,")
    edit(lib, r"^    fun upload(?:MemfaultChunk|AnalyticsHeartbeat)\(.*\n", "", expect=2)
    fake = f"{base}/connection/FakeLibPebble.kt"
    edit(fake, r"^    override val (?:analyticsEvents: Flow<AnalyticsEvent>|heartbeatCounterIncrements: Flow<String>)\n        get\(\) = flow \{ \}\n", "", expect=2)
    manager = f"{base}/connection/WatchManager.kt"
    edit(manager, r"^import io\.rebble\.libpebblecommon\.(LibPebbleAnalytics|di\.logWatchEvent)\n", "", expect=2)
    edit(manager, r"^    private val (?:analytics: LibPebbleAnalytics|connectionFailureHandler: ConnectionFailureHandler),\n", "", expect=2)
    remove_kotlin_block(manager, r"^    private fun Watch\.logAnalyticsEvent\(")
    pairing = f"{base}/connection/bt/ble/pebble/PebblePairing.kt"
    edit(pairing, r"^import io\.rebble\.libpebblecommon\.di\.ConnectionAnalyticsLogger\n", "")
    edit(pairing, r"^// *analytics\.logEvent\(.*\n", "", expect=3)

    datalogging = f"{base}/datalogging/Datalogging.kt"
    remove_kotlin_block(datalogging, r"^            // Handle system-app datalogging tags\n            when \(tag\) \{")
    remove_kotlin_block(datalogging, r"^    companion object \{")
    remove_kotlin_block(datalogging, r"^class MemfaultChunk : StructMappable\(\) \{")
    edit(datalogging, r"^    private val webServices: WebServices,\n", "")
    edit(datalogging, r"^import io\.rebble\.libpebblecommon\.(connection\.WebServices|structmapper\.(SBytes|SUInt|StructMappable)|util\.(DataBuffer|Endian))\n", "", expect=6)
    tests = "libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/plugin/PluginClientTest.kt"
    edit(tests, r"^import io\.rebble\.libpebblecommon\.LibPebbleAnalytics\n", "")
    remove_kotlin_block(tests, r"^private class CountingAnalytics : LibPebbleAnalytics \{")
    edit(tests, r"^    private val analytics = CountingAnalytics\(\)\n", "")
    replace_literal(tests, "running, analytics, logs)", "running, logs)")
    for method in ("appInvocationsAreCountedSeparately", "readingCountsAnObservation"):
        remove_kotlin_block(tests, rf"^    @Test\n    fun {method}\(\) = runTest \{{")
    edit(tests, r"^        assertEquals\(.*analytics\.counters\)\n", "", expect=3)
    replace_literal(tests, "theHostInvokesWithoutCallerPermissionsAndIsCounted", "theHostInvokesWithoutCallerPermissions")
    replace_literal(tests, "aProbeNeverPromptsAndIsNotCounted", "aProbeNeverPrompts")
    tests = "libpebble3/src/androidHostTest/kotlin/io/rebble/libpebblecommon/connection/WatchManagerTest.kt"
    edit(tests, r"^import io\.rebble\.libpebblecommon\.(LibPebbleAnalytics|di\.ConnectionAnalyticsLogger)\n", "", expect=2)
    for variable, interface in (("analyticsLogger", "ConnectionAnalyticsLogger"),
                                ("connectionFailureHandler", "ConnectionFailureHandler"),
                                ("analytics", "LibPebbleAnalytics")):
        remove_kotlin_block(tests, rf"^        val {variable} = object : {interface} \{{")
    edit(tests, r"^        override val analyticsLogger: ConnectionAnalyticsLogger,\n", "")
    edit(tests, r"^ +(?:analyticsLogger|connectionFailureHandler|analytics) = \w+,\n", "", expect=3)
    for method in ("uploadMemfaultChunk", "uploadAnalyticsHeartbeat"):
        remove_kotlin_block(tests, rf"^        override fun {method}\(")


def remove_dead_leftovers() -> None:
    """Remove code that nothing calls any more (REMOVED), found with R8's list of unused classes.

    - Message types of the removed cloud speech service, and an unused OAuth client.
    - Core's OAuth integrations (they served the removed ring's apps): nothing asks for the
      launcher, so the redirect handler only swallowed links whose host is "oauth". Such links now
      reach the normal link handling, which ignores them.
    - The persistent task queue behind the removed telemetry uploads.
    - A null speech service, the Firestore watch record, the Firestore user config record and an
      unused permission helper.
    """
    android_module = "composeApp/src/androidMain/kotlin/coredevices/coreapp/di/androidDefaultModule.kt"
    edit(android_module, r"^import coredevices\.util\.integrations\.(AndroidOAuthLauncher|OAuthLauncher)\n", "", expect=2)
    edit(android_module, r"^    singleOf\(::AndroidOAuthLauncher\) bind OAuthLauncher::class\n", "")
    util_module = "composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt"
    edit(util_module, r"^import coredevices\.util\.OAuthRedirectHandler\n", "")
    edit(util_module, r"^    singleOf\(::OAuthRedirectHandler\)\n", "")

    main_activity = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainActivity.kt"
    edit(main_activity, r"^import coredevices\.util\.OAuthRedirectHandler\n", "")
    edit(main_activity, r"^    private val oAuthRedirectHandler: OAuthRedirectHandler by inject\(\)\n", "")
    # Its body always runs now.
    unwrap_kotlin_block(main_activity, "        if (!oAuthRedirectHandler.handleOAuthRedirect(uri)) {\n")

    # Android posts the real notifications and PendingIntents directly; the watch sink is empty.

    permission_request_notifier = 'pebble/src/commonMain/kotlin/coredevices/pebble/permissions/PermissionRequestNotifier.kt'
    firmware_update_ui_tracker = 'pebble/src/commonMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateUiTracker.kt'
    common_app_delegate = 'composeApp/src/commonMain/kotlin/coredevices/coreapp/CommonAppDelegate.kt'
    pebble_app_delegate = 'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleAppDelegate.kt'
    platform_android = 'util/src/androidMain/kotlin/coredevices/util/Platform.android.kt'
    platform = 'util/src/commonMain/kotlin/coredevices/util/Platform.kt'
    health_records = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/health/HealthRecords.kt'
    health = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/health/Health.kt'

    edit(permission_request_notifier,
         r"^import coredevices\.util\.(?:WatchNotifier|WatchNotificationAction|setWatchNotificationActionHandler)\n", '', expect=3)
    replace_literal(permission_request_notifier, '    private val watchNotifier: WatchNotifier,\n', '')

    edit(firmware_update_ui_tracker,
         r"^import coredevices\.util\.(?:WatchNotifier|WatchNotificationAction|setWatchNotificationActionHandler)\n", '', expect=2)
    replace_literal(firmware_update_ui_tracker, '    private val watchNotifier: WatchNotifier,\n', '')

    edit(common_app_delegate,
         r"^import coredevices\.util\.(?:WatchNotifier|WatchNotificationAction|setWatchNotificationActionHandler)\n", '')
    replace_literal(common_app_delegate, '    private val watchNotifier: WatchNotifier,\n', '')

    remove_kotlin_block(permission_request_notifier,
                    r"^    /\*\* Before the watch connects.*\*/\n    fun registerWatchActions\(")
    replace_literal(permission_request_notifier, '                    watchNotifier.remove(watchKey(appUuid))\n', '')

    replace_literal(permission_request_notifier, 'import kotlinx.serialization.json.Json\n', '')

    edit(permission_request_notifier,
         r"^        private fun watchKey\(.*\n\n        private fun watchActionType\(.*\n", '')
    remove_kotlin_block(permission_request_notifier, r"^        private fun decodeWatchActionData\(")

    replace_literal(firmware_update_ui_tracker,
                    '        val actions = if (showUpdateAction) {\n            listOf(WatchNotificationAction("Update Now", FIRMWARE_UPDATE_NOW_WATCH_ACTION, identifier.asString))\n        } else {\n            emptyList()\n        }\n        watchNotifier.send(watchKey(key), title, body, actions)', '')
    replace_literal(firmware_update_ui_tracker, '            watchNotifier.remove(watchKey(notificationKey))\n', '')

    replace_literal(firmware_update_ui_tracker, '    private fun watchKey(key: Int) = "firmware-update/$key"\n', '')
    replace_literal(firmware_update_ui_tracker,
                    'const val FIRMWARE_UPDATE_NOW_WATCH_ACTION = "firmware_update_now"\n', '')
    edit(pebble_app_delegate,
         r"^import (?:coredevices\.pebble\.firmware\.FIRMWARE_UPDATE_NOW_WATCH_ACTION|coredevices\.util\.setWatchNotificationActionHandler)\n", '', expect=2)
    remove_kotlin_block(pebble_app_delegate,
                    r"^        libPebble\.setWatchNotificationActionHandler\(FIRMWARE_UPDATE_NOW_WATCH_ACTION\) \{")
    replace_literal(pebble_app_delegate, '        permissionRequestNotifier.registerWatchActions()\n', '')

    edit(android_module, r"^import coredevices\.util\.(?:NoOpWatchNotifier|WatchNotifier)\n", '', expect=2)
    replace_literal(android_module, '    singleOf(::NoOpWatchNotifier) bind WatchNotifier::class\n', '')

    # Unreferenced library definitions; live health parsers and platform health sync stay.

    remove_kotlin_block(platform_android, r"^    companion object \{")
    replace_literal(platform_android, 'import kotlinx.coroutines.flow.MutableSharedFlow\n', '')

    remove_kotlin_block(platform, r"^    companion object \{")
    replace_literal(platform, 'import kotlinx.coroutines.channels.Channel\n', '')

    remove_kotlin_block(health_records, r"^data class StepsRecord\(")
    remove_kotlin_block(health_records, r"^data class OverlayRecord\(")

    remove_kotlin_block(health_records, r"^class RawStepsRecord : StructMappable\(\) \{")
    remove_kotlin_block(health_records, r"^class RawOverlayRecord : StructMappable\(\) \{")

    edit(health_records,
         r"^import io\.rebble\.libpebblecommon\.(?:structmapper\.(?:SUByte|SUInt|SUShort|StructMappable)|util\.Endian)\n", '', expect=5)
    remove_kotlin_block(health, r"^/\*\* [^\n]* \*/\ndata class StackedSleepData\(")

    remove_kotlin_block(health, r"^/\*\* [^\n]* \*/\ndata class WeeklyAggregatedData\(")
    remove_kotlin_block(health, r"^/\*\* [^\n]* \*/\ndata class SleepSegment\(")

    remove_kotlin_block(health, r"^/\*\* [^\n]* \*/\ndata class DailySleepData\(")
    remove_kotlin_block('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/XMLHTTPRequestManager.kt',
                    r"^@Serializable\ndata class CompleteXHRResponse\(")
    remove_kotlin_block('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/calendar/CalendarEvent.kt',
                    r"^data class EventRecurrenceRule\(")
    replace_literal(common_app_delegate, '    private val pebbleAccountProvider: PebbleAccountProvider,\n', '')

    replace_literal(common_app_delegate, 'import coredevices.pebble.services.PebbleAccountProvider\n', '')
    replace_literal(permission_request_notifier,
                    'notify(notificationFor(appUuid, keys))', 'notifyPermissionRequest(appContext, notificationFor(appUuid, keys))')
    remove_kotlin_block(permission_request_notifier, r"^    private fun notify\(")


def harden_release_manifest() -> None:
    """Take out of the release what it should never have exported.

    - Compose's PreviewActivity: a development tool, exported without a permission, that renders
      any composable an intent names. It comes with the tooling library the modules declare for
      every build; the release manifest drops it.
    - The cloud.repebble.com/githubAuth link: the landing point of Core's GitHub sign-in, removed
      with Core's account (remove_core_account()). Its handler did nothing, and Orb can't verify
      Core's domain for app links anyway.
    """
    manifest = "androidApp/src/main/AndroidManifest.xml"
    edit(manifest, r"^    </application>\n",
         '        <activity\n'
         '            android:name="androidx.compose.ui.tooling.PreviewActivity"\n'
         '            tools:node="remove" />\n'
         '        <activity\n'
         '            android:name="org.jetbrains.androidx.compose.ui.tooling.PreviewActivity"\n'
         '            tools:node="remove" />\n'
         "    </application>\n")
    edit(manifest,
         r'^            <intent-filter android:autoVerify="true">\n(?:.*\n)*?'
         r'                <data android:path="/githubAuth" />\n            </intent-filter>\n', "")

    deep_links = "pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt"
    remove_kotlin_block(deep_links, r'^            uri\.scheme == "https" \|\| uri\.scheme == "http" -> \{')
    remove_kotlin_block(deep_links, r"^    private fun handleGithubAuth\(uri: Uri\): Boolean \{")
    edit(deep_links, r"^        private const val GITHUB_OAUTH_CALLBACK_(HOST|PATH): String = .*\n", "", expect=2)


def remove_help_page() -> None:
    """Remove "Getting Started & Troubleshooting": Core's guide to its own app.

    The guide lives in Core's Intercom help centre and describes Core's app, accounts and
    support, much of which Orb doesn't have. The in-app page viewer that showed it had no other
    use and goes too.
    """
    remove_setting("pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt",
                   "Getting Started & Troubleshooting")
    nav_host = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt"
    remove_kotlin_block(nav_host, r"^[ \t]*composable<CommonRoutes\.TroubleshootingRoute> \{")
    edit(nav_host, r"^import coredevices\.ui\.GenericWebViewScreen\n", "")
    edit("util/src/commonMain/kotlin/CommonRoutes.kt",
         r"^    @Serializable\n    data object TroubleshootingRoute : CoreRoute\n\n", "")


def remove_debug_receivers() -> None:
    """Take Core's adb test hooks out of the app.

    Three broadcast receivers let a shell user attach an emulated watch, start the LAN developer
    connection and write any app setting. Only the shell and the system could send to them
    (android.permission.DUMP), but they are test tooling, not features. A pairing logger wrote
    every Bluetooth pairing request, its key included, into the log that Share Logs sends.
    """
    edit("androidApp/src/main/AndroidManifest.xml",
         r"^\n        <!--\n            Attaches a QEMU emulator watch for automated testing\.(?:.*\n)*?"
         r'                <action android:name="coredevices\.coreapp\.SET_SETTING" />\n'
         r"            </intent-filter>\n        </receiver>\n", "")
    main_application = "composeApp/src/androidMain/kotlin/coredevices/coreapp/MainApplication.kt"
    edit(main_application, r"^import coredevices\.coreapp\.util\.registerBluetoothPairingDebugLogger\n", "")
    edit(main_application, r"^        registerBluetoothPairingDebugLogger\(this\)\n", "")


def remove_qa_flag() -> None:
    """Remove Core's QA build flag. Builds without the QA variable got QA, so it was always on.

    The screens it gated are Orb's own first-run and log-sharing screens and stay, without the
    condition. What else read it was unused: a bug-report button nothing shows, and a request for
    storage permissions the app doesn't declare.
    """
    nav_host = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt"
    unwrap_kotlin_block(nav_host, "        if (CommonBuildKonfig.QA) {\n")
    edit(nav_host, r"^import coredevices\.util\.CommonBuildKonfig\n", "")
    button = "util/src/commonMain/kotlin/BugReportButton.kt"
    remove_kotlin_block(button, r"^@Composable\nfun BugReportButton\(")
    edit(button, r"^import (?:androidx\.compose\..*|coredevices\.util\.CommonBuildKonfig|kotlinx\.serialization\.json\.Json|org\.koin\.compose\.koinInject)\n", "", expect=10)
    edit(button, r"^private val jsonPretty = Json \{\n(?:.*\n)*?\}\n\n", "")

    edit("util/src/androidMain/kotlin/coredevices/util/AndroidPermissionRequester.kt",
         r"^    Permission\.ExternalStorage -> if \(.*\n(?:.*\n)*?    \} else emptyList\(\)\n", "")
    edit("util/src/commonMain/kotlin/coredevices/util/Permission.kt", r"^    ExternalStorage,\n", "")
    edit("util/src/commonMain/kotlin/coredevices/util/PermissionRequester.kt",
         r"^    Permission\.ExternalStorage -> .*\n", "", expect=2)
    edit("util/src/iosMain/kotlin/coredevices/util/IosPermissionRequester.kt",
         r"^[ \t]*Permission\.ExternalStorage -> .*\n", "", expect=2)

    gradle = "util/build.gradle.kts"
    edit(gradle, r'^val enableQa = .*\n', "")
    edit(gradle, r'^[ \t]*buildConfigField\(FieldSpec\.Type\.BOOLEAN, "QA", enableQa\.toString\(\)\)\n', "")


def block_cleartext() -> None:
    """Allow encrypted connections only. Orb itself only ever uses HTTPS; Core allowed plain HTTP
    so that watchapps' own code and settings pages could reach servers that don't offer HTTPS.

    The network security config decides this for the whole app, the WebViews included, and
    makes the manifest's usesCleartextTraffic meaningless, so that attribute goes.
    """
    edit("androidApp/src/main/res/xml/network_security_config.xml",
         r"^    <!-- This overrides android:usesCleartextTraffic in the manifest, which is ignored whenever a\n"
         r"         network security config is present\. -->\n"
         r'^    <base-config cleartextTrafficPermitted="true">\n',
         '    <!-- HTTPS only, for Orb and for watchapps. -->\n'
         '    <base-config cleartextTrafficPermitted="false">\n')
    edit("androidApp/src/main/AndroidManifest.xml", r'^        android:usesCleartextTraffic="true"\n', "")


def set_backup_rules() -> None:
    """Back up what a new phone needs to have Orb as it was, and nothing else.

    Android's backup, Seedvault on GrapheneOS, is how the locker moves to a new phone: Orb has
    no account to keep it in. Orb's rules (the overlay's res/xml files, replacing Core's, which
    only excluded Firebase sign-in files) say what is copied and why. The manifest states the
    decision to allow backup at all.
    """
    # RestoredDataTest (overlay, androidApp/src/androidTest) checks on a device what a restore
    # brings: Keystore-encrypted values from another phone, and Core's database schema.
    gradle = "androidApp/build.gradle.kts"
    edit(gradle, r"^(    androidTestImplementation\(libs\.kotlin\.test\)\n)",
         r'\1'
         r"    androidTestImplementation(libs.room.testing)\n"
         r"    androidTestImplementation(libs.sqlite.bundled)\n")
    with (APP / gradle).open("a") as file:
        file.write('\n// Room\'s MigrationTestHelper reads the exported schemas from the test\'s assets.\n'
                   'android.sourceSets.getByName("androidTest").assets.srcDirs("../util/schema", "../libpebble3/schema")\n')
    edit("androidApp/src/main/AndroidManifest.xml", r"^(    <application\n)",
         "    <!-- Backup is allowed on purpose: it is how Orb's data reaches a new phone, since there\n"
         "         is no account to keep it in. res/xml/data_extraction_rules.xml says what it copies. -->\n"
         r"\1")


def drop_core_telemetry_tables() -> None:
    """Drop four tables of Core's app database that nothing reads or writes in Orb.

    They queued Memfault diagnostics, analytics heartbeats and their state, and the removed sync
    tasks. The database moves to version 12, which deletes them; Room stores its schema in
    overlay/util/schema.
    """
    database = "util/src/commonMain/kotlin/coredevices/database/CoreDatabase.kt"
    edit(database,
         r"^        (?:HeartbeatStateEntity|MemfaultChunkEntity|AnalyticsHeartbeatEntity|SyncTaskEntity)::class,\n",
         "", expect=4)
    edit(database, r"^    version = 11,\n", "    version = 12,\n")
    edit(database, r"^(        AutoMigration\(from = 10, to = 11\),\n)",
         r"\1        AutoMigration(from = 11, to = 12, spec = DropCoreTelemetryTables::class),\n")
    edit(database, r"^(import androidx\.room\.Database\n)", r"\1import androidx.room.DeleteTable\n")
    edit(database, r"^(import androidx\.room\.TypeConverters\n)",
         r"\1import androidx.room.migration.AutoMigrationSpec\n")
    with (APP / database).open("a") as file:
        file.write(
            "\n// Orb: Core's telemetry upload queues and sync tasks, which nothing in Orb uses.\n"
            "@DeleteTable.Entries(\n"
            '    DeleteTable(tableName = "HeartbeatStateEntity"),\n'
            '    DeleteTable(tableName = "memfault_chunks"),\n'
            '    DeleteTable(tableName = "analytics_heartbeats"),\n'
            '    DeleteTable(tableName = "sync_tasks"),\n'
            ")\n"
            "class DropCoreTelemetryTables : AutoMigrationSpec\n"
        )


def remove_google_fit() -> None:
    """Remove what is left of Google Fit: a function that opened the app or its Play Store page,
    which nothing calls since its setting went, and the health library's request to see it."""
    settings_screen = "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt"
    edit(settings_screen, r"^expect fun openGoogleFitApp\(uiContext: PlatformUiContext\?\)\n\n", "")
    remove_kotlin_block("pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.android.kt",
                        r"^actual fun openGoogleFitApp\(")
    remove_kotlin_block("pebble/src/iosMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.ios.kt",
                        r"^actual fun openGoogleFitApp\(")
    edit("androidApp/src/main/AndroidManifest.xml", r"^(    <application\n)",
         '    <queries>\n'
         '        <package android:name="com.google.android.apps.fitness" tools:node="remove" />\n'
         '    </queries>\n'
         r"\1")


def harden_orb_release() -> None:
    """Release input, IPC, permission and credential boundaries."""
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        '    fun confirmPendingFirmwareSideload()',
        '    fun confirmPendingFirmwareSideload(expected: PendingFirmwareSideload)',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
        if (path != null) {
            firmwareUpdateUiTracker.updateWatchNow(libPebble, path.removePrefix("/").removeSuffix("/"))
        }
""",
        '',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
        val previous = _pendingFirmwareSideload.value
        val reserved = reserveSideloadCopy(file)
        _pendingFirmwareSideload.value = PendingFirmwareSideload(reserved, fileName)
        previous?.takeIf { it.file != reserved }
            ?.let { SystemFileSystem.delete(it.file, mustExist = false) }
""",
        """\
        val pending = PendingFirmwareSideload(file, orbDisplayName(fileName))
        if (!_pendingFirmwareSideload.compareAndSet(null, pending)) {
            SystemFileSystem.delete(file, mustExist = false)
            return false
        }
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
    override fun confirmPendingFirmwareSideload() {
        val pending = _pendingFirmwareSideload.value ?: return
        _pendingFirmwareSideload.value = null
        sideloadFirmware(pending.file)
""",
        """\
    override fun confirmPendingFirmwareSideload(expected: PendingFirmwareSideload) {
        if (!_pendingFirmwareSideload.compareAndSet(expected, null)) return
        sideloadFirmware(expected.file)
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
        if (_pendingLanguagePack.value != null) {
            SystemFileSystem.delete(file, mustExist = false)
            return false
        }
        _pendingLanguagePack.value = PendingLanguagePack(file, orbDisplayName(name))
""",
        """\
        if (!_pendingLanguagePack.compareAndSet(null, PendingLanguagePack(file, orbDisplayName(name)))) {
            SystemFileSystem.delete(file, mustExist = false)
            return false
        }
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
        _pendingAppSideload.value = file
""",
        """\
        if (!_pendingAppSideload.compareAndSet(null, file)) {
            SystemFileSystem.delete(file, mustExist = false)
            return false
        }
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt',
        '        override fun confirmPendingFirmwareSideload() {}',
        '        override fun confirmPendingFirmwareSideload(expected: coredevices.pebble.PendingFirmwareSideload) {}',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
import kotlinx.coroutines.GlobalScope
""",
        """\
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
    override fun handle(uri: Uri?): Boolean {
""",
        """\
    private val importLock = Semaphore(1)
    private var importing = false

    override fun handle(uri: Uri?): Boolean {
        uri ?: return false
        val isFile = uri.scheme == "content" || uri.lastPathSegment?.let {
            it.endsWith(".pbw") || it.endsWith(".pbz") || it.endsWith(".pbl")
        } == true
        if (isFile) {
            // handle() is an Activity entry point on the main thread.
            if (importing || _pendingFirmwareSideload.value != null ||
                _pendingLanguagePack.value != null || _pendingAppSideload.value != null) return false
            importing = true
            GlobalScope.launch(Dispatchers.IO) {
                try { importLock.withPermit { handleNow(uri) } }
                finally { importing = false }
            }
            return true
        }
        return handleNow(uri)
    }

    private fun handleNow(uri: Uri?): Boolean {
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
    private fun reserveSideloadCopy(shared: Path): Path {
        val directory = shared.parent ?: return shared
        if (reservedSideloadCount == 0) {
            sweepStaleSideloadCopies(directory)
        }
        val reserved = Path(directory, "$RESERVED_SIDELOAD_PREFIX${reservedSideloadCount++}.pbz")
        return try {
            SystemFileSystem.delete(reserved, mustExist = false)
            SystemFileSystem.atomicMove(shared, reserved)
            reserved
        } catch (e: Exception) {
            logger.w(e) { "reserveSideloadCopy: falling back to the shared path" }
            shared
        }
    }

    private fun sweepStaleSideloadCopies(directory: Path) {
        try {
            SystemFileSystem.list(directory)
                .filter { it.name.startsWith(RESERVED_SIDELOAD_PREFIX) }
                .forEach { SystemFileSystem.delete(it, mustExist = false) }
        } catch (e: Exception) {
            logger.w(e) { "sweepStaleSideloadCopies failed" }
        }
    }

""",
        '',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
    private var reservedSideloadCount = 0
""",
        '',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
        private const val RESERVED_SIDELOAD_PREFIX = "pending_sideload_"
""",
        '',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'logger.v { "handleContentFallback() $uri" }',
        'logger.v { "content import" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'logger.w { "handleContentFallback: couldn\'t get name for $uri" }',
        'logger.w { "content import: missing name" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'logger.d { "filename: $name" }',
        'logger.d { "content import: name resolved" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'logger.v { "handleLanguagePack() $uri" }',
        'logger.v { "language pack import" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'logger.v { "handleFirmware() $uri" }',
        'logger.v { "firmware import" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'logger.v { "handleApp() $uri" }',
        'logger.v { "watchapp import" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/PebbleAccount.kt',
        'import kotlinx.serialization.SerialName',
        """\
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.SerialName\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/PebbleAccount.kt',
        '    override suspend fun setToken(token: String?, bootUrl: String?) {',
        """\
    private val identityLock = Mutex()

    private fun clearIdentity() {
        settings.remove(DEV_KEY)
        _devToken.value = null
    }

    override suspend fun setToken(token: String?, bootUrl: String?) = identityLock.withLock {
        clearIdentity()\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/PebbleAccount.kt',
        """\
        setDevPortalId()
""",
        """\
        if (token != null) fetchDevPortalId()
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/PebbleAccount.kt',
        '    override suspend fun setDevPortalId() {',
        """\
    override suspend fun setDevPortalId() = identityLock.withLock {
        clearIdentity()
        if (_loggedIn.value != null) fetchDevPortalId()
    }

    private suspend fun fetchDevPortalId() {\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/BootConfig.kt',
        'logger.d("setUrl $url")',
        'logger.d("boot URL changed")',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/BootConfig.kt',
        'logger.d("got bootconfig: $bootConfig")',
        'logger.d("boot configuration received")',
    )
    replace_literal(
        'composeApp/src/androidMain/kotlin/coredevices/coreapp/MainActivity.kt',
        'logger.d { "handleIntent uri = $uri" }',
        'logger.d { "incoming link host=${uri?.host?.takeIf { Regex("[A-Za-z0-9.-]{1,253}").matches(it) }.orEmpty()}" }',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/AppPermissions.kt',
        '    if (subject.legacy && !config.askLegacyAppsForPermissions && isLegacyImplicit(permission, subject.hasAndroidCompanion)) {',
        """\
    if (subject.legacy && permission in setOf(PluginPermissions.GLOBAL_INTERNET, PluginPermissions.LOCATION)) {
        return PermissionDecision.NeedsApproval
    }
    if (subject.legacy && !config.askLegacyAppsForPermissions && isLegacyImplicit(permission, subject.hasAndroidCompanion)) {\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/AppPermissions.kt',
        '        config.permissionPolicy == PermissionPolicy.NeverAsk &&',
        """\
        !(subject.legacy && permission in setOf(PluginPermissions.GLOBAL_INTERNET, PluginPermissions.LOCATION)) &&
        config.permissionPolicy == PermissionPolicy.NeverAsk &&\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt',
        'title = "Ask before older apps use permissions"',
        'title = "Ask before older apps use other permissions"',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchSettingsScreen.kt',
        'description = "Otherwise apps built before permissions keep the access they\'ve always had. They can never get more access without updating. Some older apps may break, particularly ones that use health data"',
        'description = "Network and location always require approval. Also ask older apps before other access, including health data. Some older apps may break"',
    )
    replace_literal(
        'androidApp/src/main/res/xml/network_security_config.xml',
        """\
<?xml version="1.0" encoding="utf-8"?>
<!--
  Allow user-installed CA certificates to be trusted in addition to the system
  CA store. Since Android 7.0 (API 24), apps only trust the system store by
  default, so PKJS apps connecting to self-hosted servers with a self-signed or
  private-CA cert (e.g. Home Assistant over wss://) fail to connect even after
  the user installs and trusts the cert on their device.
-->
<network-security-config>
    <!-- HTTPS only, for Orb and for watchapps. -->
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
""",
        """\
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleSenderReceiver.kt',
        'import io.rebble.libpebblecommon.connection.ConnectedPebbleDevice',
        """\
import android.content.Intent
import android.os.Binder
import android.os.Bundle
import android.os.IBinder
import io.rebble.pebblekit2.common.UniversalRequestResponse
import io.rebble.pebblekit2.common.SendDataCallback
import io.rebble.pebblekit2.common.model.toBundle
import io.rebble.libpebblecommon.pebblekit.PebbleKitAuthorization
import kotlinx.coroutines.launch
import io.rebble.libpebblecommon.connection.ConnectedPebbleDevice\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleSenderReceiver.kt',
        '    override suspend fun sendDataToPebble(',
        """\
    override fun onBind(intent: Intent?): IBinder {
        val original = UniversalRequestResponse.Stub.asInterface(super.onBind(intent))
        return object : UniversalRequestResponse.Stub() {
            override fun request(data: Bundle, callback: SendDataCallback) {
                val action = data.getString("ACTION")
                if (action != "START_APP" && action != "STOP_APP") {
                    original.request(data, callback)
                    return
                }
                val callers = packageManager.getPackagesForUid(Binder.getCallingUid()).orEmpty().toList()
                val uuid = data.getString("WATCHAPP_UUID")?.let { runCatching { UUID.fromString(it) }.getOrNull() }
                val targets = data.getStringArray("WATCHES_ID")?.map { WatchIdentifier(it) }
                coroutineScope.launch {
                    val allowed = uuid != null && PebbleKitAuthorization.allowed(callers, uuid.toKotlinUuid())
                    val result = runOnConnectedWatches(targets) { watch ->
                        if (!allowed) TransmissionResult.FailedNoPermissions
                        else {
                            if (action == "START_APP") watch.launchApp(uuid!!.toKotlinUuid())
                            else watch.stopApp(uuid!!.toKotlinUuid())
                            TransmissionResult.Success
                        }
                    }
                    val serialized = Bundle().apply {
                        result.forEach { (watch, status) -> putBundle(watch.value, status.toBundle()) }
                    }
                    try { callback.onResult(Bundle().apply { putBundle("TRANSMISSION_RESULTS", serialized) }) }
                    catch (_: android.os.RemoteException) { /* Caller went away. */ }
                }
            }
        }
    }

    override suspend fun sendDataToPebble(\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleSenderReceiver.kt',
        """\
            it.launchApp(watchappUUID.toKotlinUuid())
            TransmissionResult.Success\
""",
        '            TransmissionResult.FailedNoPermissions',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleSenderReceiver.kt',
        """\
            it.stopApp(watchappUUID.toKotlinUuid())
            TransmissionResult.Success\
""",
        '            TransmissionResult.FailedNoPermissions',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleSenderReceiver.kt',
        """\
        if (pkg == null) {
            return false
        }

        val lockerEntry = locker.getLockerApp(uuid.toKotlinUuid()).firstOrNull() ?: return false
        val pbwInfo = PbwApp(
            lockerPBWCache.getPBWFileForApp(
                lockerEntry.properties.id,
                lockerEntry.properties.version.orEmpty(),
                locker
            )
        )

        return pkg in pbwInfo.info.pebbleKit2Packages() &&
            permissions.request(uuid.toKotlinUuid(), pebbleKit2Key(pkg)) == PermissionDecision.Granted\
""",
        '        return pkg != null && PebbleKitAuthorization.allowed(listOf(pkg), uuid.toKotlinUuid())',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleKitProvider.kt',
        'import io.rebble.libpebblecommon.connection.ConnectedPebbleDevice',
        """\
import android.database.Cursor
import android.net.Uri
import android.os.Binder
import io.rebble.libpebblecommon.pebblekit.PebbleKitAuthorization
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import io.rebble.libpebblecommon.connection.ConnectedPebbleDevice\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleKitProvider.kt',
        '   override fun getConnectedWatches()',
        """\
   override fun query(uri: Uri, projection: Array<out String>?, selection: String?,
                      selectionArgs: Array<out String>?, sortOrder: String?): Cursor? {
      val callers = context?.packageManager?.getPackagesForUid(Binder.getCallingUid()).orEmpty().toList()
      if (!runBlocking(Dispatchers.IO) { PebbleKitAuthorization.associated(callers) }) return null
      return super.query(uri, projection, selection, selectionArgs, sortOrder)
   }

   override fun getConnectedWatches()\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/PKJSApp.kt',
        '    private var jsRunner: JsRunner? = null',
        """\
    private val externalConfig = ExternalConfigRequest()

    fun closeExternalConfig(state: String?, data: String): Boolean {
        if (!externalConfig.consume(state)) return false
        triggerOnWebviewClosed(data)
        return true
    }

    private var jsRunner: JsRunner? = null\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/PKJSApp.kt',
        '    suspend fun requestConfigurationUrl(): String? {',
        """\
    suspend fun requestConfigurationUrl(): String? {
        externalConfig.clear()\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/PKJSApp.kt',
        '        return if (jsRunner.mayOpen(received)) received else null',
        """\
        if (!jsRunner.mayOpen(received)) return null
        val state = externalConfig.begin()
        return io.ktor.http.URLBuilder(received).apply {
            parameters.remove("orb_state")
            parameters.remove("return_to")
            parameters.append("orb_state", state)
            parameters.append("return_to", "pebblejs://close?orb_state=$state")
        }.buildString()\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/PKJSApp.kt',
        '    override suspend fun stop() {',
        """\
    override suspend fun stop() {
        externalConfig.clear()\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/PKJSApp.kt',
        '    fun triggerOnWebviewClosed(data: String) {',
        """\
    fun triggerOnWebviewClosed(data: String) {
        externalConfig.clear()\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
                libPebble.watches.value
                    .filterIsInstance<ConnectedPebbleDevice>()
                    .firstOrNull { it.currentPKJSSession.value != null }
                    ?.currentPKJSSession
                    ?.value
                    ?.triggerOnWebviewClosed(data) ?: run {
                        logger.w { "No PKJS session found, cannot handle webview close" }
                        return false
                    }\
""",
        """\
                val state = uri.getQueryParameter("orb_state") ?: return false
                val accepted = libPebble.watches.value.filterIsInstance<ConnectedPebbleDevice>().any {
                    it.currentPKJSSession.value?.closeExternalConfig(state, data) == true
                }
                if (!accepted) return false\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'uri.host?.startsWith("close") == true',
        'uri.host == "close"',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/NetworkGate.kt',
        '    suspend fun check(url: String, wait: Boolean): PluginNetworkVerdict',
        """\
    suspend fun check(url: String, wait: Boolean): PluginNetworkVerdict
    fun changes(): kotlinx.coroutines.flow.Flow<Unit> = kotlinx.coroutines.flow.emptyFlow()\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/NetworkGate.kt',
        """\
) : NetworkAccess {
""",
        """\
) : NetworkAccess {
    override fun changes(): kotlinx.coroutines.flow.Flow<Unit> =
        kotlinx.coroutines.flow.merge(
            permissions.permissionDecisions().map { Unit },
            permissions.statuses(appUuid).map { Unit },
        )
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/NetworkGate.kt',
        'import kotlin.uuid.Uuid',
        """\
import kotlinx.coroutines.flow.map
import kotlin.uuid.Uuid\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        'import kotlinx.coroutines.launch',
        """\
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.onStart\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        '            Instance(++lastInstance, url, protocols, headers).also { instances[it.id] = it }',
        """\
            check(instances.size < 16) { "Too many sockets" }
            Instance(++lastInstance, url, protocols, headers).also { instances[it.id] = it }\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        '        private val outgoing = Channel<Frame>(Channel.UNLIMITED)',
        '        private val outgoing = Channel<Frame>(64)',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        '            job.value = scope.launch { run() }',
        """\
            job.value = scope.launch {
                coroutineScope {
                    val connection = launch { run() }
                    val revocation = launch {
                        networkAccess.changes().collect {
                            if (networkAccess.check(url, wait = false) is PluginNetworkVerdict.Denied) connection.cancel()
                        }
                    }
                    try { connection.join() } finally { revocation.cancel() }
                }
            }\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        """\
                        for (frame in outgoing) {
                            ws.send(frame)\
""",
        """\
                        for (frame in outgoing) {
                            if (networkAccess.check(url, wait = false) is PluginNetworkVerdict.Denied) {
                                ws.cancel(); break
                            }
                            ws.send(frame)\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        '                    for (frame in ws.incoming) {',
        """\
                    for (frame in ws.incoming) {
                        if (networkAccess.check(url, wait = false) is PluginNetworkVerdict.Denied) {
                            ws.cancel(); break
                        }\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
        'logger.w(e) { "$appUuid websocket to $url failed: ${e.message}" }',
        'logger.w { "watchapp websocket failed" }',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        'import kotlinx.coroutines.Job',
        """\
import kotlinx.coroutines.Job
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.flow.collectLatest
import kotlinx.atomicfu.locks.SynchronizedObject
import kotlinx.atomicfu.locks.synchronized\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        '    private val watchJobs = mutableMapOf<Int, Job>()',
        """\
    private val watchJobs = mutableMapOf<Int, Job>()
    private val watchLock = SynchronizedObject()\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        """\
        val job = scope.launch {
            if (!geolocationPermissionGranted()) {
                triggerPositionResultWatch(id.toInt(), GeolocationPositionResult.Error("Location permission not granted"))
                return@launch
            }
            systemGeolocation.watchPosition(interval.coerceAtLeast(200.0).milliseconds, highAccuracyBool).collect { result ->
                triggerPositionResultWatch(id.toInt(), result)
            }
        }
        watchJobs[id.toInt()] = job
""",
        """\
        val key = id.toInt()
        synchronized(watchLock) {
            watchJobs.remove(key)?.cancel()
            if (watchJobs.size >= 8) return key
            val job = scope.launch(start = CoroutineStart.LAZY) {
                val owner = currentCoroutineContext()[Job]
                try {
                    if (!geolocationPermissionGranted()) {
                        triggerPositionResultWatch(key, GeolocationPositionResult.Error("Location permission not granted"))
                        return@launch
                    }
                    val subject = permissions.subjectOf(appUuid) ?: return@launch
                    permissions.grantedKeys(subject, listOf(PluginPermissions.LOCATION)).collectLatest { grants ->
                        if (PluginPermissions.LOCATION !in grants) {
                            triggerPositionResultWatch(key, GeolocationPositionResult.Error("Location permission revoked"))
                            currentCoroutineContext().cancel()
                            return@collectLatest
                        }
                        systemGeolocation.watchPosition(interval.coerceAtLeast(200.0).milliseconds, highAccuracyBool).collect { result ->
                            if (permissions.check(appUuid, PluginPermissions.LOCATION) != PermissionDecision.Granted) {
                                currentCoroutineContext().cancel()
                            } else triggerPositionResultWatch(key, result)
                        }
                    }
                } finally {
                    synchronized(watchLock) { if (watchJobs[key] === owner) watchJobs.remove(key) }
                }
            }
            watchJobs[key] = job
            job.start()
        }
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        '        watchJobs.remove(id)?.cancel("Watch cleared")',
        '        synchronized(watchLock) { watchJobs.remove(id)?.cancel("Watch cleared") }',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        """\
        watchJobs.values.forEach { it.cancel() }
        watchJobs.clear()\
""",
        """\
        synchronized(watchLock) {
            watchJobs.values.toList().forEach { it.cancel() }
            watchJobs.clear()
        }\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/firmware/Cohorts.kt',
        '        val latestFwVersion = FirmwareVersion.from(',
        """\
        if (!Regex("[0-9a-fA-F]{64}").matches(normalFw.sha256)) {
            return FirmwareUpdateCheckResult.UpdateCheckFailed("Firmware digest missing or invalid")
        }
        val latestFwVersion = FirmwareVersion.from(\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/firmware/Cohorts.kt',
        '                url = normalFw.url,',
        '                url = normalFw.url.substringBefore(\'#\') + "#orb-sha256=" + normalFw.sha256.lowercase(),',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.v("get: ${url.sanitizeUrl(libPebble.value)} auth=$auth")',
        'logger.v("get host=${io.ktor.http.Url(url).host}")',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.v { "post url=$url result=${response.status}" }',
        'logger.v { "write host=${io.ktor.http.Url(url).host} result=${response.status}" }',
        expect=2,
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.v { "delete url=$url result=${response.status}" }',
        'logger.v { "delete host=${io.ktor.http.Url(url).host} result=${response.status}" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.w(e) { "Error doing put: ${e.message}" }',
        'logger.w { "HTTP write failed" }',
        expect=3,
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.w(e) { "Error doing get: ${e.message}" }',
        'logger.w { "HTTP read failed" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.i("http call failed: $response")',
        'logger.i("HTTP read failed")',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/services/PebbleWebServices.kt',
        'logger.e("error: ${e.message}", e)',
        'logger.e("HTTP response could not be decoded")',
        expect=2,
    )
    replace_literal(
        'composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandler.kt',
        'logger.d { "handle: uri = $uri" }',
        'logger.d { "incoming deep link" }',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/music/AndroidSystemMusicControl.kt',
        """\
            context.contentResolver.openInputStream(uri.toUri())
                ?.use { BitmapFactory.decodeStream(it) }\
""",
        '            io.rebble.libpebblecommon.imaging.boundedImage(context, uri.toUri())?.bitmap',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/music/AndroidSystemMusicControl.kt',
        'logger.d(e) { "Couldn\'t read album art uri" }',
        'logger.d { "Couldn\'t read album art" }',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImage.kt',
        """\
    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    try {
        val stream = context.contentResolver.openInputStream(this) ?: return null
        // In bounds-only mode decodeStream returns null by design; the size lands in options.
        stream.use { BitmapFactory.decodeStream(it, null, options) }
    } catch (e: Exception) {
        // The listener only holds a read grant while the notification is posted, and the provider
        // can refuse regardless.
        logger.d(e) { "couldn't read notification image" }
        return null
    }
    if (options.outWidth <= 0 || options.outHeight <= 0) return null
    return NotificationImage(NotificationImageSource.FromUri(this), options.outWidth, options.outHeight)
}
""",
        """\
    val snapshot = io.rebble.libpebblecommon.imaging.boundedImage(context, this) ?: return null
    return NotificationImage(NotificationImageSource.FromBitmap(snapshot.bitmap), snapshot.width, snapshot.height)
}
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImageStore.kt',
        """\
            val options = BitmapFactory.Options().apply { inSampleSize = sample }
            val bitmap = context.contentResolver.openInputStream(source.uri)?.use {
                BitmapFactory.decodeStream(it, null, options)
            } ?: return null
            val orientation = context.contentResolver.openInputStream(source.uri)?.use {
                ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            } ?: ExifInterface.ORIENTATION_NORMAL
""",
        """\
            val snapshot = io.rebble.libpebblecommon.imaging.boundedImage(context, source.uri) ?: return null
            val bitmap = snapshot.bitmap
            val orientation = snapshot.bytes.inputStream().use {
                ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            }
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImageStore.kt',
        '    val sample = generateSequence(1) { it * 2 }',
        """\
    if (source is NotificationImageSource.FromBitmap &&
        (width !in 1..8192 || height !in 1..8192 || width.toLong() * height > 32L * 1024 * 1024)) return null
    val sample = generateSequence(1) { it * 2 }\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt',
        'settings.allowFileAccess = true',
        'settings.allowFileAccess = false',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt',
        'settings.allowUniversalAccessFromFileURLs = true',
        'settings.allowUniversalAccessFromFileURLs = false',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt',
        'settings.allowFileAccessFromFileURLs = true',
        'settings.allowFileAccessFromFileURLs = false',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt',
        '            val urlAsUri = Uri.fromFile(File(jsUrl)).toString()',
        '            val appScript = withContext(Dispatchers.IO) { File(jsUrl).readText() }',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt',
        """\
                webView.evaluateJavascript(
                        \"""
                            (() => {
                                const signalLoaded = () => {
                                    _Pebble.signalAppScriptLoadedByBootstrap();
                                }
                                const head = document.getElementsByTagName("head")[0];
                                const script = document.createElement("script");
                                script.type = "text/javascript";
                                script.onreadystatechange = signalLoaded;
                                script.onload = signalLoaded;
                                script.charset = "utf-8";
                                script.src = ${Json.encodeToString(urlAsUri)};
                                head.appendChild(script);
                            })();
                            \""".trimIndent()
                ) { value -> logger.d { "added app script tag" } }
                webView.evaluateJavascript("document.title = ${Json.encodeToString("PKJS: ${appInfo.longName}")};", null)\
""",
        """\
                webView.evaluateJavascript(appScript) {
                    webView.evaluateJavascript("_Pebble.signalAppScriptLoadedByBootstrap();", null)
                }\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt',
        'logger.d { "Page finished loading: $url" }',
        'logger.d { "PKJS page loaded" }',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewPrivatePKJSInterface.kt',
        'logger.v { "Startup script has loaded: $data" }',
        'logger.v { "Startup script loaded" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt',
        """\
    network: ConfigPageNetwork,
""",
        """\
    network: ConfigPageNetwork,
    expectedUrl: String,
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
    network: ConfigPageNetwork,
""",
        """\
    network: ConfigPageNetwork,
    expectedUrl: String,
""",
    )
    replace_literal(
        'pebble/src/iosMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.ios.kt',
        """\
    network: ConfigPageNetwork,
""",
        """\
    network: ConfigPageNetwork,
    expectedUrl: String,
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt',
        'webViewFactory(it, webViewUuid, bridge, mayLoad, pageNetwork)',
        'webViewFactory(it, webViewUuid, bridge, mayLoad, pageNetwork, url)',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/config/ConfigPageBridge.kt',
        '    if (android && android.call) return android.call(payload);',
        '    if (android && android.postMessage) return android.postMessage(payload);',
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
    addJavascriptInterface(ConfigNetwork(mayLoad), CONFIG_NETWORK_NAMESPACE)
""",
        """\
    settings.allowFileAccess = false
    settings.allowContentAccess = false
    settings.allowFileAccessFromFileURLs = false
    settings.allowUniversalAccessFromFileURLs = false
    check(WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER))
    val expected = Uri.parse(expectedUrl)
    val expectedOrigin = if (expected.scheme == "https" || expected.scheme == "http")
        "${expected.scheme}://${expected.encodedAuthority}" else null
    val origins = setOf(expectedOrigin ?: "*")
    fun accepts(origin: Uri, mainFrame: Boolean): Boolean = mainFrame &&
        if (expectedOrigin != null) origin.toString() == expectedOrigin
        else origin.toString() == "null" && url == expectedUrl
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        'configNetworkJs(context)',
        'configNetworkJs(context, network.csp)',
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
    addJavascriptInterface(NativeConfigBridge(bridge), CONFIG_NATIVE_NAMESPACE)
    bridge.attach { js -> post { evaluateJavascript(js, null) } }\
""",
        """\
    WebViewCompat.addWebMessageListener(this, CONFIG_NATIVE_NAMESPACE, origins) { _, message, origin, main, _ ->
        if (accepts(origin, main)) message.data?.let(bridge::onCall)
    }
    bridge.attach { js -> post {
        val current = Uri.parse(url.orEmpty())
        if (expectedOrigin?.let { "${current.scheme}://${current.encodedAuthority}" == it } ?: (url == expectedUrl))
            evaluateJavascript(js, null)
    } }\
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        'WebViewCompat.addDocumentStartJavaScript(this, CONFIG_PAGE_SHIM_JS, setOf("*"))',
        'WebViewCompat.addDocumentStartJavaScript(this, CONFIG_PAGE_SHIM_JS, origins)',
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        '    addJavascriptInterface(localStorageInterface, "_localStorage")',
        """\
    configStorage[this] = localStorageInterface
    WebViewCompat.addWebMessageListener(this, "_OrbConfigStorage", origins) { _, message, origin, main, _ ->
        if (accepts(origin, main)) message.data?.let { localStorageInterface.saveState(it) }
    }\
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        '    actual val enforced = csp == null || WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)',
        """\
    actual val enforced = WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER) &&
        (csp == null || WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT))\
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
private fun configNetworkJs(context: Context) =
    context.assets.open("realm_guard.js").bufferedReader().use { it.readText() } + \"""
        if (typeof $CONFIG_NETWORK_NAMESPACE !== 'undefined') {
          __pebbleGuardRealms(globalThis, $CONFIG_NETWORK_NAMESPACE.allowed.bind($CONFIG_NETWORK_NAMESPACE), false);
        }
    \""".trimIndent()

private class ConfigNetwork(private val mayLoad: (String) -> Boolean) {
    @JavascriptInterface
    fun allowed(url: String) = mayLoad(url)
}

private class NativeConfigBridge(private val bridge: ConfigPageBridge) {
    @JavascriptInterface
    fun call(json: String) = bridge.onCall(json)
}

""",
        """\
private val configStorage = java.util.WeakHashMap<WebView, WebViewJSLocalStorageInterface>()

private fun configNetworkJs(context: Context, csp: String?) =
    context.assets.open("realm_guard.js").bufferedReader().use { it.readText() } + \"""
        (function () {
          var policy = ${Json.encodeToString(csp?.substringAfter("connect-src ")?.substringBefore(';'))};
          function allowed(raw) {
            try {
              var u = new URL(raw, location.href);
              if (!['https:', 'http:', 'wss:', 'ws:'].includes(u.protocol)) return false;
              if (policy === null) return true;
              return policy.split(' ').some(function (rule) {
                if (rule === "'none'") return false;
                var r = new URL(rule.replace('://*.', '://'));
                return u.protocol === r.protocol && (u.hostname === r.hostname ||
                  (rule.includes('://*.') && u.hostname.endsWith('.' + r.hostname))) && u.port === r.port;
              });
            } catch (e) { return false; }
          }
          __pebbleGuardRealms(globalThis, allowed, false);
        })();
    \""".trimIndent()

""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
        webView.evaluateJavascript(\"""
            (function() {
                // Storage is disabled\
""",
        """\
        val saved = configStorage[webView]?.restoreState() ?: "{}"
        webView.evaluateJavascript(\"""
            (function() {
                // Storage is disabled\
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        'const localStorageData = JSON.parse(window._localStorage.restoreState());',
        'const localStorageData = JSON.parse(${Json.encodeToString(saved)});',
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        'window._localStorage.saveState(JSON.stringify(data));',
        'window._OrbConfigStorage.postMessage(JSON.stringify(data));',
    )
    replace_literal(
        'pebble/src/iosMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.ios.kt',
        '        (didReceiveScriptMessage.body as? String)?.let { bridge.onCall(it) }',
        '        if (didReceiveScriptMessage.frameInfo.mainFrame) (didReceiveScriptMessage.body as? String)?.let { bridge.onCall(it) }',
    )
    replace_literal(
        'util/src/androidMain/kotlin/RememberDocumentLauncher.android.kt',
        'logger.w(e) { "Couldn\'t open $uri" }',
        'logger.w { "Couldn\'t open incoming document" }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/config/ConfigPageBridge.kt',
        'logger.w(e) { "malformed call from config page" }',
        'logger.w { "malformed call from config page" }',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleKitProvider.kt',
        'projection: Array<out String>?',
        'projection: Array<out String?>?',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleKitProvider.kt',
        'selectionArgs: Array<out String>?',
        'selectionArgs: Array<out String?>?',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/classic/io/rebble/libpebblecommon/pebblekit/classic/PebbleKitProvider.kt',
        '        val cursor = MatrixCursor(CURSOR_COLUMN_NAMES)',
        """\
        if (!initializeIfNeeded()) return null
        val callers = context?.packageManager?.getPackagesForUid(android.os.Binder.getCallingUid()).orEmpty().toList()
        if (!kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.IO) {
            io.rebble.libpebblecommon.pebblekit.PebbleKitAuthorization.associated(callers)
        }) return null
        val cursor = MatrixCursor(CURSOR_COLUMN_NAMES)\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/classic/io/rebble/libpebblecommon/pebblekit/classic/PebbleKitProvider.kt',
        '        cursor.use { _ ->',
        '        run {',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/classic/io/rebble/libpebblecommon/pebblekit/classic/PebbleKitProvider.kt',
        '                return@use',
        '                return@run',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/BootConfig.kt',
        'logger.w("error decoding bootconfig", e)',
        'logger.w("error decoding boot configuration")',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/account/BootConfig.kt',
        'logger.w(e) { "Failed to refresh stale boot config, using cached version" }',
        'logger.w { "Boot configuration refresh failed; using cached version" }',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        """\
                            currentCoroutineContext().cancel()
                            return@collectLatest\
""",
        """\
                            owner?.cancel()
                            return@collectLatest\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/GeolocationInterface.kt',
        '                                currentCoroutineContext().cancel()',
        '                                owner?.cancel()',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        '    private var importing = false',
        '    private val importing = MutableStateFlow(false)',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
            if (importing || _pendingFirmwareSideload.value != null ||
                _pendingLanguagePack.value != null || _pendingAppSideload.value != null) return false
            importing = true\
""",
        """\
            if (_pendingBootConfig.value != null || _pendingFirmwareSideload.value != null ||
                _pendingLanguagePack.value != null || _pendingAppSideload.value != null ||
                !importing.compareAndSet(false, true)) return false\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        'finally { importing = false }',
        'finally { importing.value = false }',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        '    private fun handleBootConfig(path: String?): Boolean {',
        """\
    private fun handleBootConfig(path: String?): Boolean {
        if (importing.value || _pendingFirmwareSideload.value != null ||
            _pendingLanguagePack.value != null || _pendingAppSideload.value != null) return false\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        '    fun consumePendingAppSideload()',
        '    fun consumePendingAppSideload(expected: Path): Boolean',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt',
        """\
    override fun consumePendingAppSideload() {
        _pendingAppSideload.value = null
    }\
""",
        """\
    override fun consumePendingAppSideload(expected: Path): Boolean =
        _pendingAppSideload.compareAndSet(expected, null)\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt',
        '        override fun consumePendingAppSideload() {}',
        '        override fun consumePendingAppSideload(expected: Path) = false',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt',
        """\
            fun discard() {
                externalSideload = null\
""",
        """\
            fun discard() {
                deepLinks.consumePendingAppSideload(path)
                externalSideload = null\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt',
        '                            sideload(path)',
        '                            if (deepLinks.consumePendingAppSideload(path)) sideload(path)',
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt',
        """\
                deepLinks.consumePendingAppSideload()
                // In the screen's scope: consuming the sideload restarts this effect.
""",
        '',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'fun globalInternetIsImplicitForLegacyAppsUnlessTheUserWantsToBeAsked()',
        'fun legacyInternetAlwaysRequiresApproval()',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        '        assertEquals(Granted, decide(GLOBAL_INTERNET, legacy))',
        '        assertEquals(NeedsApproval, decide(GLOBAL_INTERNET, legacy))',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'fun legacyLocationIsImplicitUnlessTheUserWantsToBeAsked()',
        'fun legacyLocationAlwaysRequiresApproval()',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        '        assertEquals(Granted, decide(LOCATION, legacy, rows))',
        '        assertEquals(NeedsApproval, decide(LOCATION, legacy, rows))',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/js/WebSocketManagerTest.kt',
        """\
    @Test
    fun aBlockedHostIsNeverDialled()\
""",
        """\
    @Test
    fun permissionRevocationCancelsAnIdleConnection() = runTest {
        var allowed = true
        val changes = kotlinx.coroutines.flow.MutableSharedFlow<Unit>()
        val access = object : NetworkAccess {
            override suspend fun check(url: String, wait: Boolean) =
                if (allowed) PluginNetworkVerdict.Allowed else PluginNetworkVerdict.Denied("revoked")
            override fun changes() = changes
        }
        val client = HttpClient(MockEngine { awaitCancellation() }) { install(WebSockets) }
        val evals = mutableListOf<String>()
        val manager = WebSocketManager(this, { evals.add(it) }, client, Uuid.random(), access, { _, _, _, _, _ -> })
        manager.dispatch("createInstance", listOf("wss://stream.example.com/", ""))
        runCurrent()
        allowed = false
        changes.emit(Unit)
        awaitSockets()
        assertEquals(listOf(ABNORMAL_CLOSE), evals)
        client.close()
    }

    @Test
    fun aBlockedHostIsNeverDialled()\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt',
        """\
                SystemFileSystem.sink(tempAppPath).use { sink ->
                    file.source.use { source ->
                        source.transferTo(sink)
                    }
                }
                sideload(tempAppPath)\
""",
        """\
                scope.launch {
                    val copied = withContext(Dispatchers.IO) {
                        try {
                            file.source.use { source ->
                                SystemFileSystem.sink(tempAppPath).buffered().use { sink ->
                                    var total = 0L
                                    val buffer = ByteArray(8192)
                                    while (true) {
                                        val count = source.readAtMostTo(buffer)
                                        if (count < 0) break
                                        total += count
                                        require(total <= 32L * 1024 * 1024) { "Watchapp too large" }
                                        sink.write(buffer, 0, count)
                                    }
                                }
                            }
                            true
                        } catch (_: Exception) {
                            SystemFileSystem.delete(tempAppPath, mustExist = false)
                            false
                        }
                    }
                    if (copied) sideload(tempAppPath)
                    else deepLinks.showMessage("Couldn't read watchapp: unreadable or larger than 32 MiB")
                }\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/music/AndroidSystemMusicControl.kt',
        '            val bitmap = metadata.albumArtBitmap()',
        """\
            val bitmap = metadata.albumArtBitmap()?.takeIf {
                it.width in 1..8192 && it.height in 1..8192 && it.width.toLong() * it.height <= 32L * 1024 * 1024
            }\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerScreen.kt',
        'import kotlinx.io.files.Path',
        """\
import kotlinx.io.buffered
import kotlinx.io.files.Path\
""",
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'fun everyLegacyAppKeepsLocationWhateverItsCapabilitiesSay()',
        'fun everyLegacyAppMustAskForLocation()',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'assertEquals(Granted, decide(LOCATION, subject(legacy = true), exfiltrating))',
        'assertEquals(NeedsApproval, decide(LOCATION, subject(legacy = true), exfiltrating))',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        '        assertIs<PluginNetworkVerdict.Allowed>(gate(legacy = true).check("https://anywhere.example.org/", wait = false))',
        """\
        assertIs<PluginNetworkVerdict.Denied>(gate(legacy = true).check("https://anywhere.example.org/", wait = false))
        permissions.setDecisions(APP, mapOf(GLOBAL_INTERNET to true))
        assertIs<PluginNetworkVerdict.Allowed>(gate(legacy = true).check("https://anywhere.example.org/", wait = false))\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImage.kt',
        'bigPicture(context)?.asNotificationImage()',
        'bigPicture(context)',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImage.kt',
        'private fun StatusBarNotification.bigPicture(context: Context): Bitmap?',
        'private fun StatusBarNotification.bigPicture(context: Context): NotificationImage?',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImage.kt',
        '    if (bitmap != null) return bitmap',
        '    if (bitmap != null) return bitmap.asNotificationImage()',
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImage.kt',
        '    return (icon.loadDrawable(context) as? BitmapDrawable)?.bitmap',
        """\
    return when (icon.type) {
        Icon.TYPE_URI, Icon.TYPE_URI_ADAPTIVE_BITMAP -> icon.uri.asNotificationImage(context)
        Icon.TYPE_BITMAP, Icon.TYPE_ADAPTIVE_BITMAP ->
            (icon.loadDrawable(context) as? BitmapDrawable)?.bitmap?.asNotificationImage()
        else -> null
    }\
""",
    )
    replace_literal(
        'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/notification/NotificationImage.kt',
        'if (width <= 0 || height <= 0) null',
        'if (width !in 1..8192 || height !in 1..8192 || width.toLong() * height > 32L * 1024 * 1024) null',
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/endpointmanager/FirmwareUpdater.kt',
        '        if (!watchConfig.value.autoResumeFirmwareUpdate || !fwupProps.supportsResume) return',
        """\
        if (interrupted.update.url.contains("&orb-pinned")) return
        if (!watchConfig.value.autoResumeFirmwareUpdate || !fwupProps.supportsResume) return\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/endpointmanager/FirmwareUpdater.kt',
        '            logger.d { "updateFirmware: $update" }',
        """\
            val pinned = update.url.contains("&orb-pinned")
            if (pinned && (trigger == FirmwareUpdateTrigger.AutoUpdate || requireResume)) return@launch
            logger.d { "firmware installation requested" }\
""",
    )
    replace_literal(
        'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/endpointmanager/FirmwareUpdater.kt',
        """\
            if (!tryStartUpdateMutex(update, trigger)) {
                return@launch
            }
            val path = reusableDownloadedPbz(update)\
""",
        """\
            if (!pinned && update.version < fwupProps.runningFwVersion) {
                logger.w { "Refusing firmware downgrade" }
                return@launch
            }
            if (!tryStartUpdateMutex(update, trigger)) {
                return@launch
            }
            val path = reusableDownloadedPbz(update)\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/InstallReview.kt',
        """\
"Apps built before permissions existed can use these by default. To be asked first, turn on " +
                    "\\"Ask before older apps use permissions\\" in Settings."\
""",
        """\
"Network and location always require approval. For other access, turn on " +
                    "\\"Ask before older apps use other permissions\\" in Settings."\
""",
    )
    replace_literal(
        'pebble/src/commonMain/kotlin/coredevices/pebble/ui/InstallReview.kt',
        """\
            val text = if (config.watchConfig.askLegacyAppsForPermissions) {
                "Built before permissions: asks before using $access"
            } else {
                "Built before permissions: has access to $access"
            }\
""",
        """\
            val text = "Built before permissions: $access. Network and location require approval; " +
                "other access follows Settings."\
""",
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'fun aLegacyAppIsOnlyReviewedWhenTheUserAsksForThat()',
        'fun aLegacyAppAlwaysReviewsNetworkAndLocation()',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        '        assertEquals(emptySet(), reviewed(legacy))',
        '        assertEquals(setOf(GLOBAL_INTERNET, LOCATION), reviewed(legacy))',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'assertEquals("granted", permissions.query(APP, internetKey("example.com")).queryState())',
        'assertEquals("prompt", permissions.query(APP, internetKey("example.com")).queryState())',
    )
    replace_literal(
        'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/permissions/AppPermissionsTest.kt',
        'assertNull(permissions(FakePermissionDao(), installed = installedAs(subject(legacy = true))).grantedDomains(APP))',
        'assertEquals(emptyList(), permissions(FakePermissionDao(), installed = installedAs(subject(legacy = true))).grantedDomains(APP))',
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
    val expected = Uri.parse(expectedUrl)
    val expectedOrigin = if (expected.scheme == "https" || expected.scheme == "http")
        "${expected.scheme}://${expected.encodedAuthority}" else null\
""",
        '    val expectedOrigin = coredevices.pebble.config.configPageOrigin(expectedUrl)',
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
    fun accepts(origin: Uri, mainFrame: Boolean): Boolean = mainFrame &&
        if (expectedOrigin != null) origin.toString() == expectedOrigin
        else origin.toString() == "null" && url == expectedUrl\
""",
        """\
    fun accepts(origin: Uri, mainFrame: Boolean): Boolean =
        coredevices.pebble.config.configPageMayUseBridge(expectedUrl, origin.toString(), mainFrame, url)\
""",
    )
    replace_literal(
        'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt',
        """\
        val current = Uri.parse(url.orEmpty())
        if (expectedOrigin?.let { "${current.scheme}://${current.encodedAuthority}" == it } ?: (url == expectedUrl))\
""",
        '        if (expectedOrigin?.let { coredevices.pebble.config.configPageOrigin(url.orEmpty()) == it } ?: (url == expectedUrl))',
    )

    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt', '                _snackBarMessages.tryEmit("Failed to sideload firmware: no connected watch")\n                return@launch', '                _snackBarMessages.tryEmit("Failed to sideload firmware: no connected watch")\n                SystemFileSystem.delete(file, mustExist = false)\n                return@launch')

    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt', 'import kotlinx.coroutines.sync.Semaphore\nimport kotlinx.coroutines.sync.withPermit\n', '')
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt', '    private val importLock = Semaphore(1)\n', '')
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt', 'try { importLock.withPermit { handleNow(uri) } }', 'try { handleNow(uri) }')

    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/locker/Locker.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/locker/Locker.kt', 'logger.w { "Not opening ${entry.title}\'s config page: ${verdict.reason}" }', 'logger.w { "Config page refused host=${safeLogHost(page)}" }', expect=1)
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/locker/Locker.kt', 'logger.w { "Blocked $title\'s config page loading $url: ${verdict.reason}" }', 'logger.w { "Config request refused host=${safeLogHost(url)}" }', expect=1)
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt', 'logger.w { "$appUuid blocked: ${verdict.reason}" }', 'logger.w { "WebSocket refused host=${safeLogHost(url)}" }', expect=1)
    replace_literal('libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt', 'logger.w { "Blocked ${url.host}: ${verdict.reason}" }', 'logger.w { "PKJS request refused host=${safeLogHost(url.toString())}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerAppScreen.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerAppScreen.kt', 'logger.w(e) { "Failed to open URL: $url" }', 'logger.w { "Browser open failed host=${safeLogHost(url)}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/ui/LockerAppScreen.kt', 'logger.w { "Not opening invalid URL: $url" }', 'logger.w { "Browser URL refused host=${safeLogHost(url)}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt', 'logger.v { "${it.call.request.url}" }', 'logger.v { "Store response host=${safeLogHost(it.call.request.url.toString())}" }', expect=2)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt', 'logger.v { "fetchAppStoreHome fetching ${source.url}/v1/home/$typeString" }', 'logger.v { "Store home request host=${safeLogHost(source.url)}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt', 'logger.v { "get ${url} with parameters $parameters" }', 'logger.v { "Store request host=${safeLogHost(url)}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt', 'logger.w { "Failed to fetch home of type ${type.code}, status: ${it.status}, source = ${source.url}" }', 'logger.w { "Store home request failed host=${safeLogHost(source.url)}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreService.kt', 'logger.w(e)', 'logger.w', expect=12)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/weather/YahooWeatherInterceptor.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/weather/YahooWeatherInterceptor.kt', 'logger.w { "Unknown request: $url" }', 'logger.w { "Weather request refused host=${safeLogHost(url)}" }', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/weather/OpenWeather25Interceptor.kt', 'import co.touchlab.kermit.Logger', 'import io.rebble.libpebblecommon.util.safeLogHost\nimport co.touchlab.kermit.Logger', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/weather/OpenWeather25Interceptor.kt', 'logger.w { "Unknown request: $url" }', 'logger.w { "Weather request refused host=${safeLogHost(url)}" }', expect=1)
    replace_literal('pebble/src/iosMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.ios.kt', 'logger.i { "Failed to get security-scoped access for file URI: $uri. Will attempt direct access." }', 'logger.i { "File import: scoped access unavailable" }', expect=1)
    replace_literal('pebble/src/iosMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.ios.kt', 'logger.w { "NSURL path is null for URI: $uri after attempting security scope access." }', 'logger.w { "File import: path unavailable" }', expect=1)
    replace_literal('pebble/src/iosMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.ios.kt', 'logger.w { "File does not exist at security-scoped path: $sourcePath for URI: $uri" }', 'logger.w { "File import: file unavailable" }', expect=1)
    replace_literal('pebble/src/iosMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.ios.kt', 'logger.e(e) { "Error writing file for $uri" }', 'logger.e { "File import failed" }', expect=1)


def harden_config_pages_and_archives() -> None:
    screen = 'pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.kt'
    android = 'pebble/src/androidMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.android.kt'
    ios = 'pebble/src/iosMain/kotlin/coredevices/pebble/ui/WatchappSettingsScreen.ios.kt'
    pkjs = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/PKJSApp.kt'
    runner = 'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/js/WebViewJsRunner.kt'

    # The message listener saves a snapshot on Main. Updating native Storage.length is unnecessary.
    replace_literal(android, """\
    val localStorageInterface = WebViewJSLocalStorageInterface("$uuid-config", AppContext(context)) {
        runBlocking(Dispatchers.Main) {
            evaluateJavascript(
                it,
                null
            )
        }
    }""", """\
    val localStorageInterface = WebViewJSLocalStorageInterface(
        "$uuid-config", AppContext(context), coredevices.pebble.config.configStorageLengthChanged,
    )""", expect=1)
    for path in (screen, android, ios):
        replace_literal(path, 'fun persistLocalStorage(webView: NativeWebView)',
                        'suspend fun persistLocalStorage(webView: NativeWebView)', expect=1)
    replace_literal(screen, "        // Leaves the page for the linked app's page in the locker. Called on the main thread, which\n        // persistLocalStorage blocks on.",
                    "        // Save storage before leaving for the linked app's page in the locker.", expect=1)
    replace_literal(android, '    runBlocking(Dispatchers.Main) {', '    withContext(Dispatchers.Main) {', expect=1)
    replace_literal(android, 'import kotlinx.coroutines.runBlocking\n', '', expect=1)
    # PKJS still uses the Java bridge thread, but neither length updates nor restore need to block it.
    replace_literal(runner, """\
    private val localStorageInterface = WebViewJSLocalStorageInterface(appInfo.uuid, appContext) {
        runBlocking(Dispatchers.Main) {
            webView?.evaluateJavascript(
                it,
                null
            )
        }
    }""", """\
    private val localStorageInterface = WebViewJSLocalStorageInterface(appInfo.uuid, appContext) { js ->
        nativeEvals.trySend(js)
    }""", expect=1)
    replace_literal(runner, '    private fun restoreLocalStorage() {\n        runBlocking(Dispatchers.Main) {',
                    '    private suspend fun restoreLocalStorage() {\n        withContext(Dispatchers.Main) {', expect=1)

    # End return_to with the separator used by pages that append encodeURIComponent(settings).
    replace_literal(pkjs, '"pebblejs://close?orb_state=$state"', '"pebblejs://close?orb_state=$state#"', expect=1)
    replace_literal(pkjs, '    fun closeExternalConfig(state: String?, data: String): Boolean {',
                    '    fun consumeConfigState(state: String): Boolean = externalConfig.consume(state)\n\n'
                    '    fun closeExternalConfig(state: String?, data: String): Boolean {', expect=1)
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/config/ConfigPageSession.kt',
                    '    /** Whatever the page put in its close URL. */',
                    '    fun consumeConfigState(state: String): Boolean = pkjs?.consumeConfigState(state) == true\n\n'
                    '    /** Whatever the page put in its close URL. */', expect=1)
    replace_literal(screen, 'import io.ktor.http.decodeURLPart',
                    'import io.rebble.libpebblecommon.js.ConfigCloseCallback\n'
                    'import io.rebble.libpebblecommon.js.isConfigCloseUrl\n'
                    'import io.rebble.libpebblecommon.js.parseConfigCloseUrl', expect=1)
    replace_literal(screen, '        val interceptor = remember {\n            SettingsRequestInterceptor(',
                    '        val interceptor = remember(url) {\n            SettingsRequestInterceptor(\n'
                    '                mayClose = { callback ->\n'
                    '                    coredevices.pebble.config.configPageMayComplete(\n'
                    '                        url, state.lastLoadedUrl, true, callback.state,\n'
                    '                    ) { session?.consumeConfigState(it) == true }\n'
                    '                },', expect=1)
    replace_literal(screen, 'private class SettingsRequestInterceptor(\n',
                    'internal class SettingsRequestInterceptor(\n'
                    '    private val mayClose: (ConfigCloseCallback) -> Boolean,\n', expect=1)
    replace_literal(screen, '    private val PREFIX = "pebblejs://close" // non-compliant intercept for close, because some apps just use "close"\n', '', expect=1)
    replace_literal(screen, '        if (!request.url.startsWith(PREFIX)) {',
                    '        if (!isConfigCloseUrl(request.url)) {', expect=1)
    replace_literal(screen, "        // Matches PREFIX followed by #, /, or /? \n"
                    r'''        // Ideally all apps would send pebblejs://close#param1=value1&param2=value2 but it's not the case.
        // The original Pebble Technology Corp App did deviate from the official spec and handled these wrong cases too.
        val closeUrlRegex = Regex("""^pebblejs://close(?:#|/\?|/)(.*)$""")

        val data = closeUrlRegex.find(request.url)?.groupValues?.get(1)?.decodeURLPart()''',
                    '''        if (!request.isForMainFrame) return WebRequestInterceptResult.Reject
        val callback = parseConfigCloseUrl(request.url) ?: return WebRequestInterceptResult.Reject
        if (!mayClose(callback)) return WebRequestInterceptResult.Reject
        val data = callback.data''', expect=1)
    replace_literal(screen, '        if (data?.isNotEmpty() == true) {', '        if (data.isNotEmpty()) {', expect=1)
    deep_link = 'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt'
    replace_literal(deep_link, '                val data = uri.encodedFragment ?: return false\n'
                    '                val state = uri.getQueryParameter("orb_state") ?: return false',
                    '                val callback = io.rebble.libpebblecommon.js.parseConfigCloseUrl(uri.toString()) ?: return false\n'
                    '                val data = callback.data\n'
                    '                val state = callback.state ?: return false', expect=1)

    # Keep the storage's origin with it, and guard both sides of the asynchronous JS injection.
    replace_literal(android, 'configStorage[this] = localStorageInterface',
                    'configStorage[this] = localStorageInterface to expectedOrigin', expect=1)
    replace_literal(android, 'java.util.WeakHashMap<WebView, WebViewJSLocalStorageInterface>()',
                    'java.util.WeakHashMap<WebView, Pair<WebViewJSLocalStorageInterface, String?>>()', expect=1)
    replace_literal(android, '''        val saved = configStorage[webView]?.restoreState() ?: "{}"
        webView.evaluateJavascript("""
            (function() {
                // Storage is disabled inside data: URLs, which a plugin's config page is.
                try { window.localStorage.clear(); } catch (e) { return; }
                const localStorageData = JSON.parse(${Json.encodeToString(saved)});
                for (const [key, value] of Object.entries(localStorageData)) {
                    window.localStorage.setItem(key, value);
                }
            })();
                """.trimIndent(), null
        )''', '''        val (storage, origin) = configStorage[webView] ?: return@withContext
        // evaluateJavascript targets only the main frame; data: documents have no storage origin.
        if (!coredevices.pebble.config.configPageMayRestoreStorage(origin, webView.url, true)) return@withContext
        webView.evaluateJavascript(
            coredevices.pebble.config.configStorageRestoreScript(origin!!, storage.restoreState()), null,
        )''', expect=1)
    replace_literal(android, '''internal actual suspend fun persistLocalStorage(webView: NativeWebView) {
    withContext(Dispatchers.Main) {
        webView.evaluateJavascript("""
            (function() {
                const data = {};''', '''internal actual suspend fun persistLocalStorage(webView: NativeWebView) {
    withContext(Dispatchers.Main) {
        val (_, origin) = configStorage[webView] ?: return@withContext
        if (!coredevices.pebble.config.configPageMayRestoreStorage(origin, webView.url, true)) return@withContext
        webView.evaluateJavascript("""
            (function() {
                if (window !== window.top || location.origin !== ${Json.encodeToString(origin)}) return;
                const data = {};''', expect=1)

    # Bound inflated bytes before allocating strings or invoking a JSON decoder.
    pbw = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/disk/pbw/DiskUtil.kt'
    pbz = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/disk/pbz/DiskUtil.kt'
    for path in (pbw, pbz):
        replace_literal(path, 'import kotlinx.io.readString',
                        'import io.rebble.libpebblecommon.disk.MAX_ZIP_JSON_BYTES\n'
                        'import io.rebble.libpebblecommon.disk.readStringBounded', expect=1)
    replace_literal(pbw, 'import kotlinx.io.RawSource',
                    'import io.rebble.libpebblecommon.disk.MAX_ZIP_TEXT_BYTES\nimport kotlinx.io.RawSource', expect=1)
    replace_literal(pbw, 'pbwJson.decodeFromString(source.readString())',
                    'pbwJson.decodeFromString(source.readStringBounded(MAX_ZIP_JSON_BYTES))', expect=1)
    replace_literal(pbw, 'source.use { it.readString() }',
                    'source.use { it.readStringBounded(MAX_ZIP_JSON_BYTES) }', expect=1)
    replace_literal(pbw, '.use { it.readString() }',
                    '.use { it.readStringBounded(MAX_ZIP_TEXT_BYTES) }', expect=1)
    replace_literal(pbz, 'it.readString()', 'it.readStringBounded(MAX_ZIP_JSON_BYTES)', expect=1)

    # Never retain URL-bearing reasons, server text, exception messages or stack traces in PKJS logs.
    xhr = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/XMLHTTPRequestManager.kt'
    for old, category in (
        ('logger.w { "$appUuid blocked: ${verdict.reason}" }', 'REFUSED'),
        ('logger.w { "$appUuid blocked redirect: ${e.message}" }', 'REDIRECT_REFUSED'),
        ('logger.e { "Request timed out: ${e.message}" }', 'TIMED_OUT'),
        ('logger.e(e) { "Request (size ${data?.size}) failed: ${e.message}" }', 'FAILED'),
        ('logger.e(e) { "Failed to serialize response headers: ${e.message}" }', 'HEADERS_FAILED'),
        ('logger.e(e) { "Response has charset errors: ${e.message}. Decoding as UTF-8 with replacements" }', 'CHARSET_INVALID'),
        ('logger.e { "Invalid response type: $responseType" }', 'RESPONSE_TYPE_INVALID'),
        ('logger.e(e) { "Failed to read response body (type $responseType): ${e.message}" }', 'BODY_FAILED'),
    ):
        replace_literal(xhr, old, 'logger.w { pkjsNetworkLog(PkjsNetworkLogCategory.' + category + ', url) }', expect=1)
    replace_literal(xhr, 'logger.v { "XHR Response: ${response.status.value} ${response.status.description}" }',
                    'logger.v { "XHR response status=${response.status.value}" }', expect=1)
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt',
                    'logger.w { "watchapp websocket failed" }',
                    'logger.w { pkjsNetworkLog(PkjsNetworkLogCategory.FAILED, url) }', expect=1)
    replace_literal(runner, '''            logger.e {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    "Error loading page: ${error?.errorCode} ${error?.description}"
                } else {
                    "Error loading page: ${error?.toString()}"
                }
            }''', '            logger.w { pkjsNetworkLog(PkjsNetworkLogCategory.PAGE_FAILED, request?.url?.toString().orEmpty()) }', expect=1)
    replace_literal(runner, 'logger.w { "Blocking access to file: ${url.path}" }',
                    'logger.w { pkjsNetworkLog(PkjsNetworkLogCategory.REFUSED, url.toString()) }', expect=1)


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
    # The upload classes and their serial helper are in REMOVED. The
    # library drops non-health system data before parsing it (remove_library_telemetry()).
    # drop_core_telemetry_tables() also removes the old on-phone queues.
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
    for method in ("uploadMemfaultChunk", "uploadAnalyticsHeartbeat"):
        remove_kotlin_block(web_services, rf"^    override fun {method}\(")

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
    edit(
        "libpebble3/src/androidHostTest/kotlin/io/rebble/libpebblecommon/notification/NotificationDecisionTest.kt",
        r'notification\("coredevices\.coreapp", "Test Notification"',
        f'notification("{APPLICATION_ID}", "Test Notification"',
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
    remove_crashlytics()
    remove_cloud_locker()
    remove_core_account()
    remove_firebase()
    remove_analytics()
    remove_sync_manager()
    remove_release_additions()
    remove_library_telemetry()
    remove_dead_leftovers()
    harden_release_manifest()
    remove_help_page()
    remove_debug_receivers()
    remove_qa_flag()
    block_cleartext()
    set_backup_rules()
    drop_core_telemetry_tables()
    remove_google_fit()
    fit_delegate_call()
    harden_orb_release()
    harden_config_pages_and_archives()
    fix_recovery_pebblekit_and_release_checks()

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


def fix_recovery_pebblekit_and_release_checks() -> None:
    """Keep review fixes reproducible after restoring the pinned Core checkout."""
    manifest = "androidApp/src/main/AndroidManifest.xml"
    edit(manifest, r'^                <data android:scheme="file" />\n', '', expect=2)

    fw = "libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/endpointmanager/FirmwareUpdater.kt"
    replace_literal(fw, 'if (!pinned && update.version < fwupProps.runningFwVersion)',
                    'if (!pinned && !fwupProps.runningFwVersion.isRecovery && update.version < fwupProps.runningFwVersion)')
    replace_literal(fw, 'import io.rebble.libpebblecommon.web.FirmwareDownloader',
                    'import io.rebble.libpebblecommon.web.discardFirmwareDownload\nimport io.rebble.libpebblecommon.web.FirmwareDownloader')
    replace_literal(fw, '''    fun record(identifier: PebbleIdentifier, install: FirmwareInstall, reason: Reason = Reason.Interrupted) =
        pending.update { it + (identifier to Pending(install, reason)) }

    fun clear(identifier: PebbleIdentifier) = pending.update { it - identifier }''', '''    fun record(identifier: PebbleIdentifier, install: FirmwareInstall, reason: Reason = Reason.Interrupted) {
        val previous = pending.value[identifier]?.install
        pending.update { it + (identifier to Pending(install, reason)) }
        if (previous != null && previous.path != install.path && previous.update.url.isNotEmpty()) {
            discardFirmwareDownload(previous.path)
        }
    }

    fun clear(identifier: PebbleIdentifier) {
        val removed = pending.value[identifier]?.install
        pending.update { it - identifier }
        if (removed != null && removed.update.url.isNotEmpty()) discardFirmwareDownload(removed.path)
    }''')
    # The next PRF connection still needs the bundle. Clearing it is abandonment only on failure.
    replace_literal(fw, '''                pendingInstalls.clear(identifier)
                if (runningFwVersion.isRecovery) {''', '''                if (runningFwVersion.isRecovery) {''')
    replace_literal(fw, '''                    continueInPrf(pending.install)
                } else {''', '''                    continueInPrf(pending.install)
                } else {
                    pendingInstalls.clear(identifier)''')
    replace_literal(fw, '''            if (route !is InstallRoute.Direct) {
                _firmwareUpdateState''', '''            if (route !is InstallRoute.Direct) {
                pendingInstalls.clear(identifier)
                _firmwareUpdateState''')
    replace_literal(fw, '''                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    logger.w(e) { "Failed to parse firmware: ${e.message}" }''', '''                } catch (e: CancellationException) {
                    discardFirmwareDownload(path)
                    throw e
                } catch (e: Exception) {
                    discardFirmwareDownload(path)
                    logger.w(e) { "Failed to parse firmware: ${e.message}" }''')
    replace_literal(fw, '''            if (route == null) {
                _firmwareUpdateState''', '''            if (route == null) {
                pendingInstalls.clear(identifier)
                _firmwareUpdateState''')
    replace_literal(fw, '''           _firmwareUpdateState.value = FirmwareUpdateStatus.NotInProgress.Idle(e, trigger)
        }
    }

    private suspend fun determineResumeOffsets''', '''           _firmwareUpdateState.value = FirmwareUpdateStatus.NotInProgress.Idle(e, trigger)
        } finally {
            // Metadata may survive for a resumed transfer or failed boot; the next attempt can
            // re-download. Only the reboot-into-PRF handoff needs to keep the actual bundle.
            if (install.update.url.isNotEmpty()) discardFirmwareDownload(install.path)
        }
    }

    private suspend fun determineResumeOffsets''')
    lang = "libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/connection/endpointmanager/LanguagePackInstaller.kt"
    replace_literal(lang, '            logger.d { "installLanguagePack() $path" }', '''            try {
            logger.d { "installLanguagePack() $path" }''')
    replace_literal(lang, '''                source.close()
            }
        }
    }
}''', '''                source.close()
            }
            } finally {
                if (sideloadPath == null) io.rebble.libpebblecommon.web.discardFirmwareDownload(path)
            }
        }
    }
}''')

    ws = 'libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/js/WebSocketManager.kt'
    replace_literal(ws, '        private val job = atomic<Job?>(null)', '''        private val job = atomic<Job?>(null)
        private val overflow = atomic(false)''')
    replace_literal(ws, '''                eval("$js._onClose($ABNORMAL_CLOSURE, '', false)")
                throw e''', '''                if (overflow.value) fail() else eval("$js._onClose($ABNORMAL_CLOSURE, '', false)")
                throw e''')
    replace_literal(ws, '            outgoing.trySend(frame)', '            enqueue(frame)')
    replace_literal(ws, '            outgoing.trySend(Frame.Close(CloseReason(code.toShort(), reason)))',
                    '            enqueue(Frame.Close(CloseReason(code.toShort(), reason)))')
    replace_literal(ws, '        fun cancel() {', '''        private fun enqueue(frame: Frame) {
            if (outgoing.trySend(frame).isFailure && overflow.compareAndSet(false, true)) {
                // Bridge calls cannot suspend. Fail the entire stream instead of losing a frame.
                outgoing.close()
                session.value?.cancel()
                job.value?.cancel()
            }
        }

        fun cancel() {''')

    sender = 'libpebble3/src/androidMain/kotlin/io/rebble/libpebblecommon/pebblekit/two/PebbleSenderReceiver.kt'
    replace_literal(sender, '''                    val result = runOnConnectedWatches(targets) { watch ->
                        if (!allowed) TransmissionResult.FailedNoPermissions
                        else {''', '''                    val result = io.rebble.libpebblecommon.pebblekit.companionResults(allowed) {
                        runOnConnectedWatches(targets) { watch ->''')
    replace_literal(sender, '''        return runOnConnectedWatches(watches) { watch ->
            val companionApp''', '''        return io.rebble.libpebblecommon.pebblekit.companionResults(
            isAllowedToCommunicate(callingPackage, watchappUUID)
        ) { runOnConnectedWatches(watches) { watch ->
            val companionApp''')
    replace_literal(sender, '''            companionApp.sendMessage(data)
        }
''', '''            companionApp.sendMessage(data)
        } }
''')
    # The base entry points have no caller identity; the onBind wrapper handles authorized calls.
    replace_literal(sender, '''        return runOnConnectedWatches(watches) {
            TransmissionResult.FailedNoPermissions
        }''', '''        return emptyMap()''', expect=2)

    replace_literal('util/src/androidMain/kotlin/PlatformShareLauncher.android.kt', 'type = "audio/wav"', 'type = "application/zip"')
    replace_literal('pebble/src/commonMain/kotlin/coredevices/pebble/ui/PluginsHelpCard.kt',
                    'data to watchfaces, apps, and the Index Agent. ', 'data to watchfaces and apps. ')
    removed_permissions = r'(?:SET_INDEX_ALARMS|SEND_MESSAGES_BEEPER|WRITE_INDEX_NOTES|WRITE_INDEX_REMINDERS)'
    edit('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/plugin/PluginPermissions.kt',
         r'^    const val ' + removed_permissions + r' = .*\n', '', expect=4)
    edit('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/PermissionRegistry.kt',
         r'^        PermissionDefinition\(PluginPermissions\.' + removed_permissions + r', .*\n', '', expect=4)
    edit('pebble/src/commonMain/kotlin/coredevices/pebble/ui/InstallReview.kt',
         r'^    PluginPermissions\.' + removed_permissions + r' -> .*\n', '', expect=8)
    # Permission names are strings in storage; unknown names already parse and fail closed.

    nav = 'composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/AppNavHost.kt'
    remove_kotlin_block(nav, r'^                scope.launch \{(?=\n                    deepLinks.navigateToDeepLink.collect)')
    edit(nav, r'^    val deepLinks: CoreDeepLinkHandler = koinInject\(\)\n', '')
    replace_literal(nav, '''        composable<CommonRoutes.BugReport>(
            deepLinks = listOf(
                NavDeepLink("pebblecore://deep-link/bug-report?pebble={pebble}&context={context}&text={text}")
            )
        ) {''', '''        composable<CommonRoutes.BugReport> {''')
    for path in ('composeApp/src/androidMain/kotlin/coredevices/coreapp/MainActivity.kt',
                 'composeApp/src/iosMain/kotlin/coredevices/coreapp/IOSDelegateShortcuts.kt',
                 'composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt'):
        edit(path, r'^import coredevices.coreapp.ui.navigation.CoreDeepLinkHandler\n', '')
    activity = 'composeApp/src/androidMain/kotlin/coredevices/coreapp/MainActivity.kt'
    edit(activity, r'^    private val coreDeepLinkHandler: CoreDeepLinkHandler by inject\(\)\n', '')
    edit(activity, r'^            coreDeepLinkHandler.handle\(it\)\n', '')
    edit('composeApp/src/commonMain/kotlin/coredevices/coreapp/di/utilModule.kt', r'^    singleOf\(::CoreDeepLinkHandler\)\n', '')
    (APP / 'composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandler.kt').unlink()
    dead_test = APP / 'composeApp/src/commonTest/kotlin/coredevices/coreapp/ui/navigation/CoreDeepLinkHandlerTest.kt'
    if sha256(dead_test) != 'cd116f99cce317aa67d5e339cc2769e2c663899333fd7f70b3d4a091c4286e42':
        raise ApplyError('Core deep-link tests changed; review removed routes')
    dead_test.unlink()

    source_ui = 'pebble/src/commonMain/kotlin/coredevices/pebble/ui/AppstoreSettingsScreen.kt'
    replace_literal(source_ui, '''parsedUrl.protocolOrNull in setOf(URLProtocol.HTTP, URLProtocol.HTTPS)''',
                    '''parsedUrl.protocolOrNull == URLProtocol.HTTPS''')
    replace_literal(source_ui, 'label = { Text("Source URL") }', 'label = { Text("Source URL (HTTPS)") }')
    deep = 'pebble/src/commonMain/kotlin/coredevices/pebble/PebbleDeepLinkHandler.kt'
    replace_literal(deep, '''            if (name.isBlank() || url.isBlank()) return null''',
                    '''            if (name.isBlank() || !coredevices.pebble.services.validSourceUrl(url)) return null''')
    dao = 'util/src/commonMain/kotlin/coredevices/database/AppstoreSource.kt'
    replace_literal(dao, '    @Query("SELECT * FROM AppstoreSource")', '''    @Query("UPDATE AppstoreSource SET url = 'https://' || substr(url, 8) WHERE lower(substr(url, 1, 7)) = 'http://'")
    suspend fun upgradeHttpSources(): Int

    @Query("SELECT * FROM AppstoreSource")''')
    sources = 'pebble/src/commonMain/kotlin/coredevices/pebble/services/AppstoreSources.kt'
    replace_literal(sources, '''        val current = appstoreSourceDao.getAllSources().first()''', '''        // Idempotent: each persisted HTTP row is upgraded once, keeping its id and settings.
        if (appstoreSourceDao.upgradeHttpSources() > 0) appstoreCache.clearCache()
        val current = appstoreSourceDao.getAllSources().first()''')


    tracker = 'pebble/src/commonMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateUiTracker.kt'
    replace_literal(tracker, '    fun updateWatchNow(libPebble: LibPebble, identifier: String)',
                    '    fun updateWatchNow(libPebble: LibPebble, identifier: String, expectedVersion: String? = null)')
    replace_literal(tracker, 'override fun updateWatchNow(libPebble: LibPebble, identifier: String)',
                    'override fun updateWatchNow(libPebble: LibPebble, identifier: String, expectedVersion: String?)')
    replace_literal(tracker, 'if (update !is FirmwareUpdateCheckResult.FoundUpdate) {',
                    'if (update !is FirmwareUpdateCheckResult.FoundUpdate ||\n            (expectedVersion != null && update.version.stringVersion != expectedVersion)) {')
    replace_literal(tracker, '''            showUpdateAction = true,
''', '''            showUpdateAction = true,
            version = update.version.stringVersion,
''')
    replace_literal(tracker, 'private fun notify(title: String, body: String, key: Int, identifier: PebbleIdentifier, showUpdateAction: Boolean)',
                    'private fun notify(title: String, body: String, key: Int, identifier: PebbleIdentifier, showUpdateAction: Boolean, version: String? = null)')
    replace_literal(tracker, 'notifyFirmwareUpdate(appContext, title, body, key, identifier, showUpdateAction)',
                    'notifyFirmwareUpdate(appContext, title, body, key, identifier, showUpdateAction, version)')
    # All expect/actual declarations carry the advertised version to the Android PendingIntent.
    for path in (tracker,
                 'pebble/src/androidMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateUiTracker.android.kt',
                 'pebble/src/iosMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateUiTracker.ios.kt'):
        replace_literal(path, '    showUpdateAction: Boolean,\n)', '    showUpdateAction: Boolean,\n    version: String?,\n)')
    android_tracker = 'pebble/src/androidMain/kotlin/coredevices/pebble/firmware/FirmwareUpdateUiTracker.android.kt'
    edit(android_tracker, r'^import coredevices.pebble.RealPebbleDeepLinkHandler.Companion.updateNowUri\n', '')
    edit(android_tracker, r'^import android.app.PendingIntent.FLAG_MUTABLE\n', '')
    edit(android_tracker, r'^import android.app.PendingIntent.FLAG_UPDATE_CURRENT\n', '')
    edit(android_tracker, r'^    val updatePhoneIntent = context.packageManager.getLaunchIntentForPackage\(context.packageName\)\n(?:.*\n)*?(?=    val builder = NotificationCompat.Builder)', '''    val broadcastIntent = Intent(context, UpdateActionReceiver::class.java).apply {
        // A unique identity per watch and advertised version prevents another offer replacing it.
        data = android.net.Uri.Builder().scheme("orb-internal").authority("firmware")
            .appendPath(identifier.asString).appendPath(version.orEmpty()).build()
        putExtra(EXTRA_WATCH_IDENTIFIER, identifier.asString)
        putExtra(EXTRA_VERSION, version)
    }
    val updateIntent = PendingIntent.getBroadcast(context, 0, broadcastIntent, PendingIntent.FLAG_IMMUTABLE)
''')
    replace_literal(android_tracker, 'updatePhonePendingIntent', 'updateIntent')
    replace_literal(android_tracker, 'updateIntentWatch', 'updateIntent')
    replace_literal(android_tracker, '.setShowsUserInterface(true)', '.setShowsUserInterface(false)')
    replace_literal(android_tracker, 'private const val EXTRA_WATCH_IDENTIFIER = "IDENTIFIER"',
                    'private const val EXTRA_WATCH_IDENTIFIER = "IDENTIFIER"\nprivate const val EXTRA_VERSION = "VERSION"')
    replace_literal(android_tracker, '''        val identifier = intent.getStringExtra(EXTRA_WATCH_IDENTIFIER)''',
                    '''        val version = intent.getStringExtra(EXTRA_VERSION) ?: return
        val identifier = intent.getStringExtra(EXTRA_WATCH_IDENTIFIER)''')
    replace_literal(android_tracker, 'firmwareUpdateUiTracker.updateWatchNow(libPebble, identifier)',
                    'firmwareUpdateUiTracker.updateWatchNow(libPebble, identifier, version)')
    replace_literal(android_tracker, 'Firmware udpate notifications', 'Firmware update notifications')

    preview = 'pebble/src/commonMain/kotlin/coredevices/pebble/ui/PreviewUtil.kt'
    replace_literal(preview, '''            identifier: String
        ) {''', '''            identifier: String,
            expectedVersion: String?,
        ) {''')
    replace_literal(preview, '''    val storeSourceDao = object : AppstoreSourceDao {''', '''    val storeSourceDao = object : AppstoreSourceDao {
        override suspend fun upgradeHttpSources(): Int = 0''')
    replace_literal(ws, '''                eval("$js._onClose($code, ${Json.encodeToString(reason?.message.orEmpty())}, true)")''',
                    '''                if (overflow.value) fail()
                else eval("$js._onClose($code, ${Json.encodeToString(reason?.message.orEmpty())}, true)")''')
    # The dialog and deep-link path enforce the same HTTPS-only source policy.
    replace_literal(source_ui, '''    val parsedUrl = parseUrl(normalizedUrl)
    // Feed urls are concatenated into request paths, so anything past the path is a broken source.
    val urlValid = parsedUrl != null &&
            parsedUrl.protocolOrNull == URLProtocol.HTTPS &&
            parsedUrl.encodedQuery.isEmpty() &&
            parsedUrl.fragment.isEmpty() &&
            normalizedUrl !in existingUrls''', '''    val urlValid = coredevices.pebble.services.validSourceUrl(normalizedUrl) &&
            normalizedUrl !in existingUrls''')
    # Staged catalog language downloads use the same owned-temp-file lifecycle as URL installs.
    repository = 'pebble/src/commonMain/kotlin/coredevices/pebble/services/LanguagePackRepository.kt'
    replace_literal(repository, 'val directory = getLockerPBWCacheDirectory(appContext)',
                    'val directory = io.rebble.libpebblecommon.web.getFirmwareDownloadDirectory(appContext)')
    replace_literal(repository, 'val path = Path(directory, "language.pbl")',
                    'val path = Path(directory, "download-${kotlin.uuid.Uuid.random()}.pbl")')
    replace_literal(lang, 'if (sideloadPath == null) io.rebble.libpebblecommon.web.discardFirmwareDownload(path)',
                    'firmwareDownloader.discardDownload(path)')

    socket_test = 'libpebble3/src/commonTest/kotlin/io/rebble/libpebblecommon/js/WebSocketManagerTest.kt'
    replace_literal(socket_test, '    private val internet =', '    @Test\n    fun overflowingTheOutgoingQueueReportsErrorAndCloses() = runTest {\n        val client = HttpClient(MockEngine { awaitCancellation() }) { install(WebSockets) }\n        val evals = mutableListOf<String>()\n        val manager = WebSocketManager(this, { evals.add(it) }, client, Uuid.random(), internet, { _, _, _, _, _ -> })\n        manager.dispatch("createInstance", listOf("wss://stream.example.com/", ""))\n        runCurrent()\n        repeat(65) { manager.dispatch("send", listOf(1, "frame", false)) }\n        awaitSockets()\n        assertEquals(listOf("$INSTANCE._onError()", ABNORMAL_CLOSE), evals)\n        client.close()\n    }\n\n    private val internet =')

    # A companion removed by an app update must lose its persisted association too.
    replace_literal('libpebble3/src/commonMain/kotlin/io/rebble/libpebblecommon/permissions/AppPermissions.kt',
                    '        val all = requested.all', '        val all = requested.all\n        val removedCompanions = dao.getByAppUuid(appUuid).map { it.permission }.filter {\n            permissionOf(it) == PluginPermissions.PEBBLEKIT_2 && it !in all\n        }\n        if (removedCompanions.isNotEmpty()) dao.deleteByAppUuidAndPermissions(appUuid, removedCompanions)')

    edit(deep, r'^        fun updateNowUri\(identifier: PebbleIdentifier\): Uri = .*\n', '')
    replace_literal(deep, 'SHOW_WATCHES_HOST -> handleShowWatches(uri.path)', 'SHOW_WATCHES_HOST -> handleShowWatches()')
    replace_literal(deep, 'private fun handleShowWatches(path: String?)', 'private fun handleShowWatches()')

    replace_literal(lang, '        if (_state.value !is LanguagePackInstallState.Idle) {\n            return\n        }', '        if (_state.value !is LanguagePackInstallState.Idle) {\n            sideloadPath?.let(firmwareDownloader::discardDownload)\n            return\n        }')
    replace_literal(lang, '                firmwareDownloader.discardDownload(path)\n            }\n        }\n    }\n}', '                firmwareDownloader.discardDownload(path)\n            }\n        }.invokeOnCompletion {\n            // Also covers a connection scope cancelled before the install coroutine starts.\n            sideloadPath?.let(firmwareDownloader::discardDownload)\n        }\n    }\n}')

def fit_delegate_call() -> None:
    """Core passes PebbleAppDelegate's dependencies positionally; Orb's removals leave 18."""
    edit("pebble/src/commonMain/kotlin/coredevices/pebble/watchModule.kt",
         r"PebbleAppDelegate\((?:get\(\), ){22}get\(\)\)",
         "PebbleAppDelegate(" + ", ".join(["get()"] * 18) + ")")


def reset() -> None:
    # The submodule's Git directory can live outside this worktree. Restore files with a
    # temporary index here, without writing shared Git metadata or moving HEAD.
    with tempfile.TemporaryDirectory(prefix=".orb-reset-", dir=ROOT) as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        for args in (("read-tree", "HEAD"), ("checkout-index", "--all", "--force"),
                     ("clean", "-fd")):
            subprocess.run(["git", "-C", str(APP), *args], env=env, check=True,
                           capture_output=True, text=True)


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
