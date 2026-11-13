# Orb for Pebble

An unofficial build of the [Pebble mobile app by Core Devices](https://github.com/coredevices/mobileapp)
for Android phones without Google Play services. GrapheneOS is the primary target.

Orb for Pebble is not affiliated with or endorsed by Core Devices. Pebble is a trademark of
Core Devices LLC; the name is used here only to say which watches the app works with.

## Status

Early. Builds from Core's 1.18.0.1 release; the debug and release builds start on an Android 16
emulator without Google services. It has not yet been run against a watch, and dictation
through the system recognizer has not been tested with any recognizer app.

## What it is

Orb is Core's app with the Google and binary-only parts taken out, and as little else changed
as possible. It is not a rewrite and adds no features of its own beyond what is needed to
replace something that was removed.

Removed, compared with the official app:

- Firebase (sign-in, Firestore, Storage, Crashlytics), Google sign-in, Google Play in-app
  updates and Firebase Cloud Messaging. There is no Core account in Orb, so nothing that needs
  one works: cloud locker sync, submitting bug reports to Core, battery history, cloud speech
  recognition. Orb hides the settings for these. Bug reports can still be saved and shared as
  a file.
- Mixpanel analytics.
- The Cactus speech engine, which is shipped only as a prebuilt binary.
- The Index 01 ring's radio library, which has no public source. Core's ring code is still
  compiled, but no ring can be found or paired, and Orb hides the option to add one.
- The health library's Google Fit fallback. Health Connect is still used where the phone has it.

Replaced:

- PebbleOS updates for watches made by Core come from Core's public releases on GitHub, since
  Core's update server answers only signed-in accounts. Orb offers the newest release that
  passes its checks: not a draft or pre-release, a bundle for the watch's board with a
  published SHA-256 digest, a download that matches it, and manifests naming that board and
  version with matching CRCs. If the newest fails, Orb tries the next older one that is still
  newer than what the watch runs. A specific version can be pinned under Settings → Debug
  (shown after turning on "Show debug options"). Older Pebble watches still update from Rebble.
- Dictation uses the phone's speech recognition service: whichever recognizer app is installed
  and selected. Choose "System (On-Device)" under speech settings. This needs Android 13 or
  newer and a recognizer app that accepts recorded audio.

Orb declares the same PebbleKit providers as the official app, so Android will not install it
next to the official app or another fork of it. Uninstall those first.

## How it is built

This repository does not contain Core's source. It pins it, and holds the changes:

| Path | What it is |
|---|---|
| `mobileapp/` | Core's repository as a git submodule, pinned to a release tag |
| `overlay/` | Files copied over the checkout: stand-in modules under `overlay/orb/`, and the few Android files Orb replaces |
| `apply.py` | Applies the overlay and a list of small edits to a pristine checkout |
| `version.properties` | The Orb version built from the pinned tag |
| `tools/check_apk.py` | Fails if a built APK contains, or refers to, code Orb must not ship |
| `tools/fdroid_scan.sh` | Runs F-Droid's source scanner on a commit, as F-Droid's build server would |
| `tools/upstream.py` | Checks for and moves to new Core releases |
| `fdroid/` | Draft F-Droid build recipe |

`apply.py` checks every edit matched and every replaced file is the upstream version it was
written for, so a Core change that needs a human look stops the build instead of slipping
through.

The stand-in modules declare the same class names as the libraries they replace (the approach
comes from [Gravel](https://github.com/david-cant-code/pebble-app-degoogled)), which lets
Core's own code compile unmodified.

## Building

Needs JDK 17 or newer and the Android SDK.

```sh
git clone --recurse-submodules https://codeberg.org/Orb-Cybersecurity/orb-for-pebble.git
cd orb-for-pebble
echo "sdk.dir=/path/to/Android/Sdk" > mobileapp/local.properties
python3 apply.py
cd mobileapp
./gradlew :androidApp:assembleRelease
python3 ../tools/check_apk.py androidApp/build/outputs/apk/release/androidApp-release-unsigned.apk
```

`python3 apply.py --reset` restores `mobileapp/` to the pinned commit and applies again.

## Moving to a new Core release

`python3 tools/upstream.py status` compares the pinned tag with Core's newest one. A daily CI
job runs it and opens an issue when Core tags a release.

1. `python3 tools/upstream.py bump <tag>` pins the tag, sets `version.properties` to
   `<tag>-orb1`, and lists the replaced files Core changed, with the command to see each diff.
2. Port those changes into the overlay copies and update their hashes in `apply.py`.
3. Run `python3 apply.py --reset`, build, run `tools/check_apk.py` and `tools/fdroid_scan.sh`,
   and test on a phone before tagging `<tag>-orb1`.

If `apply.py` or the build fails, the message names what changed upstream.

## CI

`.forgejo/workflows/checks.yml` runs on Codeberg's hosted runners: `apply.py --check` on every
push and pull request, and the daily release check.

`.forgejo/workflows/build.yml` builds the APK, runs `tools/check_apk.py` and F-Droid's scanner,
and keeps the APK as an artifact. The build is too large for Codeberg's hosted runners, so it
needs a [Forgejo runner](https://forgejo.org/docs/latest/admin/actions/runner-installation/)
registered to this repository with the label `orb-android`. It runs on pushes to `main` and on
`*-orb*` tags only, never on pull requests. Give the runner its own unprivileged user account,
because workflow steps run with that user's access, and give that user:

- JDK 17 or newer (`JAVA_HOME`), the Android SDK (`ANDROID_HOME`), Python 3 and git;
- fdroidserver (`pip install fdroidserver`) on `PATH`;
- about 20 GB of disk for Gradle's caches.

## License

Orb for Pebble is free software under the GNU General Public License, version 3
(SPDX: GPL-3.0-only), the license of Core's app, which it is derived from. See `LICENSE`.

Core's code is copyright Core Devices and its contributors. The files in this repository are
copyright the Orb for Pebble authors and are offered under the same license. Core also sells
its code under a separate commercial license; that offer is Core's alone and does not extend
to Orb.
