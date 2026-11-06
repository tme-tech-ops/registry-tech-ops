#!/bin/sh
# create for env_precheck: puts the Harbor installer in the home directory.
#
# Airgapped mode downloads and extracts the offline package. Otherwise it
# downloads SCRIPT_URL. A GitHub release asset is checked against the
# SHA256SUMS of the same release and isn't kept if it doesn't match.
set -u

log() { ctx logger info "$1"; }
fail() { ctx logger error "$1"; exit 1; }

offline_mode=$(printf '%s' "${OFFLINE_MODE:-false}" | tr '[:upper:]' '[:lower:]')

if [ "$offline_mode" = "true" ]; then
    log "Offline mode detected."
    if [ -z "${OFFLINE_BINARY_URL:-}" ] || [ -z "${OFFLINE_BINARY_USER:-}" ] || [ -z "${OFFLINE_BINARY_PASSWORD:-}" ]; then
        fail "OFFLINE_BINARY_URL, OFFLINE_BINARY_USER, or OFFLINE_BINARY_PASSWORD is missing."
    fi
    archive="$HOME/$(basename "$OFFLINE_BINARY_URL")"
    log "Downloading offline binary..."
    curl -skfLu "${OFFLINE_BINARY_USER}:${OFFLINE_BINARY_PASSWORD}" "$OFFLINE_BINARY_URL" -o "$archive" \
        || fail "Failed to download offline binary."
    log "Extracting offline binary..."
    tar -xzf "$archive" -C "$HOME" || fail "Failed to extract offline binary."
    log "Offline binary downloaded and extracted."
    exit 0
fi

log "Online mode detected."
[ -n "${SCRIPT_URL:-}" ] || fail "SCRIPT_URL is missing."

script="$HOME/$(basename "$SCRIPT_URL")"
download="${script}.download"
rm -f "$download"
curl -sfL --retry 3 "$SCRIPT_URL" -o "$download" || fail "Failed to download ${SCRIPT_URL}."

case "$SCRIPT_URL" in
    https://github.com/*/releases/download/*/install_harbor.sh)
        sums_url="${SCRIPT_URL%/*}/SHA256SUMS"
        if ! sums=$(curl -sfL --retry 3 "$sums_url"); then
            rm -f "$download"
            fail "Failed to download ${sums_url}."
        fi
        expected=$(printf '%s\n' "$sums" | awk '$2 == "install_harbor.sh" || $2 == "*install_harbor.sh" { print $1; exit }')
        if [ -z "$expected" ]; then
            rm -f "$download"
            fail "${sums_url} has no entry for install_harbor.sh."
        fi
        actual=$(sha256sum "$download" | awk '{ print $1 }')
        if [ "$actual" != "$expected" ]; then
            rm -f "$download"
            fail "install_harbor.sh doesn't match ${sums_url} (expected ${expected}, got ${actual})."
        fi
        log "install_harbor.sh matches the release's SHA256SUMS (${actual})."
        ;;
    *)
        log "${SCRIPT_URL} isn't a GitHub release asset: no checksum to check."
        ;;
esac

if ! { mv -f "$download" "$script" && chmod +x "$script"; }; then
    fail "Failed to put the installer at ${script}."
fi
log "Install script downloaded and made executable: ${SCRIPT_URL}"
