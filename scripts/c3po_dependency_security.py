#!/usr/bin/env python3
"""Prepare bounded fixes from GitHub advisories, never from package-provided commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import tempfile

FRONTEND = "c3po/frontend/"
RECEIPT = "c3po/security/dependency-remediation.json"
ALLOWED = {FRONTEND + "package.json", FRONTEND + "pnpm-workspace.yaml",
           FRONTEND + "pnpm-lock.yaml", "c3po/backend/requirements.txt", RECEIPT}
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PACKAGE = re.compile(r"^(?:@[a-z0-9._-]+/)?[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("Only stable three-component versions can be applied automatically")
    return tuple(map(int, value.split(".")))


def compatible(current, fixed):
    old, new = version(current), version(fixed)
    return old < new and old[0] == new[0] and (old[0] != 0 or old[1] == new[1])


def normalize_alerts(alerts):
    result = []
    for raw in alerts:
        dep = raw["dependency"]
        vuln = raw["security_vulnerability"]
        item = {
            "number": raw["number"], "advisory": raw["security_advisory"]["ghsa_id"],
            "severity": raw["security_advisory"]["severity"],
            "ecosystem": dep["package"]["ecosystem"], "package": dep["package"]["name"],
            "manifest": dep["manifest_path"],
            "fixed": (vuln.get("first_patched_version") or {}).get("identifier"),
        }
        if not PACKAGE.fullmatch(item["package"]):
            raise ValueError("Invalid advisory package name")
        result.append(item)
    return sorted(result, key=lambda item: item["number"])


def npm_alerts(audit):
    if not isinstance(audit.get("advisories"), dict) or "vulnerabilities" not in audit.get("metadata", {}):
        raise ValueError("npm advisory service did not return a complete audit")
    result = []
    for item in audit["advisories"].values():
        name, advisory = item["module_name"], item["github_advisory_id"]
        if not PACKAGE.fullmatch(name) or not re.fullmatch(r"GHSA-[a-z0-9-]+", advisory):
            raise ValueError("Malformed npm advisory")
        # More complex patched ranges remain visible, without inventing a safe version.
        match = re.fullmatch(r">=([0-9]+\.[0-9]+\.[0-9]+)", item.get("patched_versions", ""))
        result.append({"number": "npm:" + advisory, "advisory": advisory,
                       "severity": item["severity"], "ecosystem": "npm", "package": name,
                       "manifest": FRONTEND + "pnpm-lock.yaml", "fixed": match[1] if match else None})
    return result


def merge_alerts(github, registry):
    merged = {(a["package"], a["advisory"], a["manifest"]): a for a in registry}
    merged.update({(a["package"], a["advisory"], a["manifest"]): a for a in github})
    return [merged[key] for key in sorted(merged)]


def prepare(files, alerts):
    """Return manifest changes and explicit unresolved reasons. Lockfile resolved by pnpm."""
    result = dict(files)
    applied, blocked = [], []
    for alert in alerts:
        name, fixed = alert["package"], alert["fixed"]
        try:
            if not fixed:
                raise ValueError("upstream_fix_unavailable")
            version(fixed)
            if any(a["package"] == name and a["ecosystem"] == alert["ecosystem"]
                   and a["manifest"] == alert["manifest"] and version(a["fixed"]) >= version(fixed) for a in applied):
                applied.append(alert)
                continue
            if alert["ecosystem"] == "npm" and alert["manifest"] == FRONTEND + "pnpm-lock.yaml":
                workspace = FRONTEND + "pnpm-workspace.yaml"
                pattern = re.compile(r"^(  " + re.escape(name) + r": )([0-9]+\.[0-9]+\.[0-9]+)$", re.M)
                matches = list(pattern.finditer(result[workspace]))
                package_path = FRONTEND + "package.json"
                package = json.loads(result[package_path])
                if len(matches) == 1:
                    current = matches[0][2]
                    if not compatible(current, fixed):
                        raise ValueError("major_change_or_already_at_fixed_version")
                    result[workspace] = pattern.sub(lambda m: m[1] + fixed, result[workspace])
                elif len(matches) == 0:
                    sections = [key for key in ("dependencies", "devDependencies")
                                if name in package.get(key, {})]
                    if len(sections) != 1:
                        raise ValueError("transitive_dependency_requires_parent_update")
                    section = sections[0]
                    current = package[section][name].lstrip("^~")
                    if not compatible(current, fixed):
                        raise ValueError("major_change_or_already_at_fixed_version")
                    package[section][name] = fixed
                    result[package_path] = json.dumps(package, indent=2, ensure_ascii=False) + "\n"
                else:
                    raise ValueError("ambiguous_override")
            elif alert["ecosystem"] == "pip" and alert["manifest"] == "c3po/backend/requirements.txt":
                # Preserve extras and the existing upper bound. Complex PEP 508 requirements
                # are explicitly deferred instead of guessed or widening constraints.
                path = "c3po/backend/requirements.txt"
                pattern = re.compile(r"^(" + re.escape(name) + r"(?:\[[a-z0-9,-]+\])?>=)([0-9.]+)(,<([0-9.]+))$", re.M | re.I)
                matches = list(pattern.finditer(result[path]))
                if len(matches) != 1:
                    raise ValueError("requirement_needs_manual_compatibility_review")
                m = matches[0]
                current = ".".join((m[2].split(".") + ["0", "0"])[:3])
                upper = tuple(int(p) for p in (m[4].split(".") + ["0", "0"])[:3])
                if not compatible(current, fixed) or version(fixed) >= upper:
                    raise ValueError("fix_outside_current_compatibility_range")
                result[path] = pattern.sub(lambda m: m[1] + fixed + m[3], result[path])
            else:
                raise ValueError("unsupported_manifest")
            applied.append(alert)
        except ValueError as exc:
            blocked.append({**alert, "reason": str(exc)})
    return result, applied, blocked


def validate_candidate(base, head, alerts, base_sha):
    """Manifest changes must be reproducible from current advisories, not a PR label."""
    if not set(head).issubset(ALLOWED) or RECEIPT not in head:
        raise ValueError("Unexpected candidate files")
    receipt = json.loads(head[RECEIPT])
    expected, applied, blocked = prepare(base, alerts)
    if not applied or receipt != {"schema": "C3PO_DEPENDENCY_REMEDIATION-v1", "base_sha": base_sha,
                                  "applied": applied, "blocked": blocked}:
        raise ValueError("Candidate is stale or does not match current advisories")
    for path in ALLOWED - {RECEIPT, FRONTEND + "pnpm-lock.yaml"}:
        if head.get(path, base[path]) != expected[path]:
            raise ValueError("Candidate contains unrelated changes: " + path)


def verify_audit(audit, receipt):
    counts = audit["metadata"]["vulnerabilities"]
    if any(not isinstance(counts.get(key), int) for key in ("high", "critical")):
        raise ValueError("Audit response is incomplete")
    if counts["high"] or counts["critical"]:
        raise ValueError("Dependency audit still contains high/critical advisories")
    serialized = json.dumps(audit)
    if any(item["advisory"] in serialized for item in receipt["applied"]):
        raise ValueError("A targeted advisory is still present after the fix")


def verify_lock(root):
    receipt = json.loads((root / RECEIPT).read_text())
    base_sha = receipt["base_sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise ValueError("Invalid candidate base")
    base_lock = subprocess.check_output(["git", "show", base_sha + ":" + FRONTEND + "pnpm-lock.yaml"], cwd=root)
    with tempfile.TemporaryDirectory(prefix="c3po-security-lock-") as directory:
        target = Path(directory)
        for name in ("package.json", "pnpm-workspace.yaml"):
            (target / name).write_bytes((root / FRONTEND / name).read_bytes())
        (target / "pnpm-lock.yaml").write_bytes(base_lock)
        subprocess.run(["pnpm", "install", "--lockfile-only", "--ignore-scripts"], cwd=target, check=True, timeout=300)
        if (target / "pnpm-lock.yaml").read_bytes() != (root / FRONTEND / "pnpm-lock.yaml").read_bytes():
            raise ValueError("Candidate lockfile is not reproducible from approved manifests")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--audit-result", type=Path)
    parser.add_argument("--npm-audit", type=Path)
    parser.add_argument("--npm-report-output", type=Path)
    parser.add_argument("--verify-lock", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--base-sha")
    args = parser.parse_args()
    if args.verify_lock:
        verify_lock(args.root.resolve())
        return
    if args.audit_result:
        verify_audit(json.loads(args.audit_result.read_text()), json.loads((args.root / RECEIPT).read_text()))
        return
    if not args.report or not args.base_sha:
        parser.error("--report and --base-sha required to prepare fixes")
    if not re.fullmatch(r"[0-9a-f]{40}", args.base_sha):
        raise ValueError("Invalid base revision")
    report = json.loads(args.report.read_text())
    if args.npm_audit:
        registry = npm_alerts(json.loads(args.npm_audit.read_text()))
        npm_report = {"schema": "C3PO_NPM_ADVISORIES-v1", "source_revision": args.base_sha,
                      "generated_at": datetime.now(timezone.utc).isoformat(), "alerts": registry}
        npm_report["report_sha256"] = digest(npm_report)
        if not args.npm_report_output:
            parser.error("--npm-report-output required with --npm-audit")
        args.npm_report_output.write_text(json.dumps(npm_report, indent=2, sort_keys=True) + "\n")
        report["alerts"] = merge_alerts(report["alerts"], registry)
    files = {p: (args.root / p).read_text() for p in ALLOWED - {RECEIPT}}
    result, applied, blocked = prepare(files, report["alerts"])
    receipt = {"schema": "C3PO_DEPENDENCY_REMEDIATION-v1", "base_sha": args.base_sha,
               "applied": applied, "blocked": blocked}
    if applied:
        for path, content in result.items():
            if content != files[path]:
                (args.root / path).write_text(content)
        (args.root / RECEIPT).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"applied": len(applied), "blocked": len(blocked), "key": digest(receipt)}))


if __name__ == "__main__":
    main()
