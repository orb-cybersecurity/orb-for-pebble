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
    "experimental/src/androidMain/kotlin/coredevices/ring/database/firestore/dao/AggregateCount.android.kt":
        "f4a6756127386188a4db9ff9a4d3d679db0c8c1dcee9edef988eea6149f1ce7f",
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
    "Enable Index Feed",
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
    # Permissions that only the Index 01 ring, Core's on-device models or nothing at all use.
    # Each was checked against the release dex: no watch feature calls an API that needs it.
    # WAKE_LOCK stays because WorkManager takes wake locks itself.
    unused_permissions = (
        "android.permission.BLUETOOTH_ADVERTISE",
        "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
        "android.permission.REQUEST_OBSERVE_COMPANION_DEVICE_PRESENCE",
        "android.permission.RUN_USER_INITIATED_JOBS",
        "android.permission.SCHEDULE_EXACT_ALARM",
        "android.permission.USE_BIOMETRIC",
        "android.permission.USE_FINGERPRINT",
        "com.android.alarm.permission.SET_ALARM",
        "com.beeper.android.permission.READ_PERMISSION",
        "com.beeper.android.permission.SEND_PERMISSION",
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

    # Onboarding: Orb supports watches only and has no account to sign in to. Picking the
    # ring in Core's flow hides the only way past the sign-in page.
    onboarding = "composeApp/src/commonMain/kotlin/coredevices/coreapp/ui/screens/OnboardingScreen.kt"
    edit(
        onboarding,
        r"^([ \t]*)viewModel\.stage\.value = OnboardingStage\.DeviceSelection\n",
        r"\1viewModel.deviceChoice.value = DeviceChoice.Watch\n"
        r"\1viewModel.stage.value = OnboardingStage.Permissions\n",
    )
    edit(
        onboarding,
        r"viewModel\.stage\.value = OnboardingStage\.SignIn",
        "viewModel.stage.value = OnboardingStage.Done",
    )

    # Core's trademark rules leave "Pebble" only for saying which watches the app is for.
    edit(onboarding, r"^import coreapp\.composeapp\.generated\.resources\.pebble_logo\n", "")
    edit(
        onboarding,
        r"^([ \t]*)Image\(\n"
        r"[ \t]*painter = painterResource\(Res\.drawable\.pebble_logo\),\n"
        r'[ \t]*contentDescription = "description",\n'
        r"[ \t]*colorFilter = ColorFilter\.tint\(Color\.White\),\n"
        r"[ \t]*modifier = Modifier\.height\(50\.dp\),\n"
        r"[ \t]*\)\n",
        r'\1Text(text = "' + APP_LABEL + r'", fontSize = 44.sp, fontWeight = FontWeight.Bold, color = Color.White)' "\n"
        r'\1Text(text = "for Pebble watches", color = Color.White)' "\n",
    )
    pebble_service = "composeApp/src/androidMain/kotlin/coredevices/coreapp/PebbleService.kt"
    edit(pebble_service, r'NOTIFICATION_CHANNEL_NAME = "Pebble Service"', 'NOTIFICATION_CHANNEL_NAME = "Watch connection"')
    edit(pebble_service, r'\.setContentTitle\("Pebble"\)', f'.setContentTitle("{APP_LABEL}")')
    edit(
        pebble_service,
        r'\.setContentText\("Keeping Pebble connection alive"\)',
        '.setContentText("Keeping the watch connected")',
    )

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
    edit(
        "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchesScreen.kt",
        r"^[ \t]*if \(watch\.watchInfo\.platform\.isCoreDevice\(\)\) \{\n"
        r"[ \t]*DropdownMenuItem\(\n"
        r'[ \t]*text = \{ Text\("Battery Life"\) \},\n'
        r"(?:.*\n)*?"
        r"[ \t]*navBarNav\.navigateTo\(PebbleNavBarRoutes\.BatterySettingsRoute\)\n"
        r"[ \t]*\}\n[ \t]*\)\n[ \t]*\}\n",
        "",
    )

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

    # Orb has no driver for Core's Index 01 ring: its BLE library is binary-only.
    edit(
        "pebble/src/commonMain/kotlin/coredevices/pebble/ui/WatchesScreen.kt",
        r"^[ \t]*FloatingActionButtonMenuItem\(\n"
        r"[ \t]*onClick = \{\n"
        r"[ \t]*addFabExpanded = false\n"
        r"[ \t]*uiContext\?\.let \{ ctx ->\n"
        r"(?:.*\n)*?"
        r'[ \t]*text = \{ Text\("Add Index 01"\) \},\n'
        r"[ \t]*\)\n",
        "",
    )

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
