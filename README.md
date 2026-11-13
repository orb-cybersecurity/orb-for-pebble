# Orb for Pebble

A Pebble companion app built for [GrapheneOS](https://grapheneos.org), based on [Core Devices' app](https://github.com/coredevices/mobileapp).

Not affiliated with or endorsed by Core Devices or GrapheneOS.

## Goal

Orb aims to be a Pebble companion app without Google: no Google Play services,
Firebase, Google libraries, or ad-tech or data-broker analytics. Where Core's app
depends on these, Orb uses what GrapheneOS provides natively or a free and
open-source alternative. Where no free replacement exists yet, Orb leaves the
feature out. Otherwise, it stays as close to Core's app as possible.

Orb is developed for GrapheneOS, and GrapheneOS is the platform it is tested and
supported on. Its design choices follow from that: it uses GrapheneOS's own
components where they exist, respects its permission toggles and scopes, and
takes its look from GrapheneOS's apps. Orb will likely run on other Android
phones without Google Play services, but those are not tested, and GrapheneOS
comes first when the two pull in different directions.

## Status

Orb is early in development and currently based on Core's 1.18.0.1 release.
It has been tested on GrapheneOS with a real watch. Releases are published on
GitHub as signed APKs, installed and updated with Obtainium.

Dictation does not work yet. Orb hands it to the phone's speech recognition
service, and no free recognizer currently transcribes the watch's audio:
GrapheneOS's own speech services do not offer speech-to-text yet, and Transcribro
records the phone's microphone instead of the audio Orb passes to it. Orb will use
whichever of these gains support first.

The watchface and app store works without an account: browsing the Pebble and
Rebble stores, searching, and installing to the watch all work. Without an
account, hearts (likes) and cloud locker sync (the installed apps list) are
unavailable.

The launcher label is **Orb**. The application ID is `com.orbcybersecurity.orb`.

## Differences from the official app

### Removed

- Firebase sign-in, Firestore, Storage, Crashlytics and Cloud Messaging;
  Google sign-in; and Google Play in-app updates.
- Core accounts and features that require them: submitting bug reports to Core
  and its support chat, battery history, messaging app developers through Core's
  store, and cloud speech recognition. Their code is removed, not hidden. Bug
  reports can still be saved and shared as files.
- Mixpanel analytics, and Core's watch analytics and Memfault diagnostics uploads.
- The Cactus speech engine, distributed only as a prebuilt binary.
- Support for Core's Index 01 ring. Its radio library is closed source, so Orb
  removes the ring's code entirely and has no plans to support the ring.
- The health library's Google Fit fallback. Health Connect remains available
  where the phone supports it.

### Replaced

- **Links and files from other apps:** Orb asks before acting on them. A Rebble sign-in
  link must use https and names the server it would switch to; watchapps and language
  packs are named before anything is installed, and a watchapp that would replace an
  installed one says so.
- **Locker:** Core keeps the list of your store apps in its cloud under a Core
  account. Orb keeps it on the phone. Signed in to Rebble, Orb brings in your
  Rebble locker. A sync refreshes apps from the store they came from and never
  removes an installed app.
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

Orb is installed and updated with [Obtainium](https://obtainium.imranr.dev),
which fetches apps directly from their release pages, with no app store account and
no Google Play services. Orb is not in the GrapheneOS App Store, Accrescent or Google
Play. Accrescent is the goal once it accepts new developers again.

1. Install Obtainium from its
   [releases page](https://github.com/ImranR98/Obtainium/releases) or from F-Droid.
2. In Obtainium, tap **Add App** and enter
   `https://github.com/orb-cybersecurity/orb-for-pebble`.
3. Tap **Add**, then **Install**. Android asks once to allow Obtainium to install
   apps.

Obtainium checks GitHub for new releases and offers each update. Every release
is a single APK signed with Orb's release key, and Android refuses an update signed
with any other key, so a replaced download can't overwrite the installed app. Each
release lists the signing certificate's SHA-256 fingerprint, so you can check the
first install against it (for example with
[AppVerifier](https://github.com/soupslurpr/AppVerifier)). It is the same for every
release:

```
2e3e6c81aa66f5f11ac8d4cbe369e5ec7e98019ef0f4aaa5259c0c1421154621
```

You can also download the APK from
[GitHub Releases](https://github.com/orb-cybersecurity/orb-for-pebble/releases)
and install it by hand. Nothing will then tell you about updates.

F-Droid will follow once Orb meets F-Droid's requirement for a period of active
development.

Uninstall Core's official app or another fork before installing Orb. They declare
the same PebbleKit providers, so Android cannot install them alongside Orb.

## Building

Requires JDK 17 or newer and the Android SDK.

```sh
git clone --recurse-submodules https://github.com/orb-cybersecurity/orb-for-pebble.git
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

Orb removes the code that needs Google services or a Core account instead of
stubbing it out, so nothing in the app only pretends to work. Speex, which Core
ships as a prebuilt library, is built from source.

## Contributing

Report issues and submit pull requests on
[GitHub](https://github.com/orb-cybersecurity/orb-for-pebble).

## License and trademarks

Orb for Pebble is free software under the GNU General Public License, version 3
(SPDX: GPL-3.0-only), the license of Core's app, which it is derived from. See `LICENSE`.

Core's code is copyright Core Devices and its contributors. The files in this repository are
copyright the Orb for Pebble authors and are offered under the same license. Core also sells
its code under a separate commercial license; that offer is Core's alone and does not extend
to Orb.

Pebble is a trademark of Core Devices LLC. The name is used only to identify the
watches the app works with.
