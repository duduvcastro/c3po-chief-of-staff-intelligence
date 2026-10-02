#!/usr/bin/env python3
"""Check the capacity mount in a `docker compose config --format json` render.

    check_compose_render.py placeholder          <render.json | ->
    check_compose_render.py bind=<absolute path> <render.json | ->

Exit 0 when r2d2-worker, and only r2d2-worker, carries the expected read-only mount at
/c3po-capacity; exit 1 with the reasons otherwise. Only the capacity mount entry is printed: on a
host the render also carries every value of the .env file, so pipe it in and never display it.
This checks what Compose resolved. It says nothing about the capacity tree, the settings or the
planner.
"""
import json
import sys

SERVICE = "r2d2-worker"
TARGET = "/c3po-capacity"
PLACEHOLDER = "c3po_capacity_unprovisioned"
PROJECT = "c3po"
WORKER_TARGETS = ["/run/c3po-maintenance", "/app/day-d-data", TARGET]


def check(render, expect):
    """Return the list of reasons the render does not match `expect` (empty when it matches)."""
    errors = []
    services = render.get("services") if isinstance(render, dict) else None
    if not isinstance(services, dict):
        return ["render has no services"]
    found = []
    for name, service in services.items():
        for volume in (service or {}).get("volumes") or []:
            if not isinstance(volume, dict):
                errors.append(f"{name}: volume is not in the resolved long form")
            elif volume.get("target") == TARGET:
                found.append((name, volume))
    if [name for name, _ in found] != [SERVICE]:
        return errors + [f"{TARGET} must be mounted once, on {SERVICE} only: {[name for name, _ in found]}"]
    mount = found[0][1]
    if mount.get("read_only") is not True:
        errors.append("the capacity mount is not read-only")
    targets = [volume.get("target") for volume in services[SERVICE]["volumes"] if isinstance(volume, dict)]
    if sorted(map(str, targets)) != sorted(WORKER_TARGETS):
        errors.append(f"{SERVICE} mounts changed: {targets}")
    if render.get("name") != PROJECT:
        errors.append(f"project name is not {PROJECT}")
    declared = (render.get("volumes") or {}).get(PLACEHOLDER)
    if not isinstance(declared, dict) or declared.get("name") != f"{PROJECT}_{PLACEHOLDER}":
        errors.append(f"placeholder volume is not declared as {PROJECT}_{PLACEHOLDER}")
    if expect == "placeholder":
        if (mount.get("type"), mount.get("source")) != ("volume", PLACEHOLDER):
            errors.append(f"expected the placeholder volume, got {mount.get('type')} {mount.get('source')!r}")
    elif expect.startswith("bind=/"):
        if (mount.get("type"), mount.get("source")) != ("bind", expect[len("bind="):]):
            errors.append(f"expected a bind of {expect[len('bind='):]!r}, got {mount.get('type')} {mount.get('source')!r}")
    else:
        errors.append("expectation must be `placeholder` or `bind=<absolute path>`")
    return errors


def main(argv):
    if len(argv) != 3:
        print("usage: check_compose_render.py placeholder|bind=<absolute path> <render.json|->", file=sys.stderr)
        return 2
    expect, source = argv[1], argv[2]
    try:
        if source == "-":
            render = json.load(sys.stdin)
        else:
            with open(source, encoding="utf-8") as handle:
                render = json.load(handle)
    except (OSError, ValueError) as error:
        print(f"CAPACITY_MOUNT_RENDER_UNREADABLE {type(error).__name__}", file=sys.stderr)
        return 1
    errors = check(render, expect)
    if errors:
        for error in errors:
            print(f"CAPACITY_MOUNT_RENDER_REFUSED {error}", file=sys.stderr)
        return 1
    mount = [v for v in render["services"][SERVICE]["volumes"] if v.get("target") == TARGET][0]
    print(f"CAPACITY_MOUNT_RENDER_OK {expect} {json.dumps(mount, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
