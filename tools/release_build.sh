#!/usr/bin/env bash
# Build Orb's signed release APK from a clean checkout of the release tag.
#
# Builds the release app bundle and has bundletool turn it into one installable APK for both
# ARM ABIs, signed with the release key (APK signature v2/v3). That APK is what goes on the
# GitHub release, where Obtainium picks it up. The script then checks it.
#
# Usage: tools/release_build.sh [KEYSTORE] [ALIAS]
#   KEYSTORE  default ~/.local/share/orb-release/orb-release.p12 (PKCS12, mode 600)
#   ALIAS     default orb
# The keystore password is read from the terminal (or ORB_KS_PASS_FILE, a file holding it) and
# never placed on a command line. Output: dist/orb-<version>.apk, and dist/orb-<version>.txt
# with its SHA-256 and the signing certificate's SHA-256.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
KS=${1:-$HOME/.local/share/orb-release/orb-release.p12}
ALIAS=${2:-orb}
BUNDLETOOL_VERSION=1.18.3
BUNDLETOOL_SHA256=a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29
export JAVA_HOME=${JAVA_HOME:-$HOME/.local/jdk/jdk-21.0.13+9}
BT_DIR=$(ls -d "${ANDROID_HOME:-$HOME/Android/Sdk}"/build-tools/*/ | sort -V | tail -1)
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/orb-tools
log() { echo "release_build: $*"; }
die() { echo "release_build: $*" >&2; exit 1; }

[ -r "$KS" ] || die "keystore not found: $KS"
[ "$(stat -c %a "$KS")" = 600 ] || die "$KS must be mode 600"

# bundletool, pinned and verified.
mkdir -p "$CACHE"
BT="$CACHE/bundletool-all-$BUNDLETOOL_VERSION.jar"
if [ ! -f "$BT" ]; then
  curl -sfL -o "$BT.part" "https://github.com/google/bundletool/releases/download/$BUNDLETOOL_VERSION/bundletool-all-$BUNDLETOOL_VERSION.jar"
  mv "$BT.part" "$BT"
fi
echo "$BUNDLETOOL_SHA256  $BT" | sha256sum -c --quiet - || { rm -f "$BT"; die "bundletool checksum mismatch"; }

# Password into a private file for the duration of the run.
WORK=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/orb-release.XXXXXX"); chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
if [ -n "${ORB_KS_PASS_FILE:-}" ]; then
  install -m 600 "$ORB_KS_PASS_FILE" "$WORK/pass"
else
  read -rsp "Keystore password for $KS: " P; echo
  ( umask 077; printf '%s' "$P" > "$WORK/pass" ); unset P
fi

# Only a clean checkout of the release tag is built: what ships is exactly what was pushed.
cd "$ROOT"
[ -z "$(git status --porcelain --untracked-files=all)" ] || die "working tree is not clean"
[ -z "$(git ls-files --others -- overlay)" ] || die "untracked or ignored files in overlay/"
VERSION=$(python3 -c 'import apply; print(apply.read_version()[0])')
[ "$(git describe --exact-match --tags HEAD 2>/dev/null)" = "$VERSION" ] || die "HEAD is not tagged $VERSION"
rm -f "dist/orb-$VERSION.apk" "dist/orb-$VERSION.txt"
python3 apply.py --reset >/dev/null
sh tools/check_deps.sh || die "the release build resolves dependencies Orb must not ship"
( cd mobileapp && ./gradlew -q :androidApp:bundleRelease --console=plain )
AAB=mobileapp/androidApp/build/outputs/bundle/release/androidApp-release.aab
[ -f "$AAB" ] || die "no bundle at $AAB"

mkdir -p dist
APK="$WORK/orb.apk"
"$JAVA_HOME/bin/java" -jar "$BT" build-apks --bundle="$AAB" --output="$WORK/universal.apks" \
  --mode=universal --ks="$KS" --ks-key-alias="$ALIAS" \
  --ks-pass="file:$WORK/pass" --key-pass="file:$WORK/pass"
unzip -qq -p "$WORK/universal.apks" universal.apk > "$APK"

# Checks: signed (v2+) with a non-debug key, the expected package, both ARM ABIs, not debuggable.
# (here-strings, not pipes: grep -q exiting early would trip pipefail)
CERTS=$("$BT_DIR/apksigner" verify -v --print-certs "$APK" 2>/dev/null) || die "signature verification failed"
grep -q 'Verified using v2 scheme (APK Signature Scheme v2): true' <<<"$CERTS" || die "not signed with v2"
grep -qi 'CN=Android Debug' <<<"$CERTS" && die "signed with a debug certificate"
CERT_SHA=$(sed -n 's/.*Signer: certificate SHA-256 digest: //p' <<<"$CERTS" | head -1)
[ -n "$CERT_SHA" ] || die "no signing certificate found"
PKG=$("$BT_DIR/aapt2" dump packagename "$APK")
[ "$PKG" = com.orbcybersecurity.orb ] || die "unexpected package $PKG"
BADGING=$("$BT_DIR/aapt2" dump badging "$APK")
grep -q "native-code: 'arm64-v8a' 'armeabi-v7a'" <<<"$BADGING" || die "expected arm64-v8a and armeabi-v7a native code"
grep -q "application-debuggable" <<<"$BADGING" && die "debuggable APK"
python3 tools/check_apk.py "$APK" || die "the APK contains code Orb must not ship"

# All checks passed: only now does it get its release name.
cp "$APK" "dist/.orb-$VERSION.apk.part"
mv "dist/.orb-$VERSION.apk.part" "dist/orb-$VERSION.apk"
APK="dist/orb-$VERSION.apk"
{
  echo "version: $VERSION"
  echo "package: $PKG"
  echo "file: $(basename "$APK")"
  echo "size: $(stat -c %s "$APK") bytes"
  echo "sha256: $(sha256sum "$APK" | cut -d' ' -f1)"
  echo "signing certificate sha256: $CERT_SHA"
} | tee "dist/orb-$VERSION.txt"
log "done: $APK"
