"""Update logic for registry-tech-ops, run on the orchestrator (no SSH).

One script for several nodes and operations (ctx.node.id, ctx.operation.name):

- update_checks: create, check_drift, update. Reasons to refuse an update are
  reported as its drift. Its update raises with them, and so does its create,
  which is what runs when "Run automatic reinstall" reinstalls it.
- env_precheck: check_drift. Drift when Script URL changes, so its update
  downloads that installer.
- install_app: check_drift and postupdate. Drift when Harbor needs work: a new
  version, missing projects, a certificate in its renewal window, a raised
  counter, a new installer, or no recorded state yet.
- env_postcheck: check_drift. Drift whenever install_app drifts, so its update
  refreshes the capabilities after install_app's.

The desired state is the update record's old inputs, overlaid with the inputs
the update sent. That is right in preview too, where operation inputs still
hold the old values. Outside an update it's the deployment's inputs. The
recorded state is install_app's harbor_facts runtime property, which
harbor_app.sh writes on the VM after each run of the installer. A refused
change is never drift on install_app, and harbor_app.sh repeats the checks
that matter on the VM.

Nothing here logs the inputs: they hold the Harbor password.
"""
from datetime import datetime, timezone
import re

DEFAULT_SCRIPT_URL = ("https://github.com/Chubtoad5/harbor-registry-installer/releases/download/"
                      "v1.3.0/install_harbor.sh")
MIN_INSTALLER = (1, 1, 1)
# An upgrade needs an installer that dumps Harbor's database before it changes anything.
MIN_UPGRADE_INSTALLER = (1, 2, 0)
DEFAULTS = {"run_arg": "install-harbor", "offline_mode": False, "projects": "",
            "duration_days": 365, "ca_rotations": 0, "cert_renewals": 0,
            "cert_renew_before_days": 30}
APP_SETTINGS = ("harbor_version", "projects", "script_url", "ca_rotations", "cert_renewals")
COUNTERS = (("ca_rotations", "CA Rotations"), ("cert_renewals", "Certificate Renewals"))


def version(value):
    """'2.15.0' or 'v1.1.1' -> (2, 15, 0); None if it isn't one."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def text(ver):
    return ".".join(str(part) for part in ver)


def installer_release(url):
    """The version of a GitHub release asset URL of install_harbor.sh, or None."""
    match = re.search(r"/releases/download/(v?\d+\.\d+\.\d+)/install_harbor\.sh$", str(url or ""))
    return version(match.group(1)) if match else None


def setting(values, name):
    """An input's value, with the blueprint default for a null or missing one
    (a deployment from 1.2.x has no counters; inputs hidden by only_with or
    exclusive_with arrive as null)."""
    value = (values or {}).get(name)
    return DEFAULTS.get(name) if value is None else value


def number(values, name):
    try:
        return int(setting(values, name))
    except (TypeError, ValueError):
        return int(DEFAULTS.get(name) or 0)


def projects(values):
    return str(setting(values, "projects") or "").split()


def desired_state(deployment_inputs, record):
    """Old inputs overlaid with the inputs the update sent (new_inputs holds
    only those); the deployment's inputs when there is no update."""
    if not record:
        return dict(deployment_inputs or {})
    values = dict(record.get("old_inputs") or {})
    values.update(record.get("new_inputs") or {})
    return values


def days_left(iso, now):
    """Days from now to an ISO time such as 2027-11-06T12:00:00Z; None if unknown."""
    if not iso:
        return None
    try:
        end = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (end - now).total_seconds() / 86400


def applied(facts, old, name):
    """A counter's value last applied on the VM. Before anything was recorded,
    the stored input (0 for a deployment from 1.2.x)."""
    if facts and name in facts:
        try:
            return int(facts[name])
        except (TypeError, ValueError):
            pass
    return number(old, name)


def offline_prep(old):
    return setting(old, "run_arg") == "offline-prep"


def installer_too_old(facts):
    """Recorded installer older than v1.1.1. harbor_facts records an empty
    version for an installer with no SCRIPT_VERSION (before v1.1.0)."""
    return bool(facts) and (version(facts.get("installer_version")) or (0, 0, 0)) < MIN_INSTALLER


def upgrade_installer(want, facts):
    """The installer version this update would run: the Script URL's release
    when the update moves it (env_precheck downloads it before install_app
    runs), otherwise the recorded one. None when it can't be told, such as a
    URL that isn't a release asset; harbor_app.sh then checks on the VM."""
    url = setting(want, "script_url")
    if not facts:
        return installer_release(url)
    if url and url != facts.get("installer_url"):
        return installer_release(url)
    return version(facts.get("installer_version"))


def install_drift(want, old, facts, now):
    """{item: why} for what install_app's update has to do. Empty: nothing.
    An update doesn't run an installer older than v1.1.1 (update_checks
    refuses the work), so then only a new Script URL is drift."""
    found = requested(want, old, facts, now)
    if installer_too_old(facts) and "installer" not in found:
        return {}
    return found


def requested(want, old, facts, now):
    """{item: why} for everything this update asks of Harbor."""
    if offline_prep(old):
        return {}
    if not facts:
        return {"state": "not recorded yet (a deployment from an earlier version): "
                         "the update records it"}
    found = {}
    airgapped = bool(setting(want, "offline_mode"))
    running, asked = version(facts.get("harbor_version")), version(setting(want, "harbor_version"))
    if running and asked and asked > running and not airgapped:
        found["harbor_version"] = f"{text(running)} -> {text(asked)}"
    have = set(facts.get("projects") or [])
    missing = [name for name in projects(want) if name not in have]
    if missing and facts.get("projects_read", True):
        found["projects"] = "to create: " + " ".join(missing)
    rotating = False
    for name, label in COUNTERS:
        done, wanted = applied(facts, old, name), number(want, name)
        if wanted > done:
            found[name] = f"{label} {done} -> {wanted}"
            rotating = rotating or name == "ca_rotations"
    window = number(want, "cert_renew_before_days")
    cert_left = days_left(facts.get("cert_not_after"), now)
    ca_left = days_left(facts.get("ca_not_after"), now)
    # A new certificate can't outlive its CA, so renewing helps only while the
    # CA has more than the window left, or is being rotated.
    if (cert_left is not None and cert_left < window
            and (rotating or ca_left is None or ca_left >= window)):
        found["certificate"] = (f"expires {facts['cert_not_after'][:10]} "
                                f"({max(0, int(cert_left))} days left), renewed in its last {window}")
    url = setting(want, "script_url")
    if url and not airgapped and url != facts.get("installer_url"):
        found["installer"] = "Script URL changed: the update downloads that installer"
    return found


def precheck_drift(want, old, facts):
    """env_precheck re-downloads the installer when Script URL changes."""
    if offline_prep(old) or setting(want, "offline_mode"):
        return {}
    url = setting(want, "script_url")
    before = (facts or {}).get("installer_url") or setting(old, "script_url")
    return {"script_url": "changed: the update downloads that installer"} if url and url != before else {}


def refusals(want, old, facts, now):
    """Reasons this update can't go ahead. Each one leaves Harbor unchanged."""
    if offline_prep(old):
        changed = [name for name in APP_SETTINGS if setting(want, name) != setting(old, name)]
        if changed:
            return ["This deployment only built an offline package (Install Task offline-prep), so its "
                    f"Harbor settings can't change ({', '.join(changed)}). Create a new offline-prep "
                    "deployment for a new package."]
        return []
    reasons = []
    running = version((facts or {}).get("harbor_version")) or version(setting(old, "harbor_version"))
    asked = version(setting(want, "harbor_version"))
    if running and asked and asked != running:
        if asked < running:
            reasons.append(f"Harbor {text(running)} is running and Harbor Version {text(asked)} is older. "
                           "An older Harbor can't start on a newer database. Update again with "
                           f"{text(running)} or later.")
        elif setting(want, "offline_mode"):
            reasons.append("Upgrading Harbor in airgapped mode isn't supported yet, because it needs a new "
                           f"offline package. Update again with Harbor Version {text(running)}.")
        else:
            inst = upgrade_installer(want, facts)
            if inst and inst < MIN_UPGRADE_INSTALLER:
                reasons.append(f"Upgrading Harbor needs installer v{text(MIN_UPGRADE_INSTALLER)} or later, "
                               "which dumps Harbor's database before it changes anything, and this update "
                               f"would run v{text(inst)}. Set Script URL to {DEFAULT_SCRIPT_URL} (this "
                               "version's default), in this update or before it.")
    rotating = False
    for name, label in COUNTERS:
        done, wanted = applied(facts, old, name), number(want, name)
        if wanted < done:
            reasons.append(f"{label} can only go up, and it is {done} on this deployment. "
                           f"Update again with {done} or more.")
        rotating = rotating or (name == "ca_rotations" and wanted > done)
    ca_left = days_left((facts or {}).get("ca_not_after"), now)
    if ca_left is not None and ca_left <= 0 and not rotating:
        reasons.append(f"Harbor's CA expired on {facts['ca_not_after'][:10]}, so no certificate can be "
                       "renewed. Raise CA Rotations by one in this update to replace it. Every client "
                       "must then trust the new CA (capability harbor_ca_cert).")
    duration, window = number(want, "duration_days"), number(want, "cert_renew_before_days")
    if duration <= window:
        reasons.append(f"Duration ({duration} days) must be longer than the renewal window ({window} "
                       "days), or every update would renew the certificate.")
    url = setting(want, "script_url")
    release = installer_release(url)
    if url and not setting(want, "offline_mode") and release and release < MIN_INSTALLER:
        reasons.append(f"Script URL is installer v{text(release)}, and this version needs v1.1.1 or "
                       f"later, such as its default {DEFAULT_SCRIPT_URL}")
    elif installer_too_old(facts):
        moving = url and url != facts.get("installer_url")
        work = {k: v for k, v in requested(want, old, facts, now).items() if k != "installer"}
        if work and not moving:
            reasons.append("This deployment's Harbor installer is older than v1.1.1, and an update doesn't "
                           f"run it ({', '.join(sorted(work))}). Set Script URL to {DEFAULT_SCRIPT_URL} "
                           "(this version's default), in this update or before it.")
    return reasons


def warnings(want, old, facts, now):
    """Worth saying at the start of an update; never fails it."""
    if offline_prep(old):
        return []
    found = []
    removed = [name for name in projects(old) if name not in projects(want)]
    if removed:
        found.append("Harbor keeps the projects removed from Registry Projects (" + " ".join(removed)
                     + "): an update never deletes a project.")
    ca_left = days_left((facts or {}).get("ca_not_after"), now)
    window = number(want, "cert_renew_before_days")
    rotating = number(want, "ca_rotations") > applied(facts, old, "ca_rotations")
    if ca_left is not None and 0 < ca_left < window and not rotating:
        found.append(f"Harbor's CA expires on {facts['ca_not_after'][:10]} ({int(ca_left)} days left). A "
                     "server certificate can't outlive it, so renewing doesn't help: raise CA Rotations "
                     "by one to replace it, and have every client trust the new CA.")
    url = setting(want, "script_url")
    if facts and url and url != facts.get("installer_url") and not version(facts.get("installer_version")):
        found.append("This deployment's installer is older than v1.1.0, so moving to the new Script URL "
                     "redeploys Harbor once (a short outage). Its data and CA are kept.")
    return found


def postupdate_problems(want, old, facts):
    """What install_app's update should have done and didn't."""
    if offline_prep(old):
        return []
    if not facts:
        return ["The update didn't record Harbor's state (harbor_facts)."]
    if installer_too_old(facts):
        return []  # the update only recorded the state
    problems = []
    asked, running = version(setting(want, "harbor_version")), version(facts.get("harbor_version"))
    if asked and running != asked and not setting(want, "offline_mode"):
        problems.append(f"Harbor {text(running) if running else 'unknown'} is running, not {text(asked)}.")
    have = set(facts.get("projects") or [])
    missing = [name for name in projects(want) if name not in have]
    if missing and facts.get("projects_read", True):
        problems.append("Projects missing in Harbor: " + " ".join(missing) + ".")
    for name, label in COUNTERS:
        if applied(facts, old, name) != number(want, name):
            problems.append(f"{label} is {number(want, name)}, but {applied(facts, old, name)} was applied.")
    return problems


def drift(node_id, items):
    return {"resource_id": node_id, "diff_count": len(items), "diff": items} if items else None


def main():
    from dell import ctx
    from dell.exceptions import NonRecoverableError
    from dell.manager import get_rest_client

    node, op = ctx.node.id, ctx.operation.name.split(".")[-1]
    workflow = ctx.workflow_id
    if node == "update_checks" and op == "create" and workflow != "update":
        ctx.logger.info("update checks: nothing to check outside an update")
        return
    now = datetime.now(timezone.utc)
    try:
        client = get_rest_client()
        record = None
        if workflow == "update":
            update_id = (client.executions.get(ctx.execution_id).parameters or {}).get("update_id")
            if update_id:
                record = client.deployment_updates.get(update_id, _include=["old_inputs", "new_inputs"])
        deployment_inputs = None
        if not record:
            deployment_inputs = client.deployments.get(ctx.deployment.id, _include=["inputs"]).inputs
        want = desired_state(deployment_inputs, record)
        old = dict(record.get("old_inputs") or {}) if record else dict(want)
        if node == "install_app":
            facts = ctx.instance.runtime_properties.get("harbor_facts")
        else:
            found = client.node_instances.list(deployment_id=ctx.deployment.id, node_id="install_app")
            facts = (found[0].runtime_properties or {}).get("harbor_facts") if found else None
        facts = dict(facts) if facts else None
    except Exception as err:  # API not reachable: don't block, harbor_app.sh checks again on the VM
        ctx.logger.warning(f"{node}: could not read this update ({err}); no change from here")
        if op == "check_drift":
            ctx.returns(None)
        return

    if node == "update_checks":
        reasons = refusals(want, old, facts, now)
        if op == "check_drift":
            for warning in warnings(want, old, facts, now):
                ctx.logger.warning(f"update checks: {warning}")
            for reason in reasons:
                ctx.logger.warning(f"update checks: {reason}")
            ctx.returns(drift(node, {f"refused_{n}": r for n, r in enumerate(reasons, 1)}))
        elif reasons:
            raise NonRecoverableError(" ".join(reasons))
        else:
            ctx.logger.info(f"update checks: {op}: passed")
        return

    if op == "check_drift":
        if node == "env_precheck":
            items = precheck_drift(want, old, facts)
        elif node == "install_app":
            items = install_drift(want, old, facts, now)
        elif node == "env_postcheck":
            items = ({"capabilities": "refreshed after install_app's update"}
                     if install_drift(want, old, facts, now) else {})
        else:
            items = {}
        for name, why in items.items():
            ctx.logger.info(f"{node}: {name}: {why}")
        ctx.returns(drift(node, items))
        return

    if node == "install_app" and op == "postupdate":
        problems = postupdate_problems(want, old, facts)
        if problems:
            raise NonRecoverableError("Harbor isn't as requested after the update: " + " ".join(problems))
        ctx.logger.info("install_app: Harbor is as requested")
        return

    ctx.logger.info(f"{node}: {op}: nothing to do")


main()
