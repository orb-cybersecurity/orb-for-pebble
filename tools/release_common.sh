#!/usr/bin/env bash
# Shared release identity. Changing this breaks Android updates for existing installations.
readonly ORB_CERT_SHA256=2e3e6c81aa66f5f11ac8d4cbe369e5ec7e98019ef0f4aaa5259c0c1421154621

orb_apk_certificate() {
  local sdk build_tools certificates digest
  sdk=${ANDROID_HOME:-$HOME/Android/Sdk}
  build_tools=$(ls -d "$sdk"/build-tools/*/ | sort -V | tail -1) || return 1
  certificates=$("$build_tools/apksigner" verify --print-certs "$1") || return 1
  digest=$(sed -n 's/.*certificate SHA-256 digest: //p' <<<"$certificates" | tr '[:upper:]' '[:lower:]' | tr -d ':\r')
  if [ "$digest" != "$ORB_CERT_SHA256" ]; then
    echo "Signing certificate does not match Orb's published SHA-256" >&2
    return 1
  fi
  printf '%s\n' "$digest"
}
