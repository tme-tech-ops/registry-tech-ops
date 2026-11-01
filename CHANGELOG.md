# Changelog for registry-tech-ops

All notable changes to this blueprint are recorded here. The version is also
the catalog revision to upload the blueprint as.

## 1.2.0.0 - 2026-10-31

Safe deployment updates (Day-2). Works on a VM from edge-cloudinit-linux
1.0.0 or 1.2.0.0.

- Fixed: an update could delete the registry. `install_app`'s `stop` ran
  `uninstall-harbor`, and an update's automatic reinstall, a reinstall list or
  Heal runs `stop`. Harbor and its data are now removed only when the
  deployment is uninstalled, and only for an `install-harbor` deployment.
- Changed: an update never re-runs the installer. `env_precheck`,
  `install_app` and `env_postcheck` report no drift and have no update
  operation. Changed settings used to be ignored anyway; every input is now
  locked (see "Updating a Deployment" in the README).
- Fixed: `tech-ops/definitions.yaml` set `host_string` twice, a YAML parse
  error for strict readers. The update operation also lacked
  `enable_socks5: false`; it is gone with the update operation.
- Fixed: 13 inputs pointed at display groups that don't exist, so the form
  showed them ungrouped; they now sit in Registry Configuration and
  Self-Signed Certificates.
- Fixed: `offline_package_name` reported the old file name after an upload
  and nothing without one. It now reports the uploaded (timestamped) name,
  or the package's name when it wasn't uploaded.
- Fixed: in airgapped mode the Install Task is hidden and arrived empty, so
  the install command had no task; it now runs `install-harbor`.
- Fixed: the offline download command was logged with its password.
- Changed: `script_url` defaults to a pinned installer commit instead of the
  installer's `main` branch.
- Changed: plugin imports moved to the entry file (fabric only; edge and
  utilities were unused); unused hidden inputs removed; every constraint has
  an error message; the certificate duration, port and debug inputs are
  validated; the version label is corrected (was 4.1.0.0). Lint: the remaining
  findings are the plain-text `harbor_password` input, left for the
  credentials change (secret inputs) that follows this release.

## 1.1.5.0

Release restructure and pinning supported plugins for DAP 2.0.0.1 / DDPC 4.2.0.0 -
untested (2026-11-01).

- This branch, `ddpc-4.2.0.0-snapshot`: the 1.2.0.0 code for DAP 2.0.0.1 with
  DDPC 4.2.0.0. Version label 1.1.5.0. Not tested on that platform.
- Imports only the fabric-plugin, unchanged (no pin needed).
- DAP 2.0.0.1 doesn't ship the fabric-plugin: upload it before this blueprint.

## 1.0.0

Catalog revision 1.0.0, before this changelog.
