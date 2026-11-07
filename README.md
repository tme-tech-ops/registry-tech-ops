# registry-tech-ops

Blueprint for deploying Harbor OCI registry on an existing **edge-cloud-init** VM using the fabric-plugin.  
  
This blueprint is designed for **NativeEdge Endpoints** on **Dell Automation Platform**


## Releases

| Release | DAP | DDPC | Version | Tested |
|---|---|---|---|---|
| [`1.2.1.0`](https://github.com/tme-tech-ops/registry-tech-ops/releases/tag/1.2.1.0) | 2.1.1.0 | 4.3.0.0 | 1.2.1.0 | yes |
| [`1.2.0.0`](https://github.com/tme-tech-ops/registry-tech-ops/releases/tag/1.2.0.0) | 2.1.1.0 | 4.3.0.0 | 1.2.0.0 | yes |
| [`1.1.5.0`](https://github.com/tme-tech-ops/registry-tech-ops/releases/tag/1.1.5.0) | 2.0.0.1 | 4.2.0.0 | 1.1.5.0 (branch `ddpc-4.2.0.0-snapshot`) | no |

Download the zip attached to the release that matches your DAP and DDPC versions (not
"Source code"); its notes give the blueprint name, revision and upload order.

### Harbor installer

Each version runs a fixed release of
[harbor-registry-installer](https://github.com/Chubtoad5/harbor-registry-installer), the
default of **Script URL**:

| Blueprint | Installer |
|---|---|
| 1.3.0.0 | [`v1.1.1`](https://github.com/Chubtoad5/harbor-registry-installer/releases/tag/v1.1.1), checked against the release's `SHA256SUMS` |
| 1.2.1.0 | [`v1.1.1`](https://github.com/Chubtoad5/harbor-registry-installer/releases/tag/v1.1.1), checked against the release's `SHA256SUMS` |
| 1.2.0.0 | commit `1bd7b54`, since tagged [`v1.0.0`](https://github.com/Chubtoad5/harbor-registry-installer/releases/tag/v1.0.0) |

## Prerequisites

This blueprint **must be deployed on top of an existing `edge-cloud-init` deployment** from the tme-tech-ops suite. The `edge-cloud-init` deployment provides the target VM and exposes the SSH connection details (hostname, user, and private key) that this blueprint consumes via shared resource capabilities.

The target `edge-cloud-init` deployment must be labeled with:
- `csys-obj-type: environment`
- `solution: edge-cloud-init`

## Required Secrets

| Secret | Type | When Required | Description |
|--------|------|---------------|-------------|
| `offline_binary_secret` | `binary_configuration` | When **Airgapped Mode** is enabled | Contains `url`, `username`, `access_token`, and `version` fields pointing to the offline Harbor archive package |
| `upload_binary_secret` | `binary_configuration` | When **Upload offline-prep package** is enabled | Contains `url`, `username`, `access_token`, and `version` fields pointing to the target upload location (e.g. `https://myfileserver.lab/upload_dir/`) |

> **Note:** The SSH private key used to connect to the target VM is automatically sourced from the `edge-cloud-init` deployment's capabilities. No separate SSH secret needs to be configured in this blueprint.

## Inputs

### Deployment Target

Choose the `edge-cloud-init` deployment in **Deploy On**. The VM's name, user, SSH key and
proxy target come from that deployment's capabilities; there is no input for them.

### Registry Configuration

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| Harbor Version | `harbor_version` | `2.15.0` | Harbor release version to install, such as `2.15.0` (no leading `v`). An update to a later version upgrades Harbor (see "Updating a Deployment") |
| Harbor Port | `harbor_port` | `443` | HTTPS port Harbor will listen on |
| Harbor Username | `harbor_username` | `admin` | Harbor administrator. `admin` is Harbor's built-in account. Another name becomes a second system administrator with the same password (Harbor can't rename `admin`), and needs a password of at least 8 characters with a lowercase letter, an uppercase letter and a digit |
| Harbor Password | `harbor_password` | `changeme` | Harbor administrator password. Harbor hands it to its containers in an env file, which expands `$` and treats a space followed by `#` as a comment, so these are refused: single quotes (`'`), dollar signs (`$`), a `#` after a space, a space or `"` at the start, a space at the end, and control characters |
| Docker CIDR | `docker_bridge_cidr` | `172.17.0.1/16` | IP CIDR range for the Docker bridge network |
| Registry Projects | `projects` | `chrislusf e2e-test-images library frrouting haproxytech longhornio metallb rancher velero grafana prom bats kiwigrid prometheus prometheus-operator ingress-nginx kube-state-metrics fluent` | Space-separated Harbor project names to create on install (lowercase letters, digits, `.`, `_`, `-`). Defaults to all projects used by the tme-tech-ops suite; empty creates none. An update creates the names added, and Harbor keeps projects removed from the list |
| Debug Logging | `debug` | `1` | Set to `1` to enable or `0` to disable debug logging |

### Environment Configuration

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| Airgapped Mode | `offline_mode` | `false` | Set to `true` to download and install Harbor from an offline package instead of the internet |
| Offline Binary Configuration Secret | `offline_binary_secret` | *(no default)* | Secret (type: `binary_configuration`) containing the URL, credentials, and version of the offline Harbor archive. Only shown when **Airgapped Mode** is enabled |
| Install Task | `run_arg` | `install-harbor` | The install task to run. Valid values: `install-harbor` (standard install), `offline-prep` (download artifacts and create an offline package). Mutually exclusive with **Airgapped Mode** |
| Script URL | `script_url` | *(pinned installer release)* | URL of the installer script to download and execute; the default is the installer release this version was tested with (see "Harbor installer"). A GitHub release asset is checked against that release's `SHA256SUMS`, and the install stops on a mismatch. An update keeps the URL a deployment was created with, so change it to move a deployment to another installer; updates need `v1.1.1` or later. Mutually exclusive with **Airgapped Mode** |
| Upload offline-prep package | `upload_package` | `false` | When using the `offline-prep` install task, set to `true` to upload the generated offline package to an HTTP server |
| Upload URL location | `upload_binary_secret` | *(no default)* | Secret (type: `binary_configuration`) pointing to the upload target location. Only shown when **Upload offline-prep package** is enabled |
| Log Output to hide | `hide_log_output` | `["stdout"]` | Controls which script output streams are suppressed in deployment logs. Valid values: `stdout`, `stderr`, `both` |

### Self-Signed Certificates

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| Duration | `duration_days` | `365` | Days the server certificate is valid (31 or more). An update in its last 30 days renews it under the same CA. A change applies to the next certificate issued |
| Common Name | `common_name` | `registry.harbor.edge.lab` | Certificate Common Name (CN) — also used as the FQDN for the Harbor UI URL output |
| Country | `country` | `US` | Certificate country code (2-letter ISO) |
| State | `state` | `MA` | Certificate state or province |
| Location | `location` | `Hopkinton` | Certificate locality (city) |
| Organization | `organization` | `EdgeLab` | Certificate organization name |
| CA Rotations | `ca_rotations` | `0` | Raise by one in an update to replace the CA and the server certificate. Every client must then trust the new CA (`harbor_ca_cert`). It can't go down |
| Certificate Renewals | `cert_renewals` | `0` | Raise by one in an update to issue a new server certificate under the same CA. Clients keep working. It can't go down |

## Outputs

After a successful deployment the following capabilities are exposed:

| Capability | Description |
|---|---|
| `harbor_running` | Whether Harbor answers its health check (`/api/v2.0/health`) after the install |
| `harbor_ip_url` | Harbor UI URL via management IP (e.g. `https://192.168.1.10:443`) |
| `harbor_fqdn_url` | Harbor UI URL via the configured Common Name FQDN (e.g. `https://registry.harbor.edge.lab:443`) |
| `harbor_ca_cert` | Harbor's CA certificate (PEM), for clients that have to trust the registry. It changes when the CA is rotated |
| `harbor_username` | The Harbor administrator, if Harbor accepted its credentials (otherwise `N/A`) |
| `harbor_password` | The Harbor administrator's password, if Harbor accepted it (otherwise `N/A`) |
| `offline_package_name` | Name of the generated offline package (populated when `run_arg: offline-prep`) |
| `offline_package_uploaded` | Whether the offline package was successfully uploaded |
| `offline_package_url` | URL where the offline package was uploaded |

## Updating a Deployment

An update changes Harbor only when one of these changed, and leaves its data in
place:

| In the update | What happens on the VM |
|---|---|
| Nothing, and the certificate has more than 30 days left | Nothing |
| Nothing, and the certificate is in its last 30 days | The installer issues a new server certificate under the same CA and redeploys Harbor (about a minute's outage). Clients keep working |
| **Harbor Version**, higher | The update checks the credentials and the disk (4 GB free), dumps Harbor's database, then upgrades Harbor (about a minute's outage) |
| **Harbor Version**, lower | Refused before anything runs: an older Harbor can't start on a newer database |
| **Registry Projects**, names added | They are created. Names removed are kept in Harbor, with a warning |
| **CA Rotations**, raised by one | A new CA and server certificate. Every client must then trust the new CA (`harbor_ca_cert`) |
| **Certificate Renewals**, raised by one | A new server certificate under the same CA |
| **Script URL** | That installer is downloaded and checked, then re-run with the deployment's settings |
| **Duration**, **Debug Logging**, **Log Output to hide** | Nothing now: they apply to the next run or certificate |

Every other input is fixed at install, and DAP refuses a change to it. The
update's preview shows the same plan as the update: the checks run on the
orchestrator, from what the last run recorded on the deployment
(`harbor_facts` on `install_app`). Changes made by hand in Harbor, such as a
project deleted in its UI, aren't seen. A reinstall of `install_app` and
`env_postcheck` re-runs the installer and refreshes everything.

- **Refused updates** fail with the reason on the `update_checks` node and
  change nothing: a lower version, a version change in airgapped mode, any
  change to an `offline-prep` deployment, a lowered counter, a CA that has
  expired unless CA Rotations goes up, and a Duration within the 30-day renewal
  window. On the VM, the update also stops before changing anything if Harbor
  isn't answering or rejects the deployment's credentials. If you changed the
  password in Harbor's UI, change it back there: an update can't change it.
- **Renewal needs an update.** DAP doesn't run updates by itself, so run one
  with no change in the certificate's last 30 days. With the default Duration of
  365, that's once a year. On installer `v1.1.1` the CA lasts as long as the
  first server certificate, so a deployment's first renewal is a CA rotation.
- **A failed update** keeps the inputs it sent, as DAP does for every failed
  update, so send the right values in the next one. With "Run automatic
  reinstall" ticked, `install_app` is reinstalled: Harbor stays, and the
  installer runs again with the same settings.
- **Deployments from 1.2.1.0:** the first update to 1.3.0.0 records Harbor's
  state, and the installer reports "No change".
- **Deployments from 1.2.0.0** still have installer `1bd7b54` on the VM. Their
  first update only records the state. Other changes are refused until Script
  URL is set to this version's default. That update redeploys Harbor once (a
  short outage), and keeps its data and CA.
- **Uninstalling** an `install-harbor` deployment uninstalls Harbor and deletes
  its data (images, projects, users, database), and the database dumps made by
  updates. Uninstalling an `offline-prep` deployment leaves the VM's Harbor, if
  any, alone.
- **A Heal** of `install_app` re-runs the installer with the deployment's
  settings, which changes nothing when nothing changed.
- To resize the VM under the registry, update its **edge-cloudinit-linux**
  deployment with Force ticked (this deployment depends on it). Harbor comes back
  after the VM restarts.
- If the VM gets a new IP address, the next update that runs the installer puts
  the new address in the certificate and in `harbor_ip_url`. The FQDN URL keeps
  working if DNS follows the VM.

### Restoring Harbor's database

Before an upgrade, the update dumps Harbor's database (`pg_dumpall` from
`harbor-db`, gzipped, root only) to
`/data/backup/registry-tech-ops/harbor-db-v<old version>-<UTC time>.sql.gz` and
names the file in the event log. If an upgrade fails and Harbor doesn't come back,
restore that dump into the old version, following the restore steps of the
installer release this version pins.

See [CHANGELOG.md](CHANGELOG.md) for the changes in each version.
