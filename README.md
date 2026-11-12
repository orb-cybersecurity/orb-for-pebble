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
  one works: cloud locker sync, remote bug reports, cloud speech recognition.
- Mixpanel analytics.
- The Cactus speech engine, which is shipped only as a prebuilt binary.
- The Index 01 ring's radio library, which has no public source. Core's ring code is still
  compiled, but no ring can be found or paired.
- The health library's Google Fit fallback. Health Connect is still used where the phone has it.

Replaced:

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

`apply.py` checks every edit matched and every replaced file is the upstream version it was
written for, so a Core change that needs a human look stops the build instead of slipping
through.

The stand-in modules declare the same class names as the libraries they replace (the approach
comes from [Gravel](https://github.com/david-cant-code/pebble-app-degoogled)), which lets
Core's own code compile unmodified.

## Building

Needs JDK 17 or newer and the Android SDK.

```sh
git clone --recurse-submodules https://codeberg.org/Gaunkle/orb-for-pebble.git
cd orb-for-pebble
echo "sdk.dir=/path/to/Android/Sdk" > mobileapp/local.properties
python3 apply.py
cd mobileapp
./gradlew :androidApp:assembleRelease
python3 ../tools/check_apk.py androidApp/build/outputs/apk/release/androidApp-release-unsigned.apk
```

`python3 apply.py --reset` restores `mobileapp/` to the pinned commit and applies again.

## Moving to a new Core release

1. Point the submodule at the new tag: `git -C mobileapp fetch --tags && git -C mobileapp checkout <tag>`.
2. Set `versionName` and `versionCode` in `version.properties`.
3. Run `python3 apply.py --reset`, build, and run `tools/check_apk.py`.

If `apply.py` or the build fails, the message names what changed upstream.

## License

GPL-3.0, the same as Core's app. See `LICENSE`.
