# C3 — the TLS probe of the supervisor network (HOSTOPS02, `GO_READONLY_HOSTOPS02_TLS_PROBE_01`)

Offline work only. Nothing in this directory was run on the host, pushed or bound. Every hash named here was taken by
command. Built on the frozen core (generation `4c24c5cf…`, seal `73fb546b…`), which this operation does not modify:
`../core/assemble.py --check .` prints `BUILD_EQUAL`.

Contents: 1 name and class · 2 day, band, gate · 3 the provider's host and port · 4 the probe script and its line ·
5 the run in order, and the budget · 6 refusals and verdicts · 7 the receipt · 8 the Linux proof · 9 proven and
unproven · 10 decisions · 11 against the siblings.

---

## 1. Name and class

The weekend authority (A1 rev 2, `909573aa…`, section 4.2) lists C3 among the container runs that are *not* reads in
its own sense ("Execução de contêiner não é leitura: cria e remove um contêiner") and keeps it under the owner's
individual signature by hash. That is the authority's signature regime. The name of an operation of this family
follows the core's classes, which are another matter:

| Core rule (CORE.md) | What it says | C3 |
|---|---|---|
| Section 4, kinds | `CONTAINER`: "an attached `docker run` that creates and removes one container with read-only binds only" | one attached run, `--rm`, no bind at all |
| Section 8, rule 1 | "A container run with read-only binds is allowed in a reading source and is said in its scope statement and side effects" | said in `SCOPE_STATEMENT` and `side_effects` |
| Section 4, kinds | `EFFECT`: "changes the host or the engine; exists only where `WRITES_ALLOWED` is True" | nothing of the host's filesystem or of the engine's state is changed (the container is the engine's, created and removed by it) |
| Section 3 | a source whose `WRITES_ALLOWED` is False is of class `READ` | `DATE_CLASS='READ'` |
| `assemble.py` lint | `GO_READONLY_HOSTOPS02_…` for a reading source, `GO_WRITE_…` for a writing one; `READONLY_…` schemas and phase | refused otherwise |

So the operation is `GO_READONLY_HOSTOPS02_TLS_PROBE_01`, phase `READONLY_SUPERVISOR_TLS_PROBE`, exactly like K11
(`GO_READONLY_HOSTOPS02_EPOCH_READBACK_01`), which also starts one container and is also under individual signature in
the A1 (row C4). `GO_WRITE_…` would need `WRITES_ALLOWED=True` and an `EFFECT` row: it would say that the probe
changes the host, which it does not, and it would put the run under the write class's dates (`WRITE_WEEKEND`, three
days) instead of the narrower band below. The one thing the class does not say, and the scope does: this is the only
run of the family with a network (`bridge`), and its traffic leaves the host (side effects, second item).

## 2. Day, band, gate

- `DATE_CLASS='READ'`, `DATES=DATE_SETS['READ']` (nine days): the core requires it and the dispatcher carries it.
- `validate_plan` narrows it: the signed window (`plan.window` = the request's window) must begin on `2026-10-04`
  (`PROBE_DAY_NOT_IN_SCOPE`) and lie inside `2026-10-04T11:45:00Z .. 2026-10-04T12:30:00Z`
  (`PROBE_WINDOW_OUTSIDE_THE_BAND`): the A1 row C3, "dom 04/10, 08:45–09:30 (11:45–12:30Z); antes de E3". The
  dispatcher runs `authenticate()` before any claim, so both layers refuse, with the source's own code and no claim
  (tests: `test_conformance.py`, the replaced date-scope test).
- Saturday is excluded: the A1 has no band for C3 on 03/10; its reserves R1–R4 serve its reads only (cases i–iii);
  its section 5 says the GO "nunca muda o dia". A "same-day spare" is not a rule of this family for C3: the bytes allow
  any request inside the band, and a second request needs its own "Assino" and the A1's section 8 (a spare only
  replaces a principal provably never dispatched).
- `MAX_GATE_SPAN_SECONDS=900`: the A1's section 5 limit for the GO's short window. The request and the authority may
  carry the whole band (2700 s); the gate is the intersection with the GO (`test_a_window_of_the_band_longer_than_the_gate…`).
- Not in the bytes, for the binder: the dispatch minute is outside HH:05–07, HH:10–25, HH:35–37 (A1 section 3). Inside
  the band that leaves 11:45–12:04, 12:08–12:09 and 12:26–12:30 UTC.

## 3. The provider's host and port

| Value | From | Line |
|---|---|---|
| host `socket.massive.com` | `c3po/backend/app/r2d2_v2_massive_transport.py` at dd4ec4bb (sha256 `2ff62bb6…`) | 99: `socket=connector('wss://socket.massive.com/stocks',open_timeout=10,` |
| port `443` | the URI has no port; the client the transport uses (websockets, `requirements.txt` line 8: `websockets>=14,<16`) takes 443 for `wss` | websockets `uri.py`: `port = parsed.port or (443 if secure else 80)` (read in 15.0.1) |
| the same pair | `c3po/deployment/massive-supervisor/README.md` at dd4ec4bb (`644c6211…`) | 580: "2. A TLS connection to `socket.massive.com:443` succeeds from `@NETWORK@`, without a token." |

No other `wss://` endpoint is in the transport (pinned by `test_static_pins.py`). The transport's client resolves with
`socket.create_connection((host, port))`, sets no proxy (`proxy=None`), and wraps with `ssl.create_default_context()`
and `server_hostname=host` (websockets `sync/client.py`, version 15.0.1). The probe makes the same three steps, with the
image's own trust store, and stops after the handshake.

## 4. The probe script and its line

`PROBE_SCRIPT` (5746 bytes, sha256 `d625d84f…`) is carried in `op.py` as a raw string; `script_bytes()` compares size
and hash before anything (`SCRIPT_NOT_THE_PINNED_HASH`, also inside `validate_plan`, so before any claim). The
container gets these bytes and nothing else on standard input, under `python -I -B -`.

| Step | Bound | Codes | Notes |
|---|---|---|---|
| alarm | `signal.alarm(14)`, the first statement | — | the kernel ends the interpreter at 14 s; under `--init` docker-init reports 142; the CLI's limit is 20 s |
| context | — | `TLS_CONTEXT_NOT_VERIFYING` | `ssl.create_default_context()`; refuses unless `verify_mode == CERT_REQUIRED` and `check_hostname` |
| DNS | a thread joined for 4 s | `DNS_TIMEOUT`, `DNS_NAME_NOT_RESOLVED` (EAI_NONAME, EAI_NODATA), `DNS_FAILED`, `DNS_NO_ADDRESS` | `getaddrinfo(host, 443, 0, SOCK_STREAM, IPPROTO_TCP)`; distinct IPv4/IPv6 answers, at most 16 counted |
| TCP | 4 s in total over the answers, in order | `TCP_REFUSED`, `TCP_TIMEOUT`, `TCP_UNREACHABLE` | each attempt gets what is left of the 4 s; the first that connects is kept |
| TLS | 4 s, its own | `TLS_CERTIFICATE_NOT_VERIFIED` (+ the OpenSSL verify code), `TLS_HANDSHAKE_TIMEOUT`, `TLS_PROTOCOL_ERROR`, `TLS_CONNECTION_ERROR` | one handshake, server name `socket.massive.com`; on success the version, the cipher name, the SHA-256 of the leaf's DER |
| end | — | `PROBE_FAILED` (any exception) | one line, `json.dumps(sort_keys, compact)`, `os._exit(0)`; the socket is closed without `unwrap` |

What it never does: `send`, `sendall`, a read after the handshake, `unwrap` (close_notify), any HTTP, any write but the
one line on standard output (pinned by `test_script_constants_agree…`, which walks its syntax tree). Worst case:
4 + 4 + 4 s of network plus the interpreter's start, under the 14 s alarm, under the 20 s class.

The line (`LINE_SCHEMA='HOSTOPS02_TLS_PROBE_LINE_V1'`):

```
{"application_bytes_sent":0,"context":{"check_hostname":true,"verify_mode_required":true},
 "dns":{"addresses":1,"answered":true,"code":null,"ipv4":1,"ipv6":0,"ms":0},"host":"socket.massive.com","port":443,
 "schema":"HOSTOPS02_TLS_PROBE_LINE_V1","status":"TLS_VERIFIED",
 "tcp":{"attempts":1,"code":null,"connected":true,"family":"ipv4","ms":0},
 "tls":{"cipher":"TLS_AES_256_GCM_SHA384","code":null,"handshake":true,"leaf_sha256":"<64 hex>","ms":1,"verified":true,"verify_code":null,"version":"TLSv1.3"},
 "total_ms":4}
```

`line_grammar()` accepts it only when every key set is exact, every member has its type and range (counts ≤ 16,
milliseconds ≤ 60000, verify code ≤ 1000, version TLSv1.2 or TLSv1.3, cipher `[A-Z0-9][A-Z0-9_-]{0,63}`, a non-zero
64-hex leaf hash, codes from the lists above), the host and port are the provider's, `application_bytes_sent` is 0,
and the members agree with the status (a DNS failure has no TCP attempt; a TCP failure has an answer and no
handshake; `TLS_NOT_VERIFIED` has a connection, no handshake and `TLS_CERTIFICATE_NOT_VERIFIED`; `TLS_VERIFIED` has a
verifying context, an answer, a connection, a completed and verified handshake, a version, a cipher and a leaf and no
code; `TLS_CONTEXT_NOT_VERIFYING` touched nothing). Only a line that meets it is copied into the receipt; of any other
output only its size and hash are kept.

## 5. The run, in order, and the budget

| # | What | Command | Class | A failure |
|---|---|---|---|---|
| 0 | pure: script bytes, container name `hostops02-tls-<16 hex of the GO>` | — | — | — |
| 1 | first `gate()` | — | — | dry gate stops here |
| 2 | executor 0:0 | — | — | `EXECUTOR_IDENTITY` |
| 3 | boot of the evidence | read of `/proc/sys/kernel/random/boot_id` | — | `EVIDENCE_FROM_EARLIER_BOOT` |
| 4 | the image by the signed ID: ID, revision label | `docker image inspect --format IMAGE_FORMAT <ID>` | QUICK 8 s | `IMAGE_…` |
| 5 | the retention tag: resolves to that ID, is among its tags | `docker image inspect --format IMAGE_FORMAT <tag>` | QUICK 8 s | `RETENTION_TAG_…` |
| 6 | every container; this GO's name is free | `docker ps -a --no-trunc --format PS_FORMAT` | QUICK 8 s | `CONTAINER_LISTING_FAILED`, `CONTAINER_NAME_TAKEN` |
| 7 | the budget: `gate() >= effects_budget(probe)` = 20 + 4 = 24 s | — | — | `BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER` |
| 8 | the probe | `docker run <PROBE_PREFIX> --name … <ID> python -I -B -` + the script on stdin | RUN_SHORT 20 s | from here on nothing refuses |
| 9 | every container again | `docker ps -a …` | QUICK 8 s | a finding, never a refusal |

Worst case 3 × 8 + 24 + 8 = 56 s < 60 s. The reads of 4–6 normally take well under a second each.

## 6. Refusals and verdicts

| Exit | status | outcome | When |
|---|---|---|---|
| 0 | `METADATA_ONLY_REQUIRES_REVIEW` | `TLS_VERIFIED_TO_THE_PROVIDER_HOST` | CLI 0, a valid `TLS_VERIFIED` line, the listing after complete, no container of the name, none that was not there |
| 1 | `REFUSED` | `REFUSED_NO_CONTAINER_STARTED` | any refusal of 2–7, or the runner refused to start 8: nothing started, nothing on the network |
| 2 | `PARTIAL_METADATA_REQUIRES_REVIEW` | `PROBE_RAN_TLS_NOT_VERIFIED` | a valid line that is not `TLS_VERIFIED` (code: the failed step's) |
| 2 | 〃 | `TLS_VERIFIED_WITH_FINDINGS` | a valid `TLS_VERIFIED` line beside docker's own status 125–127, an unavailable listing, a container of the name still listed, or a new container |
| 2 | 〃 | `PARTIAL_PROBE_RESULT_UNKNOWN` | the run did not return, or no valid line (engine status, alarm 142, not one line, not the grammar, a non-zero exit) |
| 2 | 〃 | `PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN` | an escape after the run started (the core's envelope) |
| 3 | — | — | anything that escapes `run()` (the launcher) |

"REFUSED" for a reading source of this core usually means "nothing observed". Here it means "no container started":
the reads of 3–6 observed the image and the containers, and a mismatch among them is still a refusal, because the
thing this operation is for (one connection from the network bridge) did not happen and nothing changed. K2a uses the
same rule for its docker reads before its container.

## 7. The receipt

Counts, booleans, constant codes, hashes, timings, and two names the task asks for (TLS version, cipher). Never an
address (the script prints none; a test scans the receipt for IPv4 text), never a certificate name, never a byte of the
output (only its size and SHA-256 when it is not a valid line), never the text of an exception. The full list is in
CONTRACT.txt section 3.8. Size: about 4 kB (4055 bytes for a complete receipt of the emulated run); `REDUCTIONS` is empty (the limit is 60,000 bytes).

## 8. The Linux proof (`linux_root/`, NOT RUN)

`run.sh` (from this directory, after the core's job step and preferably last in the job) on a throwaway GitHub-hosted
ubuntu-24.04 runner, as the runner's user with `sudo -n`:

1. Refuses unless: Linux, `HOSTOPS_THROWAWAY_RUNNER=yes`, GitHub Actions, `RUNNER_ENVIRONMENT=github-hosted`, not root,
   none of the host's paths exist, the seal holds, `BUILD_EQUAL`, `openssl` and `iptables` usable, the release files
   (README, transport, Dockerfile) are the pinned ones, the image store is the containerd snapshotter.
2. Makes a throwaway authority and two leaves (the provider's name, `other.invalid`) in a private `mktemp` directory;
   the keys never leave it and are removed at the end.
3. Builds two images on the release's base **by digest** (`python:3.12-alpine3.24@sha256:b64631e0…`), both labelled with
   the release revision and tagged with retention-grammar names: `…-ci-trusting`, which appends the authority to the
   default bundle that `ssl.get_default_verify_paths()` names (TEST ONLY), and `…-ci-stock`, the base as it is.
4. Reads the gateway of the network bridge, saves `daemon.json`, adds `"dns": [<gateway>]`, restarts the engine, checks
   the gateway and the image store did not change. No address is written in any file of the branch (public safety).
5. The guard: three `FORWARD -i docker0` rules reject TCP 443, TCP 53 and UDP 53 that the network bridge would forward
   anywhere. Their packet counter must be 0 at the end.
6. `probe_shape.py` (as root): starts the DNS stand-in on `<gateway>:53` and the TLS stand-in on `<gateway>:443`
   (`stubs.py`), checks that a container of the network bridge gets the stand-in as its only name server and that the
   provider's name resolves to the gateway only (otherwise no probe starts), then runs **the source's own
   `perform()` and `Native`** six times with the real argv:

   | Case | Image | DNS | TLS | Expected |
   |---|---|---|---|---|
   | verified | trusting | answer | good | `TLS_VERIFIED_TO_THE_PROVIDER_HOST`, the leaf hash = the stand-in's leaf, SNI `socket.massive.com`, 0 application bytes |
   | image_without_the_test_authority | stock | answer | good | `TLS_CERTIFICATE_NOT_VERIFIED`, verify code 19 or 20 |
   | certificate_of_another_name | trusting | answer | other_name | `TLS_CERTIFICATE_NOT_VERIFIED`, verify code 62 |
   | port_refused | trusting | answer | closed | `TCP_REFUSED`, no connection |
   | name_not_found | trusting | nxdomain | good | `DNS_NAME_NOT_RESOLVED`, no connection |
   | handshake_never_answered | trusting | answer | hang | `TLS_HANDSHAKE_TIMEOUT`, 4–5 s, the run under 14 s |

   and, with the source's row and `container_run` but a sleeping snippet, inspects the running container
   (`NetworkMode bridge` and only that network, no bind or mount, `AutoRemove`, read-only root, `CapDrop ALL`, no
   privilege or device, `no-new-privileges`, init, user `0:0`, the image by ID, the command, the image's environment
   unchanged, stdin attached once), then checks that no container of its name is listed; and reads `docker events`
   of the verified probe (create, connect to `bridge` only, start, die 0, destroy).
7. Puts back `daemon.json` and restarts the engine; removes the guard, the images and the work directory; checks the
   seal again. Exit 0 only when every run was made, every expectation is met, the guard rejected nothing, and the
   engine's DNS is back.

The sealed bytes are never changed: the stand-ins are reached because the engine's DNS (a property of the runner) and
the trust store (a property of the test image) say so. `--self-test` runs the same collection on the emulation.

## 9. Proven and unproven

- C3-U1 the network bridge reaches the provider: egress and the engine's DNS on the host. **Only the run on the host.**
- C3-U2 the production image's trust store verifies the provider's chain for `socket.massive.com`. **Only the run on
  the host.** The Linux proof uses a test authority and the release's base, not the production image.
- C3-U3 the argv on a real engine (`--init`, `--network bridge`, `--read-only`, `--rm` removal, alarm → 142 through
  docker-init) — closed by the Linux job for the runner's engine; the host's engine (29.5.3) is shown by the run itself.
- C3-U4 the docker CLI without `DOCKER_CONFIG` and `HOME` writes nothing — not observed (same as the precheck's reads).
- C3-U5 the duration on the host (expected 1–2 s when TLS is verified; at most about 15 s).
- C3-U6 what a CLI killed at 20 s leaves: the alarm should prevent it; if it happens, the receipt lists the name.

## 10. Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | No HTTP request | README item 2 asks for the TLS connection only; A1 C3 says "não envia nada"; an HTTP GET to a WebSocket endpoint adds nothing to egress, DNS and trust, and puts application bytes in the provider's logs |
| D2 | No `DOCKER_CONFIG` | the reads of the family run so; giving the unit's directory risks a write into it (K2A-U2 open until the Saturday rehearsal); a reading source cannot create a throwaway one |
| D3 | The band is a constant | defense in depth for a 45-minute window: a wrong date in a signed request cannot run the probe; a moved band needs new bytes |
| D4 | TLSv1.2 or TLSv1.3 only | Python's default floor; anything older is not a line of the grammar |
| D5 | `GO_READONLY` | section 1 |
| D6 | Retention tag checked in the run | A1 4.2: the image must be the one the retention tag names; the README (line 131) reads both the ID and the tag |
| D7 | No second connection without verification (to hash an unverified leaf) | "refuse to send anything else": one connection, one handshake |

## 11. Against the siblings

- K2a (`catalog_init`): the same shape of precheck, container and verdict; the same rule that a refusal means "no
  container started". Differences: no bind, no `EFFECT` (nothing is written), network `bridge`, `--name`, a grammar of
  the line instead of a readback of files.
- K11 (`epoch_readback`): the same class (`READ`, `GO_READONLY`), `--name hostops02-…-<go16>`, an alarm before the CLI's
  limit, a container under individual signature. Differences: K11 observes many items and its outcome is a set of
  findings; C3 has one purpose and one success.
- The four tier 0 seals are unchanged by this operation; its conformance suite refuses their documents in both
  directions when they lie beside the core.
