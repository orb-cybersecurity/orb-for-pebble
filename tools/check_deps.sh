#!/bin/sh
# Fails if the release build resolves any artifact Orb replaces or must not ship, instead of
# the stand-in or source-built project. Run after apply.py, from the repository root.
#
# check_apk.py looks at the APK, where R8 has renamed most classes and a prebuilt native
# library looks like any other; this looks at what Gradle actually resolved.
set -eu

forbidden='io\.github\.coredevices\.(speex|haversine)|io\.github\.mirzemehdi:kmpnotifier|dev\.gitlive:firebase|com\.google\.firebase|com\.google\.android\.(gms|play|libraries\.identity)|com\.mixpanel'

deps=$(cd mobileapp && ./gradlew -q --no-daemon :androidApp:dependencies --configuration releaseRuntimeClasspath)
found=$(printf '%s\n' "$deps" | grep -E "$forbidden" | grep -vE -- "-> project '?:" || true)
if [ -n "$found" ]; then
    printf 'Release dependencies include artifacts Orb must not ship:\n%s\n' "$found" >&2
    exit 1
fi
substituted=$(printf '%s\n' "$deps" | grep -E "$forbidden" | sed -E "s/.*--- ([^ ]+) -> project '?(:[^' ]+).*/\\1 -> \\2/" | sort -u)
printf 'OK: no forbidden artifacts in the release dependencies. Replaced:\n%s\n' "$substituted"
