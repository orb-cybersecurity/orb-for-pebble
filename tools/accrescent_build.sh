#!/usr/bin/env bash
# Build the signed APK set (.apks) that Accrescent accepts, from a clean overlay apply.
#
# Accrescent takes split APKs made by bundletool (>= 1.11.4) and signed with a non-debug key
# (APK signature v2/v3), not a monolithic APK. This builds the release app bundle, turns it
# into an APK set signed with the release key, and checks the result.
#
# Usage: tools/accrescent_build.sh [KEYSTORE] [ALIAS]
#   KEYSTORE  default ~/.local/share/orb-release/orb-release.p12 (PKCS12)
#   ALIAS     default orb
# The keystore password is read from the terminal (or ORB_KS_PASS_FILE, a file holding it) and
# never placed on a command line. Output: dist/orb-<version>.apks and a .txt with its SHA-256
# and the signing certificate's SHA-256.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
KS=${1:-$HOME/.local/share/orb-release/orb-release.p12}
ALIAS=${2:-orb}
BUNDLETOOL_VERSION=1.18.3
BUNDLETOOL_SHA256=a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29
export JAVA_HOME=${JAVA_HOME:-$HOME/.local/jdk/jdk-21.0.13+9}
BT_DIR=$(ls -d "${ANDROID_HOME:-$HOME/Android/Sdk}"/build-tools/*/ | sort -V | tail -1)
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/orb-tools
log() { echo "accrescent_build: $*"; }
die() { echo "accrescent_build: $*" >&2; exit 1; }

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
PASSDIR=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/orb-ks.XXXXXX"); chmod 700 "$PASSDIR"
trap 'rm -rf "$PASSDIR"' EXIT
if [ -n "${ORB_KS_PASS_FILE:-}" ]; then
  install -m 600 "$ORB_KS_PASS_FILE" "$PASSDIR/pass"
else
  read -rsp "Keystore password for $KS: " P; echo
  ( umask 077; printf '%s' "$P" > "$PASSDIR/pass" ); unset P
fi

# Clean apply and build the release bundle.
cd "$ROOT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || log "warning: working tree has uncommitted changes"
python3 apply.py --reset >/dev/null
VERSION=$(python3 -c 'import apply; print(apply.read_version()[0])')
( cd mobileapp && ./gradlew -q :androidApp:bundleRelease --console=plain )
AAB=mobileapp/androidApp/build/outputs/bundle/release/androidApp-release.aab
[ -f "$AAB" ] || die "no bundle at $AAB"

mkdir -p dist
OUT="dist/orb-$VERSION.apks"
rm -f "$OUT"
"$JAVA_HOME/bin/java" -jar "$BT" build-apks --bundle="$AAB" --output="$OUT" \
  --ks="$KS" --ks-key-alias="$ALIAS" \
  --ks-pass="file:$PASSDIR/pass" --key-pass="file:$PASSDIR/pass"

# Checks: signed with a non-debug key (v2+), the expected package, 64-bit ARM present.
CHECK=$(mktemp -d); trap 'rm -rf "$PASSDIR" "$CHECK"' EXIT
unzip -qq "$OUT" -d "$CHECK"
BASE="$CHECK/splits/base-master.apk"
[ -f "$BASE" ] || die "no base-master split in $OUT"
CERTS=$("$BT_DIR/apksigner" verify -v --print-certs "$BASE" 2>/dev/null) || die "signature verification failed"
# (here-strings, not pipes: grep -q exiting early would trip pipefail)
grep -q 'Verified using v2 scheme (APK Signature Scheme v2): true' <<<"$CERTS" || die "not signed with v2"
grep -qi 'CN=Android Debug' <<<"$CERTS" && die "signed with a debug certificate"
CERT_SHA=$(sed -n 's/.*Signer: certificate SHA-256 digest: //p' <<<"$CERTS" | head -1)
PKG=$("$BT_DIR/aapt2" dump packagename "$BASE")
[ "$PKG" = com.orbcybersecurity.orb ] || die "unexpected package $PKG"
[ -f "$CHECK/splits/base-arm64_v8a.apk" ] || die "no arm64-v8a split"
for f in "$CHECK"/splits/*.apk; do
  "$BT_DIR/apksigner" verify "$f" >/dev/null 2>&1 || die "split not verified: $(basename "$f")"
done
SIZE=$(stat -c %s "$OUT")
SHA=$(sha256sum "$OUT" | cut -d' ' -f1)
{
  echo "file: $(basename "$OUT")"
  echo "version: $VERSION"
  echo "package: $PKG"
  echo "size: $SIZE bytes"
  echo "sha256: $SHA"
  echo "signing certificate sha256: $CERT_SHA"
  echo "splits: $(ls "$CHECK"/splits | wc -l) APKs"
} | tee "${OUT%.apks}.txt"
log "done: $OUT"
