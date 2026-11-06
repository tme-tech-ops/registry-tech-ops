#!/bin/sh
# create for env_postcheck: reports whether Harbor answers and whether the
# deployment's credentials work, then uploads an offline-prep package if asked.
#
# The health check needs no credentials. The credentials are then checked on
# /api/v2.0/users/current, because Harbor treats bad credentials as anonymous
# on read calls such as /projects, which then still return 200. Only
# credentials Harbor accepted are published as capabilities.
set -u

log() { ctx logger info "$1"; }
warn() { ctx logger warning "$1"; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

OFFLINE_PACKAGE_NAME="harbor-offline-package.tar.gz"
offline_package_uploaded="false"
offline_package_url="N/A"
new_offline_package_name=""
harbor_running="false"
harbor_ip_url="N/A"
harbor_fqdn_url="N/A"
cap_username="N/A"
cap_password="N/A"

mgmt_ip=$(hostname -I | awk '{ print $1 }')
base_url="https://${mgmt_ip}:${HARBOR_PORT}"

log "Post install check started."

# install-harbor has just finished, so give Harbor up to two minutes.
# offline-prep installs nothing: one look is enough.
if [ "${RUN_ARG:-install-harbor}" = "install-harbor" ]; then
    attempts=12
else
    attempts=1
fi

health_code="000"
health_status=""
n=0
while [ "$n" -lt "$attempts" ]; do
    n=$((n + 1))
    reply=$(curl -sk --max-time 10 -w '\n%{http_code}' "${base_url}/api/v2.0/health" 2>/dev/null) || true
    health_code=$(printf '%s\n' "$reply" | tail -n 1)
    health_status=$(printf '%s\n' "$reply" | grep -o '"status": *"[a-z]*"' | head -n 1 | sed 's/.*"\([a-z]*\)"$/\1/')
    if [ "$health_code" = "200" ] && [ "$health_status" = "healthy" ]; then
        break
    fi
    [ "$n" -lt "$attempts" ] && sleep 10
done

if [ "$health_code" = "200" ]; then
    harbor_running="true"
    harbor_ip_url="$base_url"
    harbor_fqdn_url="https://${COMMON_NAME}:${HARBOR_PORT}"
    if [ "$health_status" = "healthy" ]; then
        log "Harbor is running."
    else
        warn "Harbor is running, but reports status '${health_status:-unknown}' on /api/v2.0/health."
    fi

    # The credentials go to curl on stdin, in a config line, so they aren't on
    # its command line. Inside its double quotes, \ and " are escaped.
    esc_user=$(printf '%s' "$HARBOR_USERNAME" | sed 's/[\\"]/\\&/g')
    esc_pass=$(printf '%s' "$HARBOR_PASSWORD" | sed 's/[\\"]/\\&/g')
    auth_code=$(printf 'user = "%s:%s"\n' "$esc_user" "$esc_pass" \
        | curl -sk --max-time 10 -K - -o /dev/null -w '%{http_code}' "${base_url}/api/v2.0/users/current" 2>/dev/null) || true
    case "$auth_code" in
        200)
            log "Harbor accepted the credentials for ${HARBOR_USERNAME}."
            cap_username="$HARBOR_USERNAME"
            cap_password="$HARBOR_PASSWORD"
            ;;
        401)
            warn "Harbor is running, but it rejected the credentials for ${HARBOR_USERNAME}. They aren't published."
            ;;
        *)
            warn "Harbor is running, but checking the credentials returned HTTP ${auth_code}. They aren't published."
            ;;
    esac
else
    log "Harbor is not running (health check: HTTP ${health_code})."
fi

if [ -f "$HOME/${OFFLINE_PACKAGE_NAME}" ]; then
    log "Offline package found."
    log "Upload package: ${UPLOAD_OFFLINE_PACKAGE}"
    if [ "$(lower "${UPLOAD_OFFLINE_PACKAGE}")" = "true" ]; then
        log "Uploading offline package..."
        new_offline_package_name="$(date +%Y%m%d%H%M)-${OFFLINE_PACKAGE_NAME}"
        mv "$HOME/${OFFLINE_PACKAGE_NAME}" "$HOME/${new_offline_package_name}"
        if [ -z "${UPLOAD_BASE_URL:-}" ] || [ -z "${UPLOAD_OFFLINE_PACKAGE_USER:-}" ] || [ -z "${UPLOAD_OFFLINE_PACKAGE_PASSWORD:-}" ]; then
            log "UPLOAD_BASE_URL, UPLOAD_OFFLINE_PACKAGE_USER, or UPLOAD_OFFLINE_PACKAGE_PASSWORD is missing."
            exit 1
        fi
        offline_package_url="${UPLOAD_BASE_URL}${new_offline_package_name}"
        if ! curl -ku "${UPLOAD_OFFLINE_PACKAGE_USER}:${UPLOAD_OFFLINE_PACKAGE_PASSWORD}" \
            -X POST "$offline_package_url" \
            -F "file=@$HOME/${new_offline_package_name}"; then
            log "Failed to upload offline package."
            exit 1
        fi
        offline_package_uploaded="true"
        log "Offline package uploaded to ${offline_package_url}."
    fi
else
    log "Offline package not found."
    OFFLINE_PACKAGE_NAME="N/A"
fi

log "Post install check completed."
# An uploaded package was renamed with a timestamp before the upload.
if [ "$offline_package_uploaded" = "true" ]; then
    ctx instance runtime-properties capabilities.offline_package_name "$new_offline_package_name"
else
    ctx instance runtime-properties capabilities.offline_package_name "$OFFLINE_PACKAGE_NAME"
fi
ctx instance runtime-properties capabilities.offline_package_uploaded "$offline_package_uploaded"
ctx instance runtime-properties capabilities.offline_package_url "$offline_package_url"
ctx instance runtime-properties capabilities.harbor_running "$harbor_running"
ctx instance runtime-properties capabilities.harbor_ip_url "$harbor_ip_url"
ctx instance runtime-properties capabilities.harbor_fqdn_url "$harbor_fqdn_url"
ctx instance runtime-properties capabilities.harbor_username "$cap_username"
ctx instance runtime-properties capabilities.harbor_password "$cap_password"
