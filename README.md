# Orb for Pebble

An Android companion app for Pebble watches, based on [Core Devices' app](https://github.com/coredevices/mobileapp), for phones without Google Play services.

Not affiliated with or endorsed by Core Devices or GrapheneOS.

## Goal

Orb aims to be a Pebble companion app without Google: no Google Play services,
Firebase, Google libraries, or ad-tech or data-broker analytics. Where Core's app
depends on these, Orb uses what GrapheneOS provides natively or a free and
open-source alternative. Where no free replacement exists yet, Orb leaves the
feature out. Otherwise, it stays as close to Core's app as possible.

GrapheneOS is the primary target. Orb should also work on other Android phones
without Google Play services.

## Status

Orb is early in development and currently based on Core's 1.18.0.1 release.
Debug and release builds start on an Android 16 emulator without Google services.
It has not been tested with a real watch. Dictation through the system speech
recognizer is also untested. No release has been published yet.

The watchface and app store works without an account: browsing the Pebble and
Rebble stores, searching, and installing to the watch all work. Without an
account, hearts (likes) and cloud locker sync (the installed apps list) are
unavailable.

The launcher label is **Orb**. The application ID is `com.orbcybersecurity.orb`.

## Differences from the official app

### Removed

- Firebase sign-in, Firestore, Storage, Crashlytics and Cloud Messaging;
  Google sign-in; and Google Play in-app updates.
- Core accounts and features that require them: cloud locker sync, submitting
  bug reports to Core, battery history and cloud speech recognition. Their
  settings are hidden. Bug reports can still be saved and shared as files.
- Mixpanel analytics, and Core's watch analytics and Memfault diagnostics uploads.
- The Cactus speech engine, distributed only as a prebuilt binary.
- The Index 01 ring's closed-source radio library. Ring code remains compiled,
  but discovering and pairing rings is unavailable, and the add-ring option is hidden.
- The health library's Google Fit fallback. Health Connect remains available
  where the phone supports it.

### Replaced

- **Firmware updates for Core watches:** Orb uses Core's public GitHub releases
  because Core's update server requires an account. Older Pebble watches still
  update through Rebble. A version can be pinned under Settings → Debug after
  enabling "Show debug options".
- **Dictation:** Orb uses the phone's selected speech recognition service.
  Choose "System (On-Device)" in speech settings. This requires Android 13 or
  newer and a recognizer app that accepts recorded audio.

For Core watches, Orb selects the newest non-draft, non-prerelease firmware newer
than the installed version, checking the watch board, published SHA-256 digest,
download hash, manifest board and version, and CRCs. If a release fails these
checks, it tries the next older eligible release.

## Network and privacy

Services Orb is known to contact include:

- Pebble app store: `appstore-api.repebble.com`.
- Rebble app store: `appstore-api.rebble.io`.
- Algolia, a third-party search service, using the stores' public search-only keys.
- Core's weather and notification-icon services on `repebble.com`.
- Rebble's boot, binaries and firmware cohorts services.
- GitHub, for Core watch firmware releases.

Links also open Core's documentation pages. A full audit of every host the app can
reach is in progress; this list will be completed as part of it.

Orb sends no telemetry. Mixpanel analytics is removed, and so is the code for
Core's own telemetry: the watch analytics heartbeat and Memfault diagnostics
uploads. Data the watch offers for them is dropped on the phone.

## Installing

Until a release is published, build from source. Distribution is planned for
Accrescent first and F-Droid later; F-Droid requires a period of active
development before inclusion.

Uninstall Core's official app or another fork before installing Orb. They declare
the same PebbleKit providers, so Android cannot install them alongside Orb.

## Building

Requires JDK 17 or newer and the Android SDK.

```sh
git clone --recurse-submodules https://codeberg.org/Orb-Cybersecurity/orb-for-pebble.git
cd orb-for-pebble
echo "sdk.dir=/path/to/Android/Sdk" > mobileapp/local.properties
python3 apply.py
cd mobileapp
./gradlew :androidApp:assembleRelease
python3 ../tools/check_apk.py androidApp/build/outputs/apk/release/androidApp-release-unsigned.apk
```

`python3 apply.py --reset` restores `mobileapp/` to the pinned commit and applies
Orb's changes again.

Core's source is pinned as a submodule. `apply.py` applies Orb's overlay and edits,
and stops if the upstream files no longer match the expected versions.
`tools/check_apk.py` checks the APK for code Orb must not ship.

The stand-in modules use the same class names as the libraries they replace,
allowing Core's code to compile unmodified. This approach comes from
[Gravel](https://github.com/david-cant-code/pebble-app-degoogled).

## Contributing

Report issues and submit pull requests on
[Codeberg](https://codeberg.org/Orb-Cybersecurity/orb-for-pebble).

## License and trademarks

Orb for Pebble is free software under the GNU General Public License, version 3
(SPDX: GPL-3.0-only), the license of Core's app, which it is derived from. See `LICENSE`.

Core's code is copyright Core Devices and its contributors. The files in this repository are
copyright the Orb for Pebble authors and are offered under the same license. Core also sells
its code under a separate commercial license; that offer is Core's alone and does not extend
to Orb.

Pebble is a trademark of Core Devices LLC. The name is used only to identify the
watches the app works with.
