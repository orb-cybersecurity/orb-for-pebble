# Using Orb without a Core account

Orb cannot sign in to a Core Devices account. This page lists what that account
does in Core's Pebble app and what Orb offers instead. Each entry was checked
against Core's code. A change to Orb that costs users something adds its entry
here in the same commit.

Core's app signs every user in to an anonymous account at first start. Users can
then sign in with Google, Apple or GitHub. Data kept under the anonymous account
is lost when the app is reinstalled, so restoring anything from Core's cloud
needs one of those sign-ins.

A Rebble account is separate, and Orb supports it. To sign in, turn on the Rebble
store under Configure Appstore Sources. Orb opens `boot.rebble.io` in your
browser, and the sign-in link from there brings you back to Orb. Several entries
below depend on it.

## Gone, with no replacement

**Hearts in Core's app store.** Liking an app in Core's store sends the Core
account's token to `appstore-api.repebble.com`. Orb has no token, so Core's store
treats you as signed out (`AppstoreService.isLoggedIn()` is false for it). Hearts
in the Rebble store work when you are signed in to Rebble.

**Battery history.** Core's battery screen is a Core web page opened with your
Core account's token (`BatterySettingsScreen`). Orb removes the screen. There is
no replacement.

**Plugin sign-ins through Core.** Core lets plugins sign in to other services
through a sign-in broker that Core hosts, as your Core account
(`HostedPluginOAuthApi`). Orb removes it. A plugin that signs in this way cannot
sign in.

**Sharing permission answers with Core's web store.** Core stores your answers
to watchapp permission requests, and how often apps may ask, under your account,
so its web store and your other phones ask the same way (`PermissionDecisionSync`,
`PermissionSettingsSync`). Orb keeps them on the phone only. A new phone asks
again unless you restore Orb's data from a backup (see the locker entry).

## Gone, with a workaround

**Your list of store apps across phones and reinstalls (the locker).** Core keeps
the list in its cloud under your account (`FirestoreLocker`). Orb keeps it on the
phone (overlay `FirestoreLocker.kt`, `LocalLocker`). Android's backup carries it
instead. On GrapheneOS that is Seedvault, which encrypts the backup on the phone
and writes it to a USB drive or any folder the system file picker reaches. Orb's
backup rules (`res/xml/data_extraction_rules.xml`) copy Orb's databases, its
settings file and the apps you opened from `.pbw` files. That covers your watches,
the locker, which store each app came from, your settings, your Rebble sign-in and
your answers to watchapp permission requests.

1. On the old phone, open Settings → System → Backup and turn backups on. Write
   down the recovery code it shows. Choose where backups go, then run a backup.
2. On the new phone, install Orb, then restore that backup from the same Backup
   screen, using the recovery code.
3. Open Orb. It starts where the old phone left off, without onboarding. Pair the
   watch again under Devices.

What does not come back:

- **The Bluetooth pairing.** It belongs to the phone, not to Orb, so step 3 is
  always needed.
- **Plugin secrets**, such as a plugin's sign-in to another service. They are
  encrypted under a key that never leaves the old phone. Orb drops them on the
  new phone, and the plugin asks again.
- **Caches and logs**, which Orb fetches or writes again as needed.

Without a backup, nothing restores apps from Core's store. If you are signed in to
Rebble, Orb brings in your Rebble locker on each sync. A sync never removes an
installed app, so nothing is lost if a store can't be reached.

[backup-check.md](backup-check.md) is the procedure that checks a backup and
restore on the emulator, and when it last passed.

**Dictation and voice replies.** Core's cloud speech recognition (Wispr Flow)
needs your Core account. Orb removes it, along with Core's on-device engine,
which ships only as a prebuilt binary. What remains:

- Rebble dictation. It needs a Rebble account with a paid subscription. Choose a
  Rebble mode under Speech Recognition.
- "System (On-Device)" under Speech Recognition, using the phone's speech
  recognition app. It needs Android 13 or newer and an app that accepts the audio
  Orb hands it. GrapheneOS has no such app yet, so on GrapheneOS without a Rebble
  subscription there is no dictation today.

**Support chat and bug reports to Core.** Core's in-app support chat, its bug
report upload and the replies it pushes to the phone all use your Core account.
Orb removes them. Under Get Help, Share Logs saves the app and watch logs to a
file. Check what is in it, then attach it to an issue on Orb's GitHub page. Core
does not support Orb.

**Messaging an app's developer.** Core's store sends your message to the
developer through Core, as your account (`ContactDeveloperApi`). Orb removes it.
When the developer published a source code link, the app's page shows it, and
the project there is usually the way to reach them.

**CloudPebble and pebble-tool over the internet.** Core relays developer
connections to the watch through `cloudpebble-proxy.repebble.com`, using your
Core account. Orb never connects to it. Turn on "Use LAN developer connection" in
settings and connect pebble-tool on the same network instead. It is off by
default, and any device on that network can then reach the watch.

## Different source

**Firmware updates for Core's watches.** Core's app asks Core's update server,
which needs your Core account's token (`EngDashOtaApi`). Orb reads Core's public
GitHub releases instead (overlay `GitHubFirmware.kt`). It installs the newest
release that is not a draft or prerelease and passes Orb's checks. Orb only sees
what Core publishes there. A build that Core's server hands only to some watches
or to a test group does not reach Orb. A version can be pinned under
Settings → Debug after turning on "Show debug options".

## Never needed an account

**Firmware updates for original Pebble watches.** Both apps ask Rebble's cohorts
service, where signing in is optional (`Cohorts.kt`).

**Installing apps and watchfaces.** Browsing, searching and installing from
Core's and Rebble's stores work without any account. Signed in to Rebble,
installs from the Rebble store are also added to your Rebble locker. You can also
open a `.pbw` file from a file manager or a download. Orb names the app before
anything is installed.

**Weather.** Core's weather service takes no account or token
(`HttpClientAuthType.None`). It receives the coordinates of each weather
location.

**Timeline pins.** Neither app fetches pins from a server. Pins that watchapps
create through the timeline web API are handled on the phone
(`RemoteTimelineEmulator`). A watchapp's real timeline token comes from the
Rebble locker when you are signed in to Rebble. Core's store never supplies one.

**Settings and watches on a new phone.** The only setting Core synced to the
account was a switch for experimental devices, used by the removed Index ring
(`UserConfig`). The list of your watches went to Core's cloud, but nothing read it
back (`FirestoreKnownWatchesSync`). So no setting or watch followed the account to
a new phone.

**"What's new" and the getting-started guide.** Neither needed an account. Orb
removes them because they describe Core's app. Orb's changes are listed with each
release on GitHub. Core's guide is still at `help.repebble.com` in a browser.
