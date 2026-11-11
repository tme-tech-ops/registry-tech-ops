"""Tests for tech-ops/scripts/update_logic.py, without DAP.

Run from the repo root: python3 -m unittest discover -s tests
"""
import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tech-ops/scripts/update_logic.py"
NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)


def load():
    """Everything in update_logic.py except the call to main()."""
    tree = ast.parse(SCRIPT.read_text())
    body = [node for node in tree.body
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call))]
    namespace = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), SCRIPT, "exec"), namespace)
    return namespace


L = load()


def iso(days):
    return (NOW + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def inputs(**kwargs):
    values = {"harbor_version": "2.14.1", "projects": "library rancher", "run_arg": "install-harbor",
              "offline_mode": False, "script_url": L["DEFAULT_SCRIPT_URL"], "duration_days": 365,
              "ca_rotations": 0, "cert_renewals": 0, "cert_renew_before_days": 30,
              "harbor_password": "secret"}
    values.update(kwargs)
    return values


def facts(**kwargs):
    values = {"harbor_version": "2.14.1", "installer_version": "1.3.0",
              "installer_url": L["DEFAULT_SCRIPT_URL"], "cert_not_after": iso(300),
              "ca_not_after": iso(3000), "projects": ["library", "rancher"], "projects_read": True,
              "ca_rotations": 0, "cert_renewals": 0}
    values.update(kwargs)
    return values


class HelperTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(L["version"]("2.15.0"), (2, 15, 0))
        self.assertEqual(L["version"]("v1.1.1"), (1, 1, 1))
        self.assertIsNone(L["version"]("latest"))
        self.assertIsNone(L["version"](None))

    def test_installer_release(self):
        self.assertEqual(L["installer_release"](L["DEFAULT_SCRIPT_URL"]), (1, 3, 0))
        self.assertIsNone(L["installer_release"]("https://example.com/x/install_harbor.sh"))

    def test_desired_state_overlays_sent_inputs(self):
        record = {"old_inputs": inputs(), "new_inputs": {"harbor_version": "2.15.0"}}
        want = L["desired_state"](None, record)
        self.assertEqual(want["harbor_version"], "2.15.0")
        self.assertEqual(want["projects"], "library rancher")

    def test_desired_state_without_update(self):
        self.assertEqual(L["desired_state"]({"a": 1}, None), {"a": 1})

    def test_null_and_missing_inputs_get_defaults(self):
        self.assertEqual(L["number"]({}, "ca_rotations"), 0)
        self.assertEqual(L["setting"]({"run_arg": None}, "run_arg"), "install-harbor")
        self.assertEqual(L["projects"]({"projects": None}), [])


class InstallDriftTests(unittest.TestCase):
    def drift(self, want=None, old=None, rec="default"):
        want = want or inputs()
        return L["install_drift"](want, old or inputs(), facts() if rec == "default" else rec, NOW)

    def test_nothing_to_do(self):
        self.assertEqual(self.drift(), {})

    def test_no_recorded_state(self):
        self.assertIn("state", self.drift(rec=None))

    def test_offline_prep_never_drifts(self):
        old = inputs(run_arg="offline-prep")
        self.assertEqual(self.drift(want=old, old=old, rec=None), {})

    def test_upgrade(self):
        self.assertEqual(self.drift(want=inputs(harbor_version="2.15.0"))["harbor_version"], "2.14.1 -> 2.15.0")

    def test_downgrade_is_not_drift(self):
        self.assertEqual(self.drift(want=inputs(harbor_version="2.13.2")), {})

    def test_airgapped_upgrade_is_not_drift(self):
        self.assertEqual(self.drift(want=inputs(harbor_version="2.15.0", offline_mode=True, script_url=None)), {})

    def test_projects_added(self):
        self.assertEqual(self.drift(want=inputs(projects="library rancher velero"))["projects"], "to create: velero")

    def test_projects_removed_is_not_drift(self):
        self.assertEqual(self.drift(want=inputs(projects="library")), {})

    def test_projects_not_read(self):
        rec = facts(projects=[], projects_read=False)
        self.assertNotIn("projects", self.drift(rec=rec))

    def test_counters(self):
        found = self.drift(want=inputs(ca_rotations=1, cert_renewals=2))
        self.assertEqual(found["ca_rotations"], "CA Rotations 0 -> 1")
        self.assertEqual(found["cert_renewals"], "Certificate Renewals 0 -> 2")

    def test_certificate_in_window(self):
        self.assertIn("certificate", self.drift(rec=facts(cert_not_after=iso(10))))

    def test_certificate_outside_window(self):
        self.assertNotIn("certificate", self.drift(rec=facts(cert_not_after=iso(31))))

    def test_window_input(self):
        self.assertIn("certificate", self.drift(want=inputs(cert_renew_before_days=400)))

    def test_ca_in_window_makes_renewal_useless(self):
        rec = facts(cert_not_after=iso(10), ca_not_after=iso(10))
        self.assertNotIn("certificate", self.drift(rec=rec))
        self.assertIn("certificate", self.drift(want=inputs(ca_rotations=1), rec=rec))

    def test_old_installer_never_drifts(self):
        rec = facts(installer_version="", installer_url="https://raw.example/1bd7b54/install_harbor.sh")
        old = inputs(script_url=rec["installer_url"])
        self.assertEqual(L["install_drift"](inputs(script_url=rec["installer_url"], harbor_version="2.15.0"),
                                            old, rec, NOW), {})

    def test_old_installer_moving_drifts(self):
        rec = facts(installer_version="", installer_url="https://raw.example/1bd7b54/install_harbor.sh")
        found = L["install_drift"](inputs(harbor_version="2.15.0"), inputs(script_url=rec["installer_url"]), rec, NOW)
        self.assertIn("installer", found)
        self.assertIn("harbor_version", found)

    def test_new_installer(self):
        url = "https://github.com/Chubtoad5/harbor-registry-installer/releases/download/v1.2.0/install_harbor.sh"
        self.assertIn("installer", self.drift(want=inputs(script_url=url)))


class PrecheckDriftTests(unittest.TestCase):
    def test_script_url_changed(self):
        url = "https://example.com/new/install_harbor.sh"
        self.assertTrue(L["precheck_drift"](inputs(script_url=url), inputs(), facts()))

    def test_same_url(self):
        self.assertEqual(L["precheck_drift"](inputs(), inputs(), facts()), {})

    def test_compares_recorded_url_first(self):
        # A failed update saved the new URL; the VM still has the old installer.
        url = "https://example.com/new/install_harbor.sh"
        self.assertTrue(L["precheck_drift"](inputs(script_url=url), inputs(script_url=url), facts()))

    def test_airgapped(self):
        self.assertEqual(L["precheck_drift"](inputs(offline_mode=True, script_url="x"), inputs(), facts()), {})


class RefusalTests(unittest.TestCase):
    def refused(self, want=None, old=None, rec="default"):
        want = want or inputs()
        return L["refusals"](want, old or inputs(), facts() if rec == "default" else rec, NOW)

    def test_nothing_refused(self):
        self.assertEqual(self.refused(), [])

    def test_first_update_from_1_2(self):
        old = {k: v for k, v in inputs().items() if k not in ("ca_rotations", "cert_renewals")}
        self.assertEqual(self.refused(want=dict(old), old=old, rec=None), [])

    def test_downgrade(self):
        self.assertIn("older", self.refused(want=inputs(harbor_version="2.13.2"))[0])

    def test_downgrade_compares_running_version(self):
        # The stored input says 2.14.1, but 2.15.0 runs (a failed update saved inputs).
        self.assertTrue(self.refused(rec=facts(harbor_version="2.15.0")))

    def test_airgapped_upgrade(self):
        reasons = self.refused(want=inputs(harbor_version="2.15.0", offline_mode=True, script_url=None))
        self.assertIn("airgapped", reasons[0])

    def test_counter_lowered(self):
        self.assertIn("can only go up", self.refused(want=inputs(ca_rotations=0), rec=facts(ca_rotations=1))[0])

    def test_expired_ca(self):
        rec = facts(ca_not_after=iso(-1), cert_not_after=iso(-1))
        self.assertIn("expired", self.refused(rec=rec)[0])
        self.assertEqual(self.refused(want=inputs(ca_rotations=1), rec=rec), [])

    def test_duration_inside_window(self):
        self.assertIn("renewal window", self.refused(want=inputs(duration_days=30))[0])

    def test_old_installer_release_in_script_url(self):
        url = "https://github.com/Chubtoad5/harbor-registry-installer/releases/download/v1.0.0/install_harbor.sh"
        self.assertIn("v1.0.0", self.refused(want=inputs(script_url=url))[0])

    def test_old_installer_with_work(self):
        rec = facts(installer_version="", installer_url="https://raw.example/1bd7b54/install_harbor.sh")
        old = inputs(script_url=rec["installer_url"])
        reasons = self.refused(want=inputs(script_url=rec["installer_url"], harbor_version="2.15.0"), old=old, rec=rec)
        self.assertIn("older than v1.1.1", reasons[0])

    def test_old_installer_without_work(self):
        rec = facts(installer_version="", installer_url="https://raw.example/1bd7b54/install_harbor.sh")
        old = inputs(script_url=rec["installer_url"])
        self.assertEqual(self.refused(want=dict(old), old=old, rec=rec), [])

    def test_old_installer_moving_to_new_url(self):
        rec = facts(installer_version="", installer_url="https://raw.example/1bd7b54/install_harbor.sh")
        old = inputs(script_url=rec["installer_url"])
        self.assertEqual(self.refused(want=inputs(harbor_version="2.15.0"), old=old, rec=rec), [])

    V111 = "https://github.com/Chubtoad5/harbor-registry-installer/releases/download/v1.1.1/install_harbor.sh"

    def test_upgrade_needs_installer_that_dumps(self):
        # A 1.2.1.0 deployment keeps its Script URL (v1.1.1), which makes no dump (Q41).
        rec = facts(installer_version="1.1.1", installer_url=self.V111)
        old = inputs(script_url=self.V111)
        reasons = self.refused(want=inputs(script_url=self.V111, harbor_version="2.15.0"), old=old, rec=rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("v1.2.0 or later", reasons[0])
        self.assertIn(L["DEFAULT_SCRIPT_URL"], reasons[0])

    def test_upgrade_with_script_url_moved_in_same_update(self):
        rec = facts(installer_version="1.1.1", installer_url=self.V111)
        old = inputs(script_url=self.V111)
        self.assertEqual(self.refused(want=inputs(harbor_version="2.15.0"), old=old, rec=rec), [])

    def test_upgrade_moving_to_older_installer(self):
        self.assertIn("v1.2.0 or later", self.refused(want=inputs(script_url=self.V111, harbor_version="2.15.0"))[0])

    def test_first_update_upgrade_on_v1_1_1(self):
        old = {k: v for k, v in inputs(script_url=self.V111).items() if k not in ("ca_rotations", "cert_renewals")}
        want = dict(old, harbor_version="2.15.0")
        self.assertIn("v1.2.0 or later", self.refused(want=want, old=old, rec=None)[0])

    def test_v1_1_1_other_work_allowed(self):
        rec = facts(installer_version="1.1.1", installer_url=self.V111)
        old = inputs(script_url=self.V111)
        self.assertEqual(self.refused(want=inputs(script_url=self.V111, projects="library rancher velero",
                                                  cert_renewals=1), old=old, rec=rec), [])

    def test_upgrade_custom_url_left_to_vm(self):
        url = "https://example.com/mirror/install_harbor.sh"
        rec = facts(installer_url="https://example.com/old/install_harbor.sh", installer_version="1.1.1")
        self.assertEqual(self.refused(want=inputs(script_url=url, harbor_version="2.15.0"),
                                      old=inputs(script_url=rec["installer_url"]), rec=rec), [])

    def test_offline_prep(self):
        old = inputs(run_arg="offline-prep")
        self.assertIn("offline-prep", self.refused(want=inputs(run_arg="offline-prep", harbor_version="2.15.0"),
                                                   old=old, rec=None)[0])
        self.assertEqual(self.refused(want=dict(old), old=old, rec=None), [])


class WarningTests(unittest.TestCase):
    def test_projects_removed(self):
        found = L["warnings"](inputs(projects="library"), inputs(), facts(), NOW)
        self.assertIn("rancher", found[0])

    def test_ca_expiring(self):
        found = L["warnings"](inputs(), inputs(), facts(ca_not_after=iso(10)), NOW)
        self.assertIn("CA expires", found[0])

    def test_moving_from_unversioned_installer(self):
        rec = facts(installer_version="", installer_url="https://raw.example/1bd7b54/install_harbor.sh")
        found = L["warnings"](inputs(), inputs(script_url=rec["installer_url"]), rec, NOW)
        self.assertIn("redeploys Harbor once", found[0])


class PostupdateTests(unittest.TestCase):
    def test_as_requested(self):
        self.assertEqual(L["postupdate_problems"](inputs(), inputs(), facts()), [])

    def test_version_not_reached(self):
        self.assertTrue(L["postupdate_problems"](inputs(harbor_version="2.15.0"), inputs(), facts()))

    def test_counter_not_applied(self):
        self.assertTrue(L["postupdate_problems"](inputs(ca_rotations=1), inputs(), facts()))

    def test_old_installer_recorded_only(self):
        self.assertEqual(L["postupdate_problems"](inputs(harbor_version="2.15.0"), inputs(),
                                                  facts(installer_version="")), [])

    def test_no_state(self):
        self.assertTrue(L["postupdate_problems"](inputs(), inputs(), None))


class BlueprintTests(unittest.TestCase):
    inputs = yaml.safe_load((ROOT / "tech-ops/inputs.yaml").read_text())["inputs"]

    def test_default_script_url_matches(self):
        self.assertEqual(self.inputs["script_url"]["default"], L["DEFAULT_SCRIPT_URL"])

    def test_defaults_match(self):
        for name in ("duration_days", "ca_rotations", "cert_renewals", "cert_renew_before_days"):
            self.assertEqual(self.inputs[name]["default"], L["DEFAULTS"][name], name)

    def test_duration_range(self):
        # Installer v1.3.0 issues server certificates for 730 days at most (Q42).
        self.assertEqual(self.inputs["duration_days"]["constraints"][0]["in_range"], [31, 730])

    def test_updatable_inputs(self):
        updatable = {name for name, spec in self.inputs.items() if spec.get("allow_update")}
        self.assertEqual(updatable, {"harbor_version", "projects", "script_url", "duration_days", "debug",
                                     "hide_log_output", "ca_rotations", "cert_renewals",
                                     "cert_renew_before_days"})


if __name__ == "__main__":
    unittest.main()
