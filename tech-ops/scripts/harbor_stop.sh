#!/bin/sh
set -u

# stop for install_app.
#
# Harbor and its data (images, projects, users, database) are removed only when
# this deployment is uninstalled, and only if its Install Task installed Harbor
# (install-harbor). An offline-prep deployment only built a package.
#
# Other workflows run stop too: a reinstall during an update ("Run automatic
# reinstall" or a reinstall list) and Heal. In those Harbor stays as it is, and
# the create that follows re-runs install-harbor. The installer this blueprint
# pins (v1.1.0 or later) then changes nothing when nothing changed. In an update,
# create refuses an installer older than v1.1.1. A Heal of a deployment installed
# from 1.2.0.0 still runs its older installer copy, which redeploys Harbor and
# replaces the server key.
#
# Uninstalling also removes the database dumps the installer made before each
# upgrade (/data/backup/harbor-installer, installer v1.2.0 and later).

workflow="$(ctx workflow-id 2>/dev/null || echo unknown)"

case "${workflow}" in
    uninstall)
        if [ "${RUN_ARG:-install-harbor}" = "install-harbor" ]; then
            if [ -x ~/install_harbor.sh ]; then
                ctx logger info "Uninstalling Harbor."
                (cd ~ && sudo -E ./install_harbor.sh uninstall-harbor) || exit 1
            else
                ctx logger info "install_harbor.sh not found in the home directory: nothing to uninstall."
            fi
        else
            ctx logger info "Install Task '${RUN_ARG}' didn't install Harbor: nothing to uninstall."
        fi
        ;;
    *)
        ctx logger info "Keeping Harbor and its data (${workflow} workflow): only uninstalling the deployment removes them."
        ;;
esac
