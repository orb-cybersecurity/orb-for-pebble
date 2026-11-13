#!/bin/sh
# Run F-Droid's source scanner on a commit of this repository (default HEAD) the way F-Droid's
# build server does: fresh clone, submodules, signing lines stripped, prebuild, then scan.
# Needs `fdroid` from fdroidserver on PATH.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
commit=$(git -C "$root" rev-parse "${1:-HEAD}")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/metadata"
sed -e "s#^Repo: .*#Repo: file://$root#" \
    -e "s#^\(    commit: \).*#\1$commit#" \
    "$root/fdroid/com.orbcybersecurity.orb.yml" > "$work/metadata/com.orbcybersecurity.orb.yml"
cd "$work"
exec fdroid scanner --exit-code -v com.orbcybersecurity.orb
