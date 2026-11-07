"""Reads Harbor's state on this VM and prints it as JSON, for install_app's
harbor_facts runtime property (see update_logic.py). Run by harbor_app.sh,
with its environment. Standard library only: the fabric plugin's ctx proxy
already needs Python on the VM.

  harbor_facts.py            the state, as JSON
  harbor_facts.py missing    the projects in PROJECTS that Harbor doesn't have

No password is printed. The credentials go to Harbor in a request header.
"""
import base64
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
INSTALLER = os.path.join(HOME, "install_harbor.sh")
MARKER = "/opt/harbor/.registry-tech-ops"
PORT = os.environ.get("HARBOR_PORT", "443")
NAME = os.environ.get("REGISTRY_COMMON_NAME", "localhost")
PEM = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)


def run(*cmd, data=None):
    try:
        done = subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def iso(openssl_date):
    """'Nov  6 12:00:00 2027 GMT' -> '2027-11-06T12:00:00Z'."""
    try:
        when = datetime.strptime(" ".join(openssl_date.split()), "%b %d %H:%M:%S %Y %Z")
    except ValueError:
        return ""
    return when.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cert_info(pem):
    """(expiry, sha256 fingerprint) of a PEM certificate, or empty strings."""
    if not pem:
        return "", ""
    out = run("openssl", "x509", "-noout", "-enddate", "-fingerprint", "-sha256", data=pem)
    end = re.search(r"notAfter=(.+)", out)
    fp = re.search(r"Fingerprint=([0-9A-F:]+)", out, re.I)
    return (iso(end.group(1)) if end else ""), (fp.group(1).upper() if fp else "")


def served_cert():
    """The certificate Harbor serves, as clients see it."""
    out = run("openssl", "s_client", "-connect", f"127.0.0.1:{PORT}", "-servername", NAME, data="")
    found = PEM.search(out)
    return found.group(0) + "\n" if found else ""


def harbor_version():
    image = run("sudo", "-n", "docker", "inspect", "-f", "{{.Config.Image}}", "harbor-core").strip()
    return image.rsplit(":v", 1)[1] if ":v" in image else ""


def installer_version():
    try:
        with open(INSTALLER, encoding="utf-8", errors="replace") as script:
            for line in script:
                found = re.match(r'SCRIPT_VERSION="([0-9.]+)"', line)
                if found:
                    return found.group(1)
    except OSError:
        pass
    return ""


def installer_sha256():
    out = run("sha256sum", INSTALLER)
    return out.split()[0] if out else ""


def marker():
    values = {}
    for line in run("sudo", "-n", "cat", MARKER).splitlines():
        key, _, value = line.partition("=")
        if value.strip().isdigit():
            values[key.strip()] = int(value.strip())
    return values


def ca_pem():
    return run("sudo", "-n", "cat", "/opt/harbor/certs/ca.crt")


def harbor_projects(ca):
    """Names of every project the deployment's user can see, or None if Harbor
    didn't answer. The connection is verified against Harbor's own CA. The host
    name isn't checked, because the certificate names the VM, not 127.0.0.1."""
    if not ca:
        return None
    user = os.environ.get("HARBOR_USERNAME", "admin")
    password = os.environ.get("HARBOR_PASSWORD", "")
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    try:
        context = ssl.create_default_context(cadata=ca)
    except (ssl.SSLError, ValueError):
        return None
    context.check_hostname = False
    names, page = [], 1
    while page < 100:
        request = urllib.request.Request(
            f"https://127.0.0.1:{PORT}/api/v2.0/projects?page={page}&page_size=100",
            headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, context=context, timeout=20) as reply:
                batch = json.load(reply)
        except (urllib.error.URLError, OSError, ValueError):
            return None
        names += [item.get("name") for item in batch or [] if item.get("name")]
        if len(batch or []) < 100:
            return sorted(names)
        page += 1
    return sorted(names)


def main():
    ca = ca_pem()
    if sys.argv[1:] == ["missing"]:
        have = harbor_projects(ca)
        if have is None:
            print("Harbor didn't list its projects.", file=sys.stderr)
            return 1
        print(" ".join(name for name in os.environ.get("PROJECTS", "").split() if name not in have))
        return 0
    cert_not_after, cert_sha256 = cert_info(served_cert())
    ca_not_after, ca_sha256 = cert_info(ca)
    counters = marker()
    have = harbor_projects(ca)
    facts = {
        "harbor_version": harbor_version(),
        "installer_version": installer_version(),
        "installer_url": os.environ.get("SCRIPT_URL", ""),
        "installer_sha256": installer_sha256(),
        "cert_not_after": cert_not_after,
        "cert_sha256": cert_sha256,
        "ca_not_after": ca_not_after,
        "ca_sha256": ca_sha256,
        "projects": have if have is not None else [],
        "projects_read": have is not None,
        "ca_rotations": counters.get("CA_ROTATIONS", 0),
        "cert_renewals": counters.get("CERT_RENEWALS", 0),
        "read_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    print(json.dumps(facts, sort_keys=True))
    return 0


sys.exit(main())
