# Changelog for registry-tech-ops

All notable changes to this blueprint are recorded here. The version is also
the catalog revision to upload the blueprint as.

## 1.2.1.0 - 2026-11-06

Moves to harbor-registry-installer `v1.1.1` and fixes what was wrong in 1.2.0.0.
Updating a 1.2.0.0 deployment to it changes nothing on the VM.

- Changed: `script_url` defaults to the installer's `v1.1.1` release asset
  instead of commit `1bd7b54`. `env_precheck` checks a GitHub release asset
  against that release's `SHA256SUMS` and stops on a mismatch, and no longer
  downloads with `curl -k`. With `v1.1.1`, an unchanged re-run (a reinstall or
  Heal of `install_app`) changes nothing, a failed upgrade no longer records the
  new version, and the helper scripts it downloads are pinned too.
- Fixed: text values reached the installer through an unquoted shell `export`,
  so `$`, backticks, `\` and spaces in a password or other value were changed or
  broke the command. They are now single-quoted, and the inputs refuse a single
  quote. Host name, country, subject fields, user name, Docker CIDR and projects
  are validated.
- Fixed: `env_postcheck` checked `/api/v2.0/projects` with the credentials,
  which Harbor answers with 200 for wrong credentials too, so a wrong password
  was reported as working and published. It now checks `/api/v2.0/health`, with
  retries after an install, then the credentials on `/api/v2.0/users/current`,
  and publishes only credentials Harbor accepted.
- Fixed: cleared Registry Projects could arrive as null; an empty value now
  creates no projects.
- Fixed: the README said a reinstall leaves a running Harbor alone; on 1.2.0.0
  it redeploys. The README also listed a `vm_deployment_id` input that doesn't
  exist (the target is chosen in Deploy On).
- Changed: `harbor_version` defaults to 2.15.0, the installer's default, and
  must look like `2.15.0`; `v2.15.0` used to build a broken download URL.
- Changed: in online mode the installer gets `HARBOR_FORCE_ONLINE=true`, so a
  package left on the VM by an earlier `offline-prep` deployment can't switch an
  online install to the offline package.
- Changed: a Harbor Username other than `admin` now works (installer `v1.1.0`):
  it becomes a second system administrator and needs a stronger password. The
  description says so.

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

- On branch `ddpc-4.2.0.0-snapshot`, not on `main`: the 1.2.0.0 code for DAP
  2.0.0.1 with DDPC 4.2.0.0, not tested on that platform.
- Imports only the fabric-plugin, unchanged (no pin needed).
- Tags are now blueprint versions. Each has a GitHub release named after the DAP
  and DDPC versions it was tested on, with upload-ready zips.

## 1.0.0

Catalog revision 1.0.0, before this changelog.
