"""Runs tech-ops/scripts/harbor_app.sh with stand-ins for ctx, sudo, docker, curl,
df and the installer, so its paths can be checked without a VM.

Run from the repo root: python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tech-ops/scripts/harbor_app.sh"

STUBS = {
    # ctx: answers what harbor_app.sh asks, and records the rest.
    "ctx": r'''
        #!/bin/sh
        echo "$*" >> "$T/ctx.log"
        case "$1 $2" in
            "operation name") echo "dell.interfaces.lifecycle.$OP" ;;
            "workflow-id ") echo "$WORKFLOW" ;;
            "download-resource tech-ops/scripts/harbor_facts.py") echo "$T/facts.sh" ;;
            "instance runtime-properties") printf '%s' "${4#@}" > "$T/harbor_facts.json" ;;
        esac
    ''',
    # sudo: runs the command as this user, with /opt/harbor and /data under $T/root.
    "sudo": r'''
        #!/bin/sh
        while [ $# -gt 0 ]; do case "$1" in -E|-n) shift ;; *) break ;; esac; done
        for a in "$@"; do
            case "$a" in
                /opt/harbor*|/data*) set -- "$@" "$T/root$a" ;;
                *) set -- "$@" "$a" ;;
            esac
            shift
        done
        exec "$@"
    ''',
    "docker": r'''
        #!/bin/sh
        case "$1" in
            inspect) echo "goharbor/harbor-core:v$(cat "$T/live")" ;;
            info) echo "$T/docker" ;;
            exec) printf -- '--\n-- PostgreSQL database cluster dump\n--\n' ;;
        esac
    ''',
    "curl": r'''
        #!/bin/sh
        for a in "$@"; do url=$a; done
        cat > /dev/null 2>&1 < /dev/null
        case "$url" in
            */health) printf '%s' "$HEALTH" ;;
            */users/current) cat > /dev/null; printf '%s' "$AUTH" ;;
        esac
    ''',
    "df": r'''
        #!/bin/sh
        printf 'Filesystem 1024-blocks Used Available Capacity Mounted\nx 1 1 %s 1%% /\n' "$FREE_KB"
    ''',
}

INSTALLER = r'''
#!/bin/sh
SCRIPT_VERSION="__VERSION__"
echo "$1 NEW_CERT_GEN=${NEW_CERT_GEN:-} ROTATE_CA=${ROTATE_CA:-} HARBOR_VERSION=$HARBOR_VERSION" >> "$T/installer.log"
[ "$1" = "$FAIL_ON" ] && exit 1
[ "$1" = "install-harbor" ] && printf '%s' "$HARBOR_VERSION" > "$T/live"
exit 0
'''

FACTS = r'''
#!/bin/sh
if [ "${1:-}" = missing ]; then printf '%s' "$MISSING"; exit 0; fi
printf '{"harbor_version": "%s", "ca_rotations": %s}' "$(cat "$T/live")" \
    "$(sed -n 's/^CA_ROTATIONS=//p' "$T/root/opt/harbor/.registry-tech-ops" 2>/dev/null || echo 0)"
'''


class HarborAppTests(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.t)
        bin_dir = self.t / "bin"
        bin_dir.mkdir()
        for name, body in STUBS.items():
            path = bin_dir / name
            path.write_text(textwrap.dedent(body).lstrip())
            path.chmod(0o755)
        (self.t / "facts.sh").write_text(FACTS.lstrip())
        (self.t / "root/opt/harbor").mkdir(parents=True)
        (self.t / "root/data").mkdir(parents=True)
        (self.t / "home").mkdir()
        (self.t / "live").write_text("2.14.1")
        self.scripts = self.t / "nativeedge-ctx/scripts"
        self.scripts.mkdir(parents=True)
        self.installer("1.1.1")

    def installer(self, version):
        path = self.t / "home/install_harbor.sh"
        path.write_text(INSTALLER.lstrip().replace("__VERSION__", version))
        path.chmod(0o755)

    def marker(self, ca=0, renew=0):
        (self.t / "root/opt/harbor/.registry-tech-ops").write_text(f"CA_ROTATIONS={ca}\nCERT_RENEWALS={renew}\n")

    def run_op(self, op="update", workflow="update", **env):
        script = self.scripts / "harbor_app.sh-abc12345"
        shutil.copy(SCRIPT, script)
        script.chmod(0o755)
        env_file = self.scripts / "env-harbor_app.sh-abc12345"
        env_file.write_text("export HARBOR_PASSWORD='secret'\n")
        values = {"PATH": f"{self.t / 'bin'}:{os.environ['PATH']}", "HOME": str(self.t / "home"),
                  "T": str(self.t), "OP": op, "WORKFLOW": workflow, "PYTHONBIN": "sh",
                  "HEALTH": "200", "AUTH": "200", "FREE_KB": "10485760", "MISSING": "", "FAIL_ON": "none",
                  "RUN_ARG": "install-harbor", "HARBOR_VERSION": "2.14.1", "HARBOR_PORT": "443",
                  "HARBOR_USERNAME": "admin", "HARBOR_PASSWORD": "secret", "OFFLINE_MODE": "false",
                  "CA_ROTATIONS": "0", "CERT_RENEWALS": "0"}
        values.update(env)
        done = subprocess.run([os.environ.get("TEST_SHELL", "sh"), str(script)], env=values, capture_output=True, text=True, timeout=60)
        self.assertFalse(env_file.exists(), "the env file must be deleted")
        return done

    def log(self, name):
        path = self.t / name
        return path.read_text() if path.exists() else ""

    def errors(self):
        return [line for line in self.log("ctx.log").splitlines() if line.startswith("logger error")]

    # ---- create

    def test_install_records_counters_and_facts(self):
        done = self.run_op(op="create", workflow="install", CA_ROTATIONS="2")
        self.assertEqual(done.returncode, 0, self.log("ctx.log"))
        self.assertIn("install-harbor", self.log("installer.log"))
        self.assertIn("CA_ROTATIONS=2", self.log("root/opt/harbor/.registry-tech-ops"))
        self.assertEqual(json.loads(self.log("harbor_facts.json"))["ca_rotations"], 2)

    def test_reinstall_in_update_refuses_old_installer(self):
        self.installer("")
        done = self.run_op(op="create", workflow="update")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.log("installer.log"), "")

    def test_reinstall_keeps_marker(self):
        self.marker(ca=3)
        self.run_op(op="create", workflow="update", CA_ROTATIONS="5")
        self.assertIn("CA_ROTATIONS=3", self.log("root/opt/harbor/.registry-tech-ops"))

    def test_offline_prep_create(self):
        done = self.run_op(op="create", workflow="install", RUN_ARG="offline-prep")
        self.assertEqual(done.returncode, 0)
        self.assertIn("offline-prep", self.log("installer.log"))
        self.assertEqual(self.log("harbor_facts.json"), "")

    # ---- update

    def test_no_change_runs_install_harbor(self):
        self.marker()
        done = self.run_op()
        self.assertEqual(done.returncode, 0, self.log("ctx.log"))
        self.assertEqual(self.log("installer.log").split()[0], "install-harbor")
        self.assertNotIn("update-certificates", self.log("installer.log"))

    def test_upgrade_dumps_first(self):
        self.marker()
        done = self.run_op(HARBOR_VERSION="2.15.0")
        self.assertEqual(done.returncode, 0, self.log("ctx.log"))
        dumps = list((self.t / "root/data/backup/registry-tech-ops").glob("harbor-db-v2.14.1-*.sql.gz"))
        self.assertEqual(len(dumps), 1)
        self.assertEqual(self.log("live"), "2.15.0")

    def test_upgrade_needs_disk(self):
        self.marker()
        done = self.run_op(HARBOR_VERSION="2.15.0", FREE_KB="1000")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.log("installer.log"), "")

    def test_downgrade_refused(self):
        self.marker()
        done = self.run_op(HARBOR_VERSION="2.13.2")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.log("installer.log"), "")

    def test_airgapped_upgrade_refused(self):
        self.marker()
        done = self.run_op(HARBOR_VERSION="2.15.0", OFFLINE_MODE="True")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.log("installer.log"), "")

    def test_ca_rotation_then_install(self):
        self.marker()
        done = self.run_op(CA_ROTATIONS="1", CERT_RENEWALS="1")
        self.assertEqual(done.returncode, 0, self.log("ctx.log"))
        runs = self.log("installer.log").splitlines()
        self.assertTrue(runs[0].startswith("update-certificates NEW_CERT_GEN=1 ROTATE_CA=true"), runs)
        self.assertTrue(runs[1].startswith("install-harbor NEW_CERT_GEN= ROTATE_CA="), runs)
        self.assertIn("CA_ROTATIONS=1\nCERT_RENEWALS=1", self.log("root/opt/harbor/.registry-tech-ops"))

    def test_renewal(self):
        self.marker(ca=1, renew=1)
        done = self.run_op(CA_ROTATIONS="1", CERT_RENEWALS="2")
        self.assertEqual(done.returncode, 0, self.log("ctx.log"))
        self.assertTrue(self.log("installer.log").startswith("update-certificates NEW_CERT_GEN=1 ROTATE_CA= "))
        self.assertIn("CERT_RENEWALS=2", self.log("root/opt/harbor/.registry-tech-ops"))

    def test_rotation_recorded_even_if_install_fails(self):
        self.marker()
        done = self.run_op(CA_ROTATIONS="1", FAIL_ON="install-harbor")
        self.assertEqual(done.returncode, 1)
        self.assertIn("CA_ROTATIONS=1", self.log("root/opt/harbor/.registry-tech-ops"))

    def test_rejected_credentials(self):
        self.marker()
        done = self.run_op(AUTH="401", HARBOR_VERSION="2.15.0")
        self.assertEqual(done.returncode, 1)
        self.assertIn("rejected", "\n".join(self.errors()))
        self.assertEqual(self.log("installer.log"), "")

    def test_harbor_down(self):
        done = self.run_op(HEALTH="502")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.log("installer.log"), "")

    def test_old_installer_records_only(self):
        self.installer("")
        done = self.run_op()
        self.assertEqual(done.returncode, 0, self.log("ctx.log"))
        self.assertEqual(self.log("installer.log"), "")
        self.assertNotEqual(self.log("harbor_facts.json"), "")

    def test_old_installer_refuses_work(self):
        self.installer("")
        for env in ({"HARBOR_VERSION": "2.15.0"}, {"CA_ROTATIONS": "1"}, {"MISSING": "velero"}):
            done = self.run_op(**env)
            self.assertEqual(done.returncode, 1, env)
        self.assertEqual(self.log("installer.log"), "")

    def test_offline_prep_update(self):
        done = self.run_op(RUN_ARG="offline-prep")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self.log("installer.log"), "")


if __name__ == "__main__":
    unittest.main()
