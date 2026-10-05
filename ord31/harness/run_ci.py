"""Draft ORD:31 CI harness. Docker is invoked only with --execute-ci on a CI runner.

The exact mounted launcher, reviewed five-bind unit, image source readback and
directed-process results are recorded separately. Never uses the production image.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

SOURCE_REVISION = "dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858"
SOURCE_ARCHIVE_SHA256 = "61bf5dd5e8b4c5b1e421b16949b4294f5dbfefe44a164d7097cdce7167e57660"
PRODUCTION_IMAGE_ID = "sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb621"
TEMPLATE_SHA256 = "3dc976807a0ff443307fa12e357d478980441b26d19761b0d7964b5580327770"
STATUS_PREFIX = "INFO:__main__:V2 status "
HERE = Path(os.path.abspath(__file__)).parent

class InputIntegrityError(RuntimeError):
    """A delivered or mounted input could not retain its explicit byte seal."""

def regular_bytes(path):
    """Read a regular file without following any symlink in its path."""
    path = Path(path)
    if ".." in path.parts or not path.name:
        raise InputIntegrityError("unsafe input path")
    path = Path(os.path.abspath(path))
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise InputIntegrityError("nonregular input")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        data = b"".join(chunks)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                 info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after) or len(data) != after.st_size:
            raise InputIntegrityError("input changed while being read")
        return data
    except OSError:
        raise InputIntegrityError("missing, symlinked or unreadable input") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)

def parse_delivery_manifest(data):
    """Accept every listed file, with safe unique names and no self-reference."""
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeError:
        raise InputIntegrityError("manifest is not ASCII") from None
    entries = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
        if match is None:
            raise InputIntegrityError("unsafe manifest entry")
        pin, name = match.groups()
        if name in entries or name == "SHA256SUMS":
            raise InputIntegrityError("duplicate or self-referential manifest entry")
        entries[name] = pin
    required = {"run_ci.py", "driver.py", "observe.py", "reader.service.template"}
    if not entries or not required <= entries.keys():
        raise InputIntegrityError("manifest omits required delivered inputs")
    return entries

def snapshot_inputs(args, launcher_dir, *, harness_dir=None, reference=None):
    """Capture all manifest inputs and mounted copies; collect every failure."""
    harness_dir = HERE if harness_dir is None else Path(harness_dir)
    files, errors, entries = {}, [], {}
    def capture(path, label, expected):
        try:
            data = regular_bytes(path)
            files[label] = {"bytes": len(data), "sha256": digest(data)}
            if expected is None or files[label]["sha256"] != expected:
                errors.append(label + ": expected byte seal differs")
            return data
        except InputIntegrityError as error:
            files[label] = {"error": str(error)}
            errors.append(label + ": " + str(error))
            return None
    manifest = capture(harness_dir / "SHA256SUMS", "harness/SHA256SUMS",
                       args.expected_harness_manifest_sha256)
    if manifest is not None:
        try:
            entries = parse_delivery_manifest(manifest)
        except InputIntegrityError as error:
            errors.append("harness/SHA256SUMS: " + str(error))
    reference_entries = {} if reference is None else reference["manifest_entries"]
    # Even a missing/malformed after-manifest cannot suppress the before-list.
    for name in sorted(entries.keys() | reference_entries.keys()):
        expected = reference_entries.get(name, entries.get(name))
        capture(harness_dir / name, "harness/" + name, expected)
    capture(args.launcher, "launcher_input", args.expected_launcher_sha256)
    if args.source_archive_sha256 != SOURCE_ARCHIVE_SHA256:
        errors.append("source_archive: certified external pin differs")
    capture(args.source_archive, "source_archive", SOURCE_ARCHIVE_SHA256)
    for name in ("reader_launcher.py", "driver.py", "observe.py"):
        expected = args.expected_launcher_sha256 if name == "reader_launcher.py" else reference_entries.get(name, entries.get(name))
        capture(Path(launcher_dir) / name, "bind/" + name, expected)
    return {"manifest_entries": entries, "files": files, "errors": errors}

def run_with_input_integrity(args, receipt, launcher_dir, out, execute):
    """Always seal after execution; an after failure cannot retain a PASS verdict."""
    proof = {"schema": "ORD31_INPUT_INTEGRITY_BEFORE_AFTER_V1", "before": None,
             "after": None, "status": "FAILED_INPUT_INTEGRITY",
             "expected_harness_manifest_sha256": args.expected_harness_manifest_sha256,
             "expected_launcher_sha256": args.expected_launcher_sha256,
             "expected_source_archive_sha256": SOURCE_ARCHIVE_SHA256}
    original_error, after_error = None, None
    try:
        proof["before"] = snapshot_inputs(args, launcher_dir)
        if proof["before"]["errors"]:
            raise InputIntegrityError("before input seals failed")
        execute()
    except BaseException as error:
        original_error = error
        receipt["status"] = "FAILED_INPUT_INTEGRITY" if isinstance(error, InputIntegrityError) else "FAILED_CI_SCOPE"
        receipt["failure_class"], receipt["failure"] = type(error).__name__, str(error)
        raise
    finally:
        try:
            proof["after"] = snapshot_inputs(args, launcher_dir, reference=proof["before"])
            if proof["before"] is None or proof["before"]["errors"] or proof["after"]["errors"] or proof["before"] != proof["after"]:
                raise InputIntegrityError("before/after input seals failed or differ")
            proof["status"] = "PASS_INPUT_INTEGRITY_BEFORE_AFTER"
        except Exception as error:
            after_error = InputIntegrityError(str(error))
            receipt["status"] = "FAILED_INPUT_INTEGRITY"
            receipt["failure_class"], receipt["failure"] = type(after_error).__name__, str(after_error)
            proof["after_failure_class"], proof["after_failure"] = type(error).__name__, str(error)
            if original_error is not None:
                proof["original_failure_class"], proof["original_failure"] = type(original_error).__name__, str(original_error)
                receipt["original_failure_class"], receipt["original_failure"] = type(original_error).__name__, str(original_error)
        write_json(out / "input-integrity-before-after.json", proof)
        receipt["input_integrity"] = {"status": proof["status"],
                                      "proof_file": "input-integrity-before-after.json",
                                      "proof_sha256": digest(regular_bytes(out / "input-integrity-before-after.json"))}
        write_json(out / "receipt.json", receipt)
        for evidence in out.iterdir():
            if evidence.is_file():
                evidence.chmod(0o644)
        if after_error is not None:
            raise after_error from original_error

def digest(data):
    return hashlib.sha256(data).hexdigest()

def need(value, message):
    if not value:
        raise RuntimeError(message)

def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")

def render_unit(template, image, base):
    """Pure render of the reviewed template; only throwaway paths/network/image vary."""
    need(digest(template) == TEMPLATE_SHA256, "five-bind template pin mismatch")
    need(re.fullmatch(r"sha256:[0-9a-f]{64}", image) is not None and re.fullmatch(r"/[A-Za-z0-9._/-]+", str(base)) is not None, "unsafe CI image ID or throwaway path")
    text = template.decode("ascii")
    values = {"IMAGE_ID": image, "HOST_DATA_ROOT": str(base / "data"),
              "HOST_JOURNAL_ROOT": str(base / "journal"), "CONTAINER_JOURNAL_ROOT": "/c3po-bar-journal",
              "HOST_CAPACITY_ROOT": str(base / "capacity"), "HOST_SOURCE_ROOT": str(base / "source"),
              "CONTAINER_SOURCE_ROOT": "/c3po-source", "HOST_CONFIG_DIR": str(base / "etc"), "NETWORK": "none"}
    need(set(re.findall(r"@([A-Z_]+)@", text)) == set(values), "template substitutions changed")
    for key, value in values.items():
        text = text.replace("@" + key + "@", value)
    need("@" not in text, "unrendered substitution")
    lines = text.replace("\\\n", " ").splitlines()
    def command(key, prefix, count):
        found = [shlex.split(line.split("=", 1)[1].lstrip("-")) for line in lines if line.startswith(key + "=" + prefix)]
        need(len(found) == count, "unexpected " + key + " lines")
        return found
    argv, = command("ExecStart", "/", 1)
    check, = command("ExecStartPre", "/", 1)
    stop, = command("ExecStop", "-/", 1)
    files = [str(base / "etc" / (name + ".env")) for name in ("secret", "pins", "activation")]
    binds = [(str(base / "data"), "/app/day-d-data"), (str(base / "journal"), "/c3po-bar-journal"),
             (str(base / "capacity"), "/c3po-capacity"), (str(base / "source"), "/c3po-source"),
             (str(base / "etc" / "launcher"), "/c3po-reader")]
    mounts = [argv[index + 1] for index, value in enumerate(argv) if value == "--mount"]
    need(mounts == ["type=bind,source=%s,target=%s,readonly" % pair for pair in binds], "not exactly the five reviewed read-only binds")
    need(argv[:2] == ["/usr/bin/docker", "run"] and argv[argv.index(image):] == [image, "python", "-I", "-B", "/c3po-reader/reader_launcher.py"], "launcher command changed")
    need([argv[index + 1] for index, value in enumerate(argv) if value == "--env-file"] == files, "environment file list changed")
    need(command("ExecCondition", "/", 3) == [["/usr/bin/test", "-f", item] for item in files], "conditions changed")
    need(check == ["/usr/bin/docker", "image", "inspect", "--format", "{{.Id}}", image], "image check changed")
    need(stop == ["/usr/bin/docker", "stop", "-t", "25", "c3po-reader"], "stop command changed")
    return text, argv, check, stop, binds

def check_mounts(container, binds, image):
    listed = [(entry.get("Source"), entry.get("Destination"), entry.get("RW"))
              for entry in container.get("Mounts", []) if entry.get("Type") == "bind"]
    need(sorted(listed) == sorted((source, target, False) for source, target in binds), "engine mount list differs from five read-only binds")
    need(container.get("Image") == image and container.get("HostConfig", {}).get("Init") is True, "wrong image or docker-init absent")
    need(container.get("HostConfig", {}).get("ReadonlyRootfs") is True, "root filesystem is writable")
    need(container.get("HostConfig", {}).get("NetworkMode") == "none", "runtime network is enabled")

def check_directed(case, code, stdout, stderr, pin, token):
    notices, proofs = [], []
    for line in stdout.splitlines():
        if line.startswith("ORD31_PROOF "):
            proofs.append(json.loads(line[len("ORD31_PROOF "):]))
        else:
            notices.append(json.loads(line))
    need(len(proofs) == 1, "missing or repeated directed proof")
    proof = proofs[0]
    expected_exit = {"term": 0, "kill": 0, "handover": 0, "exit1": 1, "exit0": 78}[case]
    need(code == proof.get("launcher_main_exit") == expected_exit, "container/main exit mapping differs")
    need(proof.get("token") == token and proof.get("launcher_sha256") == pin, "proof identity differs")
    need(proof.get("child_pids_absent_after_main") is True and proof.get("exclusive_lock_immediate_after_main") is True, "no reap/lock-release proof")
    need(proof.get("real_worker_input_proof") == "NOT_COVERED", "directed proof overclaims worker intake")
    statuses = [item.get("status") for item in notices]
    expected = {"term": ["STARTING", "STATUS_WITHHELD", "STOPPED"],
                "kill": ["STARTING", "STATUS_WITHHELD", "STOPPED"],
                "handover": ["STARTING", "STATUS_WITHHELD", "HANDOVER", "READY_NOT_OBSERVED", "STARTING", "STATUS_WITHHELD", "STOPPED"],
                "exit1": ["STARTING", "STATUS_WITHHELD", "FAILED"],
                "exit0": ["STARTING", "STATUS_WITHHELD", "REFUSED"]}[case]
    need(statuses == expected, "directed notice order differs")
    for event in notices:
        if event.get("status") == "STARTING":
            need(event.get("launcher_sha256") == pin and event.get("launcher_pinned") is True, "STARTING does not carry mounted launcher pin")
            need(event.get("build_sha") == SOURCE_REVISION, "STARTING build pin differs")
    if case in {"term", "kill"}:
        end = notices[-1]
        need(end.get("reason") == "SIGNAL" and end.get("child_signal") == ("SIGKILL" if case == "kill" else "SIGTERM") and end.get("killed") is (case == "kill"), "stop signal/killed mapping differs")
    if case == "handover":
        for end in (notices[2], notices[-1]):
            need(end.get("child_signal") == "SIGTERM" and end.get("killed") is False, "phase end does not show TERM")
        need(notices[-1].get("reason") == "END_OF_DAY", "session did not reach end-of-day")
        need([event.get("phase") for event in notices if event.get("status") == "STARTING"] == ["PRE_OPEN", "SESSION"], "phase sequence differs")
    if case == "exit1":
        need(notices[-1].get("child_exit") == 1 and notices[-1].get("error") == "SourceUnavailable" and notices[-1].get("code") == "RAW_DIRECTED_TEST_FAILURE", "failure extraction differs")
    if case == "exit0":
        need(notices[-1].get("code") == "READER_DISABLED" and notices[-1].get("restart_allowed") is False, "worker exit0 does not cause refusal78")
    need("US:SYNTH" not in stdout + stderr and "PRIVATE FREE TEXT" not in stdout + stderr, "forbidden child output escaped the filter")
    lines = stderr.splitlines()
    need(len(lines) == (2 if case == "handover" else 1) and all(line.startswith(STATUS_PREFIX) for line in lines), "stderr contains other than the directed valid statuses")
    public = [json.loads(line[len(STATUS_PREFIX):]) for line in lines]
    need([item["child_pid"] for item in public] == [item["pid"] for item in proof["children"]], "forwarded status PID differs from reaped child")
    for event in notices:
        if event.get("status") in {"HANDOVER", "STOPPED", "FAILED"}:
            need(event.get("status_lines") == 1 and event.get("status_withheld") == 3 and event.get("dropped_lines", 0) >= 1, "filter end counters differ")
    return {"case": case, "exit": code, "proof": proof, "notices": notices, "result": "PASS_DIRECTED_ONLY"}

def archive_python_files(path):
    """Hash app bytes directly from a pinned archive; never execute archived code."""
    result = {}
    data = regular_bytes(path)
    need(digest(data) == SOURCE_ARCHIVE_SHA256, "archive bytes consumed differ from the certified source pin")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for item in archive.getmembers():
            prefix = "c3po/backend/app/"
            if item.isfile() and item.name.startswith(prefix) and item.name.endswith(".py"):
                relative = item.name[len(prefix):]
                need(".." not in Path(relative).parts, "archive path traversal")
                need(relative not in result, "repeated archive source path")
                result[relative] = digest(archive.extractfile(item).read())
    need(bool(result), "archive has no backend app source")
    return result

def local_engine_environment(environment, docker_config, *, socket_stat=os.lstat):
    """Pin the CI CLI to its local Unix socket; never inherit remote contexts/TLS."""
    try:
        info = socket_stat("/var/run/docker.sock")
    except OSError:
        raise RuntimeError("local CI Docker socket is absent") from None
    need(stat.S_ISSOCK(info.st_mode), "local CI Docker path is not a socket")
    result = {key: value for key, value in environment.items()
              if key not in {"DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}}
    result["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    result["DOCKER_CONFIG"] = str(docker_config)
    return result

def run_engine(args, receipt, source_files, argv, check, stop, binds, base, out):
    need(sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
         and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
         and os.environ.get("HOSTOPS_THROWAWAY_RUNNER") == "yes" and os.geteuid() == 0,
         "execute-ci requires an explicitly throwaway Linux GitHub-hosted root runner")
    need(args.image_id != PRODUCTION_IMAGE_ID, "production image ID cannot be a CI target")
    need(Path("/usr/bin/docker").is_file(), "Docker is absent from the CI runner")
    env = local_engine_environment(os.environ, base / "etc" / "docker-cli")
    def call(command, timeout=30):
        return subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout, check=True)
    def inspect():
        return json.loads(call(["/usr/bin/docker", "inspect", "c3po-reader"]).stdout)[0]
    need(not call(["/usr/bin/docker", "ps", "-a", "--filter", "name=^c3po-reader$", "-q"]).stdout.strip(), "c3po-reader already exists; refusing to touch it")
    metadata = json.loads(call(["/usr/bin/docker", "image", "inspect", args.image_id]).stdout)[0]
    labels = metadata.get("Config", {}).get("Labels") or {}
    need(metadata.get("Id") == args.image_id and labels.get("org.opencontainers.image.revision") == SOURCE_REVISION, "CI image revision label differs")
    need(call(check).stdout.strip() == args.image_id, "rendered image check differs")
    readback_program = "import hashlib,json;from pathlib import Path;r=Path('/app/app');print(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*.py'))},sort_keys=True))"
    readback = json.loads(call(["/usr/bin/docker", "run", "--rm", "--pull", "never", "--network", "none", "--read-only", "--cap-drop", "ALL", "--entrypoint", "python", args.image_id, "-I", "-B", "-c", readback_program]).stdout)
    need(readback == source_files, "image app bytes differ from the exact source archive")
    write_json(out / "image-source-readback.json", {"image_id": args.image_id, "revision_label": SOURCE_REVISION, "app_files": readback, "archive_sha256": args.source_archive_sha256})
    receipt["image_source_readback"] = "PASS_APP_PYTHON_BYTES"
    receipt["cases"] = []
    for case in ("flags-off", "other-pin", "term", "kill", "handover", "exit1", "exit0"):
        token = uuid.uuid4().hex
        pin = "0" * 64 if case == "other-pin" else args.expected_launcher_sha256
        (base / "etc" / "pins.env").write_text(make_pins(pin), encoding="ascii")
        flags = "false" if case in {"flags-off", "other-pin"} else "true"
        (base / "etc" / "activation.env").write_text("C3PO_R2D2_V2_SHADOW_ENABLED=" + flags + "\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=" + flags + "\n", encoding="ascii")
        command = list(argv)
        if case not in {"flags-off", "other-pin"}:
            command[-1:] = ["/c3po-reader/driver.py", case, token, args.expected_launcher_sha256]
        actual_id = None
        with (out / (case + "-stdout.log")).open("x") as stdout, (out / (case + "-stderr.log")).open("x") as stderr:
            process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr)
            try:
                if case in {"term", "kill"}:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline and process.poll() is None:
                        observed = subprocess.run(["/usr/bin/docker", "exec", "c3po-reader", "python", "-I", "-B", "/c3po-reader/observe.py", token], env=env, capture_output=True, text=True, timeout=5)
                        if observed.returncode == 0:
                            container = inspect()
                            need(container.get("Config", {}).get("Cmd") == command[command.index(args.image_id) + 1:], "a different container owns the reader name")
                            actual_id = container["Id"]
                            check_mounts(container, binds, args.image_id)
                            write_json(out / (case + "-engine-observation.json"), {"container_id": actual_id, "image_id": args.image_id, "mounts": container["Mounts"], "live_child": json.loads(observed.stdout)})
                            break
                        time.sleep(0.1)
                    need(actual_id is not None, "directed lock-holding child never appeared")
                    call(stop, timeout=30)
                process.wait(timeout=60)
            except Exception:
                if actual_id is None:
                    try:
                        container = inspect()
                        need(container.get("Config", {}).get("Cmd") == command[command.index(args.image_id) + 1:], "unknown container command during failure")
                        check_mounts(container, binds, args.image_id)
                        actual_id = container["Id"]
                    except Exception:
                        pass  # Ownership was not established; leave it to disposable-runner teardown.
                # Remove only the exact container ID already proved to be this directed command.
                if actual_id is not None:
                    subprocess.run(["/usr/bin/docker", "rm", "--force", actual_id], env=env, capture_output=True, text=True, timeout=30)
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                raise
        output = (out / (case + "-stdout.log")).read_text()
        errors = (out / (case + "-stderr.log")).read_text()
        if case in {"flags-off", "other-pin"}:
            events = [json.loads(line) for line in output.splitlines()]
            allowed = {"READER_LAUNCHER_PIN"} if case == "other-pin" else {"READER_SESSION", "READER_WINDOW", "READER_DISABLED"}
            need(process.returncode == 78 and errors == "" and len(events) == 1 and events[0].get("status") == "REFUSED" and events[0].get("code") in allowed and events[0].get("restart_allowed") is False, "unmodified launcher refusal differs")
            result = {"case": case, "exit": 78, "notices": events, "result": "PASS_UNMODIFIED_COMMAND"}
        else:
            result = check_directed(case, process.returncode, output, errors, args.expected_launcher_sha256, token)
        write_json(out / (case + "-check.json"), result)
        receipt["cases"].append(result)
        need(not call(["/usr/bin/docker", "ps", "-a", "--filter", "name=^c3po-reader$", "-q"]).stdout.strip(), "reader container remains after case")
    receipt["status"] = "PASS_LAUNCHER_LIFECYCLE_SHAPES"

def make_pins(pin):
    return "\n".join(["C3PO_BUILD_SHA=" + SOURCE_REVISION,
                      "C3PO_R2D2_V2_SHADOW_RELEASE_FILE=/app/day-d-data/smoke/release.json",
                      "C3PO_R2D2_V2_SHADOW_RELEASE_SHA=" + "0" * 64,
                      "C3PO_R2D2_V2_SHADOW_SOURCE_DIR=/c3po-source",
                      "C3PO_R2D2_MICROSTRUCTURE_RAW_DIR=/app/day-d-data/provider=eodhd/microstructure/raw",
                      "C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=/c3po-bar-journal",
                      "C3PO_R2D2_V2_CAPACITY_REQUIRED=true",
                      "C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY",
                      "C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=/c3po-capacity/config/smoke.json",
                      "C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=" + "0" * 64,
                      "C3PO_R2D2_V2_SHADOW_POLL_SECONDS=1.0",
                      "C3PO_READER_LAUNCHER_SHA256=" + pin]) + "\n"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--expected-launcher-sha256", required=True)
    parser.add_argument("--expected-harness-manifest-sha256", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute-ci", action="store_true")
    args = parser.parse_args()
    need(re.fullmatch(r"[0-9a-f]{64}", args.expected_launcher_sha256) and re.fullmatch(r"[0-9a-f]{64}", args.expected_harness_manifest_sha256) and re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_id), "invalid launcher/manifest pin or image ID")
    need(digest(regular_bytes(args.launcher)) == args.expected_launcher_sha256, "input launcher does not match explicit expected pin")
    need(args.source_archive_sha256 == SOURCE_ARCHIVE_SHA256, "source archive pin is not the certified dd4ec4bb artifact")
    need(digest(regular_bytes(args.source_archive)) == SOURCE_ARCHIVE_SHA256, "source archive bytes differ from the certified dd4ec4bb artifact")
    source_files = archive_python_files(args.source_archive)
    args.out.mkdir(mode=0o755, parents=True, exist_ok=False)
    base = Path(tempfile.mkdtemp(prefix="ord31-reader-ci-", dir=str(args.out)))
    for relative in ("data", "journal", "capacity", "source", "etc", "etc/docker-cli", "etc/launcher"):
        (base / relative).mkdir(mode=0o700)
    for source, name in ((args.launcher, "reader_launcher.py"), (HERE / "driver.py", "driver.py"), (HERE / "observe.py", "observe.py")):
        with (base / "etc" / "launcher" / name).open("xb") as stream:
            stream.write(regular_bytes(source))
        (base / "etc" / "launcher" / name).chmod(0o600)
    (base / "journal" / "maintenance.lock").write_bytes(b"")
    (base / "journal" / "maintenance.lock").chmod(0o600)
    for name, body in (("secret", "C3PO_DATABASE_URL=\n"), ("pins", make_pins(args.expected_launcher_sha256)), ("activation", "C3PO_R2D2_V2_SHADOW_ENABLED=false\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=false\n")):
        (base / "etc" / (name + ".env")).write_text(body, encoding="ascii")
        (base / "etc" / (name + ".env")).chmod(0o600)
    template = regular_bytes(HERE / "reader.service.template")
    text, argv, check, stop, binds = render_unit(template, args.image_id, base)
    (args.out / "reader.service.rendered").write_text(text, encoding="ascii")
    write_json(args.out / "commands.json", {"ExecStart": argv, "ExecStartPre_image": check, "ExecStop": stop, "binds": binds})
    receipt = {"schema": "ORD31_READER_CI_DRAFT_V1", "status": "PREPARED_NOT_EXECUTED",
               "launcher_sha256": args.expected_launcher_sha256, "image_id": args.image_id,
               "source_revision": SOURCE_REVISION, "source_archive_sha256": args.source_archive_sha256,
               "unit_template_sha256": TEMPLATE_SHA256, "rendered_unit_sha256": digest(text.encode("ascii")),
               "harness_sha256": {name: digest(regular_bytes(HERE / name)) for name in ("run_ci.py", "driver.py", "observe.py")},
               "source_app_python_files": len(source_files), "real_worker_inputs": "NOT_COVERED",
               "systemd_host": "NOT_COVERED", "production_image_runtime": "NOT_COVERED",
               "engine_mount_observation_cases": ["term", "kill"],
               "other_directed_cases_use_same_rendered_five_bind_argv": True,
               "claim_real_reader_inputs": False, "claim_host_proof": False}
    def execute():
        if args.execute_ci:
            run_engine(args, receipt, source_files, argv, check, stop, binds, base, args.out)
    run_with_input_integrity(args, receipt, base / "etc" / "launcher", args.out, execute)
    print(json.dumps({"status": receipt["status"], "receipt_sha256": digest(regular_bytes(args.out / "receipt.json"))}, sort_keys=True))

if __name__ == "__main__":
    main()
