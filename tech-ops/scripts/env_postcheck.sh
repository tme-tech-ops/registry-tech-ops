#!/bin/sh
# create and update for env_postcheck: reports whether Harbor answers and whether
# the deployment's credentials work, publishes Harbor's CA, and on create
# uploads an offline-prep package if asked. An update runs it after
# install_app's, to refresh the capabilities, and uploads nothing.
#
# The health check needs no credentials. The credentials are then checked on
# /api/v2.0/users/current, because Harbor treats bad credentials as anonymous
# on read calls such as /projects, which then still return 200. Only
# credentials Harbor accepted are published as capabilities.
#
# The capabilities are written as one runtime property, because DAP doesn't
# keep nested writes made in update operations.
set -u
# The fabric plugin leaves the settings in an env file on the VM. It holds passwords.
rm -f "$(dirname "$0")/env-$(basename "$0")"

log() { ctx logger info "$1"; }
warn() { ctx logger warning "$1"; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
# json_str <value>: a JSON string. \ and " are escaped, and lines are joined with \n
# (the inputs refuse other control characters).
json_str() {
    printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }')"
}
op=$(ctx operation name 2>/dev/null); op=${op##*.}

OFFLINE_PACKAGE_NAME="harbor-offline-package.tar.gz"
offline_package_uploaded="false"
offline_package_url="N/A"
new_offline_package_name=""
harbor_running="false"
harbor_ip_url="N/A"
harbor_fqdn_url="N/A"
cap_username="N/A"
cap_password="N/A"
cap_ca_cert="N/A"

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
    # The CA, for clients that have to trust the registry. No credentials needed.
    ca=$(curl -sk --max-time 10 "${base_url}/api/v2.0/systeminfo/getcert" 2>/dev/null) || ca=""
    case "$ca" in
        -----BEGIN\ CERTIFICATE-----*) cap_ca_cert="$ca" ;;
        *) warn "Harbor didn't return its CA certificate, so harbor_ca_cert isn't published." ;;
    esac
else
    log "Harbor is not running (health check: HTTP ${health_code})."
fi

if [ "$op" = "update" ]; then
    # An update uploads nothing: keep what the install published.
    for key in offline_package_name offline_package_uploaded offline_package_url; do
        value=$(ctx instance runtime-properties "capabilities.${key}" 2>/dev/null) || value=""
        case "$key" in
            offline_package_name) OFFLINE_PACKAGE_NAME=${value:-N/A}; new_offline_package_name=$OFFLINE_PACKAGE_NAME ;;
            offline_package_uploaded) offline_package_uploaded=${value:-false} ;;
            offline_package_url) offline_package_url=${value:-N/A} ;;
        esac
    done
elif [ -f "$HOME/${OFFLINE_PACKAGE_NAME}" ]; then
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
    package_name="$new_offline_package_name"
else
    package_name="$OFFLINE_PACKAGE_NAME"
fi
caps="{\"offline_package_name\": $(json_str "$package_name"),"
caps="$caps \"offline_package_uploaded\": $(json_str "$offline_package_uploaded"),"
caps="$caps \"offline_package_url\": $(json_str "$offline_package_url"),"
caps="$caps \"harbor_running\": $(json_str "$harbor_running"),"
caps="$caps \"harbor_ip_url\": $(json_str "$harbor_ip_url"),"
caps="$caps \"harbor_fqdn_url\": $(json_str "$harbor_fqdn_url"),"
caps="$caps \"harbor_username\": $(json_str "$cap_username"),"
caps="$caps \"harbor_password\": $(json_str "$cap_password"),"
caps="$caps \"harbor_ca_cert\": $(json_str "$cap_ca_cert")}"
ctx instance runtime-properties capabilities "@${caps}"
