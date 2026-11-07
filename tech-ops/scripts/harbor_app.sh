#!/bin/sh
# create and update for install_app.
#
# create runs the Install Task (install-harbor or offline-prep) and records
# Harbor's state in the harbor_facts runtime property, which the update logic
# (update_logic.py, on the orchestrator) compares with each update.
#
# update runs only when update_logic.py found work: a new Harbor version,
# projects to create, a certificate in its renewal window, a raised counter or a
# new installer. In this order, it:
#   1. checks, changing nothing: Harbor answers, it accepts the deployment's
#      credentials, the installer is v1.1.1 or later, and the version doesn't go
#      down;
#   2. before an upgrade, checks the disk and dumps Harbor's database;
#   3. rotates the CA or renews the server certificate when its counter went up
#      (update-certificates);
#   4. re-runs install-harbor with every setting. The installer changes only what
#      differs: "No change", new projects, a renewal or an upgrade;
#   5. records the state again and checks the version.
#
# The settings arrive in an env file that the fabric plugin leaves on the VM,
# so the first thing this script does is delete it: it holds the password.
set -u
rm -f "$(dirname "$0")/env-$(basename "$0")"

log() { ctx logger info "$1"; }
warn() { ctx logger warning "$1"; }
fail() { ctx logger error "$1"; exit 1; }
num() { case "${1:-}" in ''|*[!0-9]*) echo 0 ;; *) echo "$1" ;; esac; }
# at_least <version> <minimum>
at_least() {
    [ -n "$1" ] || return 1
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)" = "$2" ]
}

op=$(ctx operation name 2>/dev/null); op=${op##*.}
workflow=$(ctx workflow-id 2>/dev/null || echo unknown)
task=${RUN_ARG:-install-harbor}
installer="$HOME/install_harbor.sh"
marker=/opt/harbor/.registry-tech-ops
py=${PYTHONBIN:-python3}
facts_py=$(ctx download-resource tech-ops/scripts/harbor_facts.py) || fail "Couldn't copy harbor_facts.py to the VM."
want_ca=$(num "${CA_ROTATIONS:-0}")
want_renew=$(num "${CERT_RENEWALS:-0}")

installer_version() { sed -n 's/^SCRIPT_VERSION="\([0-9.]*\)".*/\1/p' "$installer" 2>/dev/null | head -n 1; }

live_version() {
    image=$(sudo docker inspect -f '{{.Config.Image}}' harbor-core 2>/dev/null) || image=""
    case "$image" in *:v*) echo "${image##*:v}" ;; esac
}

# run_installer <command>, with the settings and anything exported before it
run_installer() { (cd "$HOME" && sudo -E ./install_harbor.sh "$1"); }

marker_value() { num "$(sudo sed -n "s/^$1=//p" "$marker" 2>/dev/null)"; }

# write_marker <CA rotations> <certificate renewals>: what has been applied on this VM
write_marker() {
    printf 'CA_ROTATIONS=%s\nCERT_RENEWALS=%s\n' "$1" "$2" | sudo tee "$marker" >/dev/null \
        && sudo chmod 600 "$marker"
}

record_facts() {
    facts=$("$py" "$facts_py") || return 1
    ctx instance runtime-properties harbor_facts "@${facts}"
}

# api_code <path>: HTTP code of a GET with the deployment's credentials. They go to
# curl on stdin, not its command line. Inside the double quotes, \ and " are escaped.
api_code() {
    esc_user=$(printf '%s' "$HARBOR_USERNAME" | sed 's/[\\"]/\\&/g')
    esc_pass=$(printf '%s' "$HARBOR_PASSWORD" | sed 's/[\\"]/\\&/g')
    printf 'user = "%s:%s"\n' "$esc_user" "$esc_pass" \
        | curl -sk --max-time 10 -K - -o /dev/null -w '%{http_code}' \
            "https://127.0.0.1:${HARBOR_PORT}/api/v2.0/$1" 2>/dev/null || true
}

free_kb() { df -Pk "$1" 2>/dev/null | awk 'NR == 2 { print $4 }'; }

# ---------------------------------------------------------------- create
if [ "$op" = "create" ]; then
    if [ "$workflow" = "update" ] && [ "$task" = "install-harbor" ] && ! at_least "$(installer_version)" 1.1.1; then
        fail "This deployment's Harbor installer is older than v1.1.1, and an update never runs it. Nothing was changed. Set Script URL to the installer release this blueprint version names as its default."
    fi
    log "Running install_harbor.sh ${task}."
    run_installer "$task" || fail "install_harbor.sh ${task} failed. Its output is above."
    [ "$task" = "install-harbor" ] || exit 0
    # A new deployment starts with its counters applied. Anywhere else, a missing
    # record means nothing has been applied yet.
    if ! sudo test -f "$marker"; then
        if [ "$workflow" = "install" ]; then
            write_marker "$want_ca" "$want_renew"
        else
            write_marker 0 0
        fi
    fi
    record_facts || warn "Harbor is installed, but its state couldn't be recorded. The next update records it."
    exit 0
fi

# ---------------------------------------------------------------- update
if [ "$op" != "update" ]; then
    fail "harbor_app.sh doesn't handle the ${op} operation."
fi
if [ "$task" != "install-harbor" ]; then
    log "Install Task ${task}: there's no Harbor to update."
    exit 0
fi

# 1. Checks. Nothing has changed if one of them stops the update.
health=$(curl -sk --max-time 10 -o /dev/null -w '%{http_code}' "https://127.0.0.1:${HARBOR_PORT}/api/v2.0/health" 2>/dev/null) || true
[ "$health" = "200" ] || fail "Harbor isn't answering on port ${HARBOR_PORT} (health check: HTTP ${health:-000}). Nothing was changed. A reinstall of install_app re-runs the installer and can repair it."
auth=$(api_code users/current)
case "$auth" in
    200) ;;
    401) fail "Harbor rejected the deployment's credentials for ${HARBOR_USERNAME}. If the password was changed in Harbor, change it back there: this version can't change the deployment's password. Nothing was changed." ;;
    *) fail "Checking the credentials returned HTTP ${auth}. Nothing was changed." ;;
esac

have=$(installer_version)
live=$(live_version)
done_ca=$(marker_value CA_ROTATIONS)
done_renew=$(marker_value CERT_RENEWALS)
[ -n "$live" ] || fail "Couldn't read the running Harbor version (docker inspect harbor-core). Nothing was changed."

if ! at_least "$have" 1.1.1; then
    asked=""
    [ "$HARBOR_VERSION" = "$live" ] || asked="${asked} Harbor Version,"
    [ "$want_ca" -le "$done_ca" ] || asked="${asked} CA Rotations,"
    [ "$want_renew" -le "$done_renew" ] || asked="${asked} Certificate Renewals,"
    missing=$("$py" "$facts_py" missing 2>/dev/null) || missing=""
    [ -z "$missing" ] || asked="${asked} Registry Projects,"
    if [ -n "$asked" ]; then
        fail "This deployment's Harbor installer (${have:-older than v1.1.0}) is older than v1.1.1, so this update can't change${asked%,}. Nothing was changed. Set Script URL to the installer release this blueprint version names as its default."
    fi
    record_facts || fail "Couldn't record Harbor's state."
    log "The installer is older than v1.1.1, so this update only recorded Harbor's state."
    exit 0
fi

if [ "$HARBOR_VERSION" != "$live" ]; then
    if at_least "$live" "$HARBOR_VERSION"; then
        fail "Harbor ${live} is running and Harbor Version ${HARBOR_VERSION} is older. An older Harbor can't start on a newer database. Nothing was changed."
    fi
    if [ "$(printf '%s' "${OFFLINE_MODE:-false}" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
        fail "Upgrading Harbor in airgapped mode isn't supported yet. Nothing was changed."
    fi

    # 2. Before the upgrade: room for the new images, and a database dump.
    # (Until the pinned installer makes the dump itself.)
    docker_root=$(sudo docker info -f '{{.DockerRootDir}}' 2>/dev/null) || docker_root=/var/lib/docker
    for dir in "$docker_root" /data; do
        free=$(num "$(free_kb "$dir")")
        [ "$free" -ge 4194304 ] || fail "Upgrading Harbor needs 4 GB free on ${dir}, and $((free / 1048576)) GB is free. Nothing was changed."
    done
    dump="/data/backup/registry-tech-ops/harbor-db-v${live}-$(date -u +%Y%m%d%H%M%S).sql.gz"
    log "Dumping Harbor's database to ${dump} before upgrading ${live} to ${HARBOR_VERSION}."
    sudo sh -c 'umask 077 && mkdir -p "$(dirname "$1")" && docker exec harbor-db pg_dumpall -U postgres | gzip > "$1"' sh "$dump" \
        || fail "The database dump failed. Nothing was changed."
    sudo sh -c 'gzip -dc "$1" | head -c 4096 | grep -q "PostgreSQL database cluster dump"' sh "$dump" \
        || fail "The database dump ${dump} is empty or incomplete. Nothing was changed."
    log "Database dumped. To restore after a failed upgrade, see the README (Restoring Harbor's database)."
fi

# 3. Certificate actions, before install-harbor, so a CA that has expired can be
# replaced first: install-harbor refuses to run on one.
# shellcheck disable=SC2030,SC2031 # NEW_CERT_GEN and ROTATE_CA are for that one run only
if [ "$want_ca" -gt "$done_ca" ]; then
    log "CA Rotations ${done_ca} -> ${want_ca}: replacing the CA. Every client must trust the new one (capability harbor_ca_cert)."
    (export NEW_CERT_GEN=1 ROTATE_CA=true; run_installer update-certificates) \
        || fail "install_harbor.sh update-certificates failed. The installer puts the previous certificates back. Its output is above."
    [ "$want_renew" -gt "$done_renew" ] && done_renew=$want_renew
    done_ca=$want_ca
    write_marker "$done_ca" "$done_renew" || fail "The CA was replaced, but ${marker} couldn't be written."
elif [ "$want_renew" -gt "$done_renew" ]; then
    log "Certificate Renewals ${done_renew} -> ${want_renew}: issuing a new server certificate under the same CA."
    (export NEW_CERT_GEN=1; run_installer update-certificates) \
        || fail "install_harbor.sh update-certificates failed. The installer puts the previous certificates back. Its output is above."
    done_renew=$want_renew
    write_marker "$done_ca" "$done_renew" || fail "The certificate was renewed, but ${marker} couldn't be written."
fi

# 4. Every setting (Q15). The installer decides what differs.
log "Running install_harbor.sh install-harbor with the deployment's settings (Harbor ${HARBOR_VERSION})."
run_installer install-harbor || fail "install_harbor.sh install-harbor failed. Its output is above."

# 5. The state after the update.
record_facts || fail "Harbor was updated, but its state couldn't be recorded."
now=$(live_version)
[ "$now" = "$HARBOR_VERSION" ] || fail "Harbor ${now:-unknown} is running after the update, not ${HARBOR_VERSION}."
log "Harbor ${now} is up to date with the deployment's settings."
