# registry-tech-ops

Blueprint for deploying Harbor OCI registry on an existing **edge-cloud-init** VM using the fabric-plugin.

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

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| POC VM Deployment Instance | `vm_deployment_id` | *(required, no default)* | The deployment ID of the existing `edge-cloud-init` deployment to deploy Harbor on top of |

### Registry Configuration

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| Harbor Version | `harbor_version` | `2.14.1` | Harbor release version to install |
| Harbor Port | `harbor_port` | `443` | HTTPS port Harbor will listen on |
| Harbor username | `harbor_username` | `admin` | Harbor basic authentication username |
| Harbor Password | `harbor_password` | `changeme` | Harbor basic authentication password |
| Docker CIDR | `docker_bridge_cidr` | `172.17.0.1/16` | IP CIDR range for the Docker bridge network |
| Registry Projects | `projects` | `chrislusf e2e-test-images library frrouting haproxytech longhornio metallb rancher velero grafana prom bats kiwigrid prometheus prometheus-operator ingress-nginx kube-state-metrics fluent` | Space-separated list of registry projects to auto-create on install. Defaults to all projects used by the tme-tech-ops suite |
| Debug Logging | `debug` | `1` | Set to `1` to enable or `0` to disable debug logging |

### Environment Configuration

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| Airgapped Mode | `offline_mode` | `false` | Set to `true` to download and install Harbor from an offline package instead of the internet |
| Offline Binary Configuration Secret | `offline_binary_secret` | *(no default)* | Secret (type: `binary_configuration`) containing the URL, credentials, and version of the offline Harbor archive. Only shown when **Airgapped Mode** is enabled |
| Install Task | `run_arg` | `install-harbor` | The install task to run. Valid values: `install-harbor` (standard install), `offline-prep` (download artifacts and create an offline package). Mutually exclusive with **Airgapped Mode** |
| Script URL | `script_url` | `https://github.com/Chubtoad5/harbor-registry-installer/raw/refs/heads/main/install_harbor.sh` | URL of the installer script to download and execute. Mutually exclusive with **Airgapped Mode** |
| Upload offline-prep package | `upload_package` | `false` | When using the `offline-prep` install task, set to `true` to upload the generated offline package to an HTTP server |
| Upload URL location | `upload_binary_secret` | *(no default)* | Secret (type: `binary_configuration`) pointing to the upload target location. Only shown when **Upload offline-prep package** is enabled |
| Log Output to hide | `hide_log_output` | `["stdout"]` | Controls which script output streams are suppressed in deployment logs. Valid values: `stdout`, `stderr`, `both` |

### Self-Signed Certificates

| Display Name | Input Key | Default | Description |
|---|---|---|---|
| Duration | `duration_days` | `365` | Validity period of the self-signed TLS certificate in days |
| Common Name | `common_name` | `registry.harbor.edge.lab` | Certificate Common Name (CN) — also used as the FQDN for the Harbor UI URL output |
| Country | `country` | `US` | Certificate country code (2-letter ISO) |
| State | `state` | `MA` | Certificate state or province |
| Location | `location` | `Hopkinton` | Certificate locality (city) |
| Organization | `organization` | `EdgeLab` | Certificate organization name |

## Outputs

After a successful deployment the following capabilities are exposed:

| Capability | Description |
|---|---|
| `harbor_running` | Boolean indicating whether the Harbor service is reachable post-install |
| `harbor_ip_url` | Harbor UI URL via management IP (e.g. `https://192.168.1.10:443`) |
| `harbor_fqdn_url` | Harbor UI URL via the configured Common Name FQDN (e.g. `https://registry.harbor.edge.lab:443`) |
| `harbor_username` | The Harbor admin username |
| `harbor_password` | The Harbor admin password |
| `offline_package_name` | Name of the generated offline package (populated when `run_arg: offline-prep`) |
| `offline_package_uploaded` | Whether the offline package was successfully uploaded |
| `offline_package_url` | URL where the offline package was uploaded |
