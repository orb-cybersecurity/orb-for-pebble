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

APPLICATION_ID = "org.codeberg.gaunkle.orb"
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
    "androidApp/src/google-services-dummy.json",
    "util/src/androidMain/ic_launcher-playstore.png",
    *(f"util/src/androidMain/res/mipmap-{d}/ic_launcher_foreground.webp"
      for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")),
]

# Catalog accessors of dependencies and plugins that must not be referenced at all.
DROPPED_ACCESSORS = (
    r"libs\.(?:firebase\.bom|firebase\.crashlytics(?:\.ndk)?|gms\.auth|identity\.google"
    r"|play\.update(?:\.ktx)?|crashkios|mixpanel\.android"
    r"|plugins\.googleServices|plugins\.firebaseCrashlytics)\b"
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


def edit(path: str, pattern: str, replacement: str, expect: int = 1) -> None:
    """Regex substitution in one file that must match exactly `expect` times."""
    file = APP / path
    text, count = re.subn(pattern, replacement, file.read_text(), flags=re.MULTILINE)
    if count != expect:
        raise ApplyError(f"{path}: expected {expect} match(es) of {pattern!r}, found {count}")
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
        if not target.exists():
            raise ApplyError(f"{path}: expected to remove it, but it is not there")
        shutil.rmtree(target) if target.is_dir() else target.unlink()

    shutil.copytree(OVERLAY, APP, dirs_exist_ok=True)

    # Build wiring.
    edit("settings.gradle.kts", r'^include\(":cactus-native"\)\n', "")
    with (APP / "settings.gradle.kts").open("a") as settings:
        settings.write('\napply(from = "orb/orb.settings.gradle.kts")\n')
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
    edit(
        "androidApp/src/main/res/values/strings.xml",
        r'<string name="app_name">Pebble</string>',
        f'<string name="app_name">{APP_LABEL}</string>',
    )
    # A checkout without a keystore packages the release unsigned, for stores that sign.
    edit(
        "androidApp/build.gradle.kts",
        r'signingConfig = signingConfigs\.getByName\("release"\)',
        'signingConfig = signingConfigs.getByName("release").takeIf { it.storeFile?.exists() == true }',
    )
    edit(
        "androidApp/build.gradle.kts",
        r'"proguard-rules\.pro"\)',
        '"proguard-rules.pro", "../orb/orb-proguard-rules.pro")',
    )

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

    # Core's "System" speech mode asks for this permission when selected. Android's speech
    # recognition service requires the microphone permission of its caller.
    edit(
        "util/src/androidMain/kotlin/coredevices/util/AndroidPermissionRequester.kt",
        r'Permission\.SpeechRecognizer -> throw IllegalArgumentException\("SpeechRecognizer not needed on Android"\)',
        "Permission.SpeechRecognizer -> listOf(Manifest.permission.RECORD_AUDIO)",
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
