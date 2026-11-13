#!/usr/bin/env bash
# Publish the APK built by tools/release_build.sh as a GitHub release, where Obtainium finds it.
#
# Creates a draft release for the tag with dist/orb-<version>.apk attached, checks that GitHub
# stored that exact file, publishes the release, then checks that the public download is
# byte-for-byte the same file. The notes carry the APK's SHA-256 and the signing certificate.
#
# Usage: tools/github_release.sh [VERSION]   (default: the version apply.py declares)
# Needs the GitHub CLI (gh) logged in with the repo scope and write access to the repository.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
REPO=${ORB_GITHUB_REPO:-orb-cybersecurity/orb-for-pebble}
WEB=https://github.com/$REPO
log() { echo "github_release: $*"; }
die() { echo "github_release: $*" >&2; exit 1; }

cd "$ROOT"
VERSION=${1:-$(python3 -c 'import apply; print(apply.read_version()[0])')}
APK=dist/orb-$VERSION.apk
TXT=dist/orb-$VERSION.txt
[ -f "$APK" ] && [ -f "$TXT" ] || die "no $APK and $TXT: run tools/release_build.sh first"

# The APK must still be the one release_build.sh checked and described.
field() { sed -n "s/^$1: //p" "$TXT"; }
SHA=$(field sha256)
CERT=$(field 'signing certificate sha256')
[ "$(field version)" = "$VERSION" ] || die "$TXT is for another version"
[ -n "$SHA" ] && [ -n "$CERT" ] || die "$TXT is incomplete"
[ "$(sha256sum "$APK" | cut -d' ' -f1)" = "$SHA" ] || die "$APK no longer matches $TXT"
COMMIT=$(git rev-parse --verify -q "refs/tags/$VERSION^{commit}") || die "no local tag $VERSION"

command -v gh > /dev/null || die "the GitHub CLI (gh) is not installed"
gh auth status > /dev/null 2>&1 || die "gh is not logged in"
WORK=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/orb-github.XXXXXX"); chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT

# GitHub must have the same tag, pointing at the same commit, and no release for it yet.
REMOTE=$(gh api "repos/$REPO/commits/$VERSION" --jq .sha 2>/dev/null) \
  || die "tag $VERSION is not on GitHub: push it first"
[ "$REMOTE" = "$COMMIT" ] || die "GitHub's tag $VERSION is $REMOTE, the local one is $COMMIT"
if gh release view "$VERSION" --repo "$REPO" > /dev/null 2>&1; then
  die "a release for $VERSION already exists"
fi

# Release notes: the changelog for this version, how to check the file, and how to install.
NAME=$(basename "$APK")
VERSION_CODE=$(python3 -c 'import apply; print(apply.read_version()[1])')
CHANGES=fastlane/metadata/android/en-US/changelogs/$VERSION_CODE.txt
{
  [ -f "$CHANGES" ] && { cat "$CHANGES"; echo; }
  echo "### Verifying"
  echo
  echo "Signing certificate SHA-256 (the same for every Orb release):"
  echo
  echo '```'
  echo "$CERT"
  echo '```'
  echo
  echo "\`$NAME\` SHA-256:"
  echo
  echo '```'
  echo "$SHA"
  echo '```'
  echo
  echo "### Installing"
  echo
  echo "In [Obtainium](https://obtainium.imranr.dev), tap **Add App**, enter \`$WEB\` and tap"
  echo "**Add**, then **Install**. Obtainium then offers each new release. Before the first"
  echo "install, you can check the APK's signing certificate against the fingerprint above, for"
  echo "example with [AppVerifier](https://github.com/soupslurpr/AppVerifier)."
} > "$WORK/notes.md"

log "creating a draft release with $NAME"
gh release create "$VERSION" "$APK" --repo "$REPO" --verify-tag --draft \
  --title "Orb $VERSION" --notes-file "$WORK/notes.md" > /dev/null || die "creating the draft failed"

# What GitHub stored must be the file that was checked.
gh release download "$VERSION" --repo "$REPO" --pattern "$NAME" --dir "$WORK/stored" \
  || die "could not read back the draft's asset (the draft is left for inspection)"
[ "$(sha256sum "$WORK/stored/$NAME" | cut -d' ' -f1)" = "$SHA" ] \
  || die "GitHub stored a different file (the draft is left for inspection)"

gh release edit "$VERSION" --repo "$REPO" --draft=false --latest > /dev/null || die "publishing failed"

# Download it anonymously, as Obtainium will, and compare.
curl -sSfL -o "$WORK/public.apk" "$WEB/releases/download/$VERSION/$NAME" \
  || die "the APK is not publicly downloadable"
[ "$(sha256sum "$WORK/public.apk" | cut -d' ' -f1)" = "$SHA" ] || die "the public download differs"
log "done: $WEB/releases/tag/$VERSION"
