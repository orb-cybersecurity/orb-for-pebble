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

Orb is early in development and currently based on Core's 2.0.0 release.
The earlier 1.18.0.1 release was tested on GrapheneOS with a real watch.
2.0.0-orb1 builds and passes Orb’s checks. Releases are published on
GitHub as signed APKs, installed and updated with Obtainium.

System/offline dictation is not yet available on GrapheneOS. Rebble dictation
works with a Rebble subscription. Other Android systems need Android 13 or newer
and a speech recognizer that accepts recorded audio for system dictation.

The Pebble app store works without an account: browsing, searching and installing
to the watch all work. The Rebble store requires a free Rebble sign-in.
[docs/no-account.md](docs/no-account.md) lists what a Core account would add, what
Orb offers instead, and how to move Orb to a new phone with Android's backup.

The launcher label is **Orb**. The application ID is `com.orbcybersecurity.orb`.

## Differences from the official app

### Removed

- Firebase sign-in, Firestore, Storage, Crashlytics and Cloud Messaging;
  Google sign-in; and Google Play in-app updates.
- Core accounts and features that require them: submitting bug reports to Core
  and its support chat, battery history, messaging app developers through Core's
  store, and cloud speech recognition. Their code is removed, not hidden. Bug
  reports can still be saved and shared as files.
- Both Mixpanel collectors, Firebase user linkage, process-exit analytics,
  and Core's watch analytics and Memfault diagnostics uploads.
- The Cactus speech engine, distributed only as a prebuilt binary.
- Support for Core's Index 01 ring. Its radio library is closed source, so Orb
  removes the ring's code entirely and has no plans to support the ring.
- The health library's Google Fit fallback. Health Connect remains available
  where the phone supports it.
- The link to Core's getting-started guide, which describes Core's app.
- Classic PebbleKit, the original API for phone apps. Phone apps need PebbleKit 2.
- Core's test hooks for adb, which let a shell user attach an emulated watch,
  start the developer connection or change any setting, and a Bluetooth pairing
  logger that wrote pairing keys into the shared logs.

### Replaced

- **Links and files from other apps:** Orb asks before acting on them. A Rebble sign-in
  link must use https and names the server it would switch to; watchapps and language
  packs are named before anything is installed, and a watchapp that would replace an
  installed one says so.
- **Locker:** Core keeps the list of your store apps in its cloud under a Core
  account. Orb keeps it on the phone. Signed in to Rebble, Orb brings in your
  Rebble locker. A sync refreshes apps from the store they came from and never
  removes an installed app.
- **Backup:** Android copies the whole databases, including notification history,
  per-app network usage and plugin-action history; app settings including the Rebble
  sign-in; and everything in `files/pbw/` (store and sideloaded PBWs and extracted
  PKJS files). Files in `cache/`, including logs, are excluded. These backups can
  exceed a backup service's quota. They go only to backup services that encrypt on
  the phone, or in a device-to-device transfer such as Seedvault's. Core's rules only excluded
  Firebase's files.
- **Firmware updates for Core watches:** Orb uses Core's public GitHub releases
  because Core's update server requires an account. Older Pebble watches still
  update through Rebble. A version can be pinned under Settings → Debug after
  enabling "Show debug options".
- **PebbleKit 2 companions:** Watch data and app control require a stored PebbleKit2
  declaration and allowed access. Queries return nothing until the companion is
  allowed: by the user, automatically for watchapps built before permissions unless
  "Ask before older apps use other permissions" is on, or with "Ask before apps use
  permissions" set to "Never". Observers can see that connected watches, the running
  watchapp, or companion access changed; no watch, app, companion or serial is
  revealed.
- **Dictation:** Orb uses the phone's selected speech recognition service.
  System/offline dictation is not yet available on GrapheneOS. Rebble dictation
  works with a Rebble subscription; select a Rebble mode in speech settings.
  Other Android systems need Android 13 or newer and a recognizer app that accepts recorded audio for system dictation.

For Core watches running normal firmware, Orb selects the newest non-draft,
non-prerelease firmware newer than the installed version, checking the watch board,
published SHA-256 digest,
download hash, manifest board and version, and CRCs. If a release fails these
checks, it tries the next older eligible release. Automatic and offered updates refuse
firmware older than normal running firmware. Recovery firmware can take a normal
release regardless of its recovery version. An explicit hidden version pin may
downgrade, but is never installed automatically. Original Pebble firmware must match Rebble’s
published SHA-256 too.

## Network and privacy

Watchapps' ordinary XHR and `fetch()` requests use Orb's permission and redirect
checks. Core's retained compatibility interceptors run before those checks:

- With weather interception enabled (the default), supported OpenWeatherMap
  `/data/2.5/weather` and Yahoo `query.yahooapis.com/v1/public/yql` requests skip
  the watchapp Internet permission check, even when access is denied.
  OpenWeatherMap requests first send the app's key and requested coordinates to
  `api.openweathermap.org`; a 401 response falls back to Core's weather service.
  Yahoo forecasts use Core's weather service; supported location lookups use the
  phone's geocoder.
- Timeline pin emulation handles legacy pin requests locally. Adding pins
  requires timeline permission.

PKJS browser resources load only from Orb's bundled assets. The debug toggle for
sending PKJS requests through the WebView has been removed; saved choices are
migrated automatically. Settings pages use live permission checks for WebSockets
and close when a network permission is revoked, stopping the page's active
connections. Reopen settings after changing its permissions.

Built-in services contact these hosts; watchapps and custom store sources can
also contact their configured hosts:

- **Rebble:** sign-in configuration (`boot.rebble.io`), the Rebble app store
  (`appstore-api.rebble.io`), app downloads and images (`binaries.rebble.io`,
  `assets2.rebble.io`), firmware for older Pebble watches (`cohorts.rebble.io`),
  and Rebble dictation if you choose it.
- **Core's Pebble app store** (`appstore-api.repebble.com`), its search endpoint
  (`appsearch.cluster.repebble.com`) and timeline icons (`developer.repebble.com`). Language contribution pages (`translate.repebble.com`)
  open in your browser.
- **Algolia**, a third-party search service, when you search the Rebble store,
  using that store's public search-only keys.
- **Core's weather service** (`weather-api.repebble.com`) while weather is on, which
  it is by default. It receives the coordinates of each weather location. Watch apps
  that ask Yahoo's old weather API are answered from this service, with the
  coordinates they ask about. OpenWeatherMap 2.5 requests contact
  `api.openweathermap.org` first, falling back to Core's service on a 401 response.
- **GitHub** (`api.github.com`, `github.com` and their release-download hosts,
  including `release-assets.githubusercontent.com`), for firmware releases for
  Core watches and the language-pack manifest at
  `https://github.com/coredevices/pebbleos-translations/releases/latest/download/manifest.json`.
  The manifest is cached and refreshed during background sync. It supplies
  language-pack URLs: current packs are restricted to that repository's releases;
  archived packs may use any HTTPS host named by the manifest, including
  `binaries.rebble.io`.

Language-pack downloads must match the manifest's exact byte count and SHA-256.
The catalog and downloads have size limits. The manifest is trusted through HTTPS
and has no separate signature; its digest checks detect mismatched downloads,
but do not protect against replacement of both the catalog and a pack.

Rebble's boot configuration supplies the locker and dictation endpoints. A custom
server requires confirmation of its host. Additional store feeds you enable and
watchapps you install can use their own HTTPS hosts.

App store pages open in your browser. Watch apps you install run their own
JavaScript on the phone and can contact their own servers, as on every Pebble app.

Settings pages keep saved local storage within their original web origin. Legacy
save callbacks must come from that origin's main page; a callback bound to the
open configuration request can also return from a sign-in redirect. Imported
watchapp and firmware archives reject JSON metadata larger than 1 MiB and text
files larger than 8 MiB.

Outbound web connections use HTTPS, with system CAs only; user-installed CAs are
not trusted. Orb blocks plain HTTP for itself, watchapps and their settings pages.
The LAN developer server is an exception: it is off by default and uses an
unencrypted local connection when enabled.

[docs/no-account.md](docs/no-account.md) lists what using Orb without a Core
account costs.

Orb sends no telemetry and has no analytics. Mixpanel, Firebase, Crashlytics,
Core's analytics and Core's watch analytics and Memfault diagnostics uploads are
all removed. Data the watch offers for them is dropped on the phone.

The per-app network-usage and plugin-action history screens introduced in 2.0.0
store their records in Orb's databases on the phone and in Android backups and
transfers you enable. They enter a shared log file only when you choose Share Logs.

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

Android can install Orb next to the original Pebble app, Cobble, Gadgetbridge,
Core's app or microPebble. Orb won't connect to a watch while one is installed
unless "Ignore other Pebble apps" is on. Uninstall them first. Enabling that
setting can make BLE connections unreliable and is not recommended.

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
`tools/check_apk.py` checks the APK for code Orb must not ship. It also checks that
the manifest keeps Orb's backup rules and HTTPS-only setting, with no debug
components. It reads the manifest with `aapt2` from the Android SDK.

Run the Python checks with `for t in tools/test_*.py; do python3 "$t"; done`.
The JavaScript transport tests require Node.js and use an in-memory transport.

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
