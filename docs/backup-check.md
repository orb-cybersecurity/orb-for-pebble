# Checking backup and restore

Android's backup is how Orb's data reaches a new phone. On GrapheneOS that
backup is Seedvault. Host tests (`BackupRulesTest`) and `tools/check_apk.py`
check the rules, and `RestoredDataTest` checks on a device how Orb reads
restored data. Neither of them runs a real backup. Run this procedure by hand
before a release that changes what Orb stores or how it backs up.

It uses the Android emulator's local backup transport. That transport can
present itself as a device-to-device transfer, which is what Seedvault does,
so Android applies the same rules to it.

## Setup

An emulator with a Google APIs or AOSP image, so that `adb root` works. Install
the release build signed with any key, open Orb, and give it some state: sign in
to Rebble, install a few apps from both stores, and open one `.pbw` file.

```sh
adb root
adb shell bmgr enable true
adb shell bmgr transport com.android.localtransport/.LocalTransport
adb shell settings put secure backup_local_transport_parameters \
  "fake_encryption_flag=true,is_device_transfer=true"
```

## Record the state

```sh
adb shell "cd /data/data/com.orbcybersecurity.orb && \
  sqlite3 databases/libpebble3.db 'select count(*) from LockerEntryEntity' && \
  sqlite3 databases/coreapp.db 'pragma user_version; select count(*) from AppstoreSource' && \
  ls files/pbw"
```

## Back up

Open Orb first. Android skips stopped apps, and reports that as "Backup is not
allowed".

```sh
adb logcat -c
adb shell bmgr backupnow com.orbcybersecurity.orb
adb logcat -d | grep "FullBackup_native: measured"
```

Pass: `Package com.orbcybersecurity.orb with result: Success`. The files
measured are only in `databases/`, `shared_prefs/` and `files/pbw/`. Nothing
comes from `cache/` (logs, images, downloads) or `no_backup/`.

## Wipe and restore

```sh
adb shell pm clear com.orbcybersecurity.orb
adb shell bmgr list sets          # the token is the number before the colon
adb shell bmgr restore <token> com.orbcybersecurity.orb
```

Pass: `restoreFinished: 0`. The commands under "Record the state" print the same
numbers and files as before. Orb then opens to Devices without onboarding. The
Apps tab shows the same apps, including those from the Rebble locker and the
opened `.pbw`, and the Rebble sign-in is still there. There is no crash in
`adb logcat`.

## Cloud backup

With `fake_encryption_flag=true` alone (no `is_device_transfer`), the backup must
copy nothing. The transport then reports `Error -1002` (an empty backup) in
`adb logcat`. That is the rule that only lets backup services that encrypt on the
phone receive Orb's data. The emulator's transport doesn't report real
encryption, so a positive cloud-backup run needs a phone with such a service.

## Clean up

```sh
adb shell settings delete secure backup_local_transport_parameters
adb shell bmgr enable false
```

## Not covered

Bluetooth pairing is never part of an app's backup, so the watch has to be
paired again on the new phone. This procedure has no watch and doesn't check
that. Plugin secrets restore as values the new phone can't decrypt, and Orb
drops them. `RestoredDataTest` checks that, not this procedure.

## Last run

2026-11-13, emulator with Android 16 (API 36): pass. The backup held 14 locker
entries, both store sources, one sideloaded `.pbw` and the Rebble sign-in. All of
them came back. Cloud backup without real encryption copied nothing, as intended.
