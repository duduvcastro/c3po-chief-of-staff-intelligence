# Reader units (MASTER_PLAN row B2) on the frozen HOSTOPS02 core — `GO_WRITE_HOSTOPS02_READER_UNITS_01`

Offline work only (2026-10-05 UTC, Sunday evening BRT). Nothing here was run on the host, pushed, bound, or reviewed by Codex. Every hash was taken by command; where this text differs from `SHA256SUMS`, `VALIDATION.json` or a mutation record, those files prevail. `W` = the work directory of the epoch (`.../va/work`); `S` = the session scratch directory. No absolute path of a workstation appears in this directory.

Abbreviations. `RDR` = the reader README of the installation candidate (`S/opsart/c3po/deployment/reader/README.md`, opsart branch `ops/r2d2-v2-epoch03-artifacts-20261002` at `4a6f7675…5562`). `HOC` = HOSTOPS01 revision 3 `CONTRACT.txt` (`S/hostops01/candidate`). `PLAN` = `W/fable-epoch03-masterplan-20261002/MASTER_PLAN.md`. `CORE` = `W/hostops02-sealed/core/CORE.md`.

## 0. In one paragraph

The owner decided on 2026-10-05T00:09:24Z that the reader is kept this epoch (`W/fable-owner-signatures-20260930/DUDU_DECISION_READER_KEPT_20261004.json`). PLAN row B2 ("Reader units", "hostops01 install_units, second request … Missed: needs install bytes with a later date set") was missed: HOSTOPS01's writes are dated 10-02 … 10-04 UTC and that family is closed. This directory ports OP_INSTALL_UNITS (HOC section 6) onto the frozen core for the three reader units, as the supervisor pair was installed by e3-20261004-a (`UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED`): exclusive creation, not activated, not reloaded; K13 (M6) activates later. **No new core generation**: every call it needs exists in the frozen core (`files.create_file` is HOSTOPS01's `install_unit` with arguments, CORE §2); the one thing the core lacks — reading the text of a symbolic link — is answered by the precheck evidence, not by a new generation (section 5, D-2).

## 1. What it does

| Order | Step | Changes the host |
|---|---|---|
| pure | the three files rendered from the source's own templates and values; each must hash to the request's `rendered_sha256`/`rendered_bytes` | no |
| 1 | executor 0:0, `umask(022)`, boot of the evidence | no |
| 2 | `/etc/systemd/system` walked by its signed rows and held | no |
| 3 | `c3po-massive.service` (E3): lstat regular 0:0 0644 one link, read by descriptor, 1674 bytes, sha256 `662c57b9…bc06`; its journal bind (source, target = its `--journal-root`, not readonly) and its image (twice, one ID) must equal the reader's values; its other bind sources (`/etc/c3po-bar`, `/var/lib/c3po-bar/supervisor`) must not overlap the journal root | no |
| 4 | journal root walked (root-only chain, leaf 0:0 0700) and held; `epoch.json` and `maintenance.lock` in it by **lstat only**: regular, 0:0, 0600, one link (Codex E1-19: B2 only after E3 and the real catalogue) | no |
| 5 | data volume walked (open root at the volume, uid 1000 accepted as signed; a mount point; another device than the journal) | no |
| 6 | the unit table at the three names, the conflict scan of the twelve lookup directories, the leftovers, the fixed precedence (HOC 6.3), then 15 s must be left | no |
| 7 | per unit expected ABSENT, service → timer → alert: `create_file(index, …, 0644)` | yes: 4 mutating calls per unit |
| 8 | readback: each name through the held directory (bytes, identity, one link, 0:0 0644; a unit signed PRESENT against its signed identity), then the directory again from "/" | no |

Outcomes: `UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED` (exit 0), `PARTIAL_REQUIRES_RECONCILIATION` (exit 2), `REFUSED_NOTHING_CREATED` (exit 1). The receipt carries hashes and metadata only: a regular file found at a destination name that is not the render is reported without digest or size (a foreign unit may carry an inline secret; tested with the emulation's canary).

## 2. Unit texts

The service is RDR's `c3po-reader.service` (`8d2ff7a9…4fab`, D1 default: the launcher, `python -I -B /c3po-reader/reader_launcher.py`) with exactly two insertions (a test proves that nothing else differs):

```
RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_JOURNAL_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_SOURCE_ROOT@ @HOST_CONFIG_DIR@
  --mount type=bind,source=@HOST_SOURCE_ROOT@,target=@CONTAINER_SOURCE_ROOT@,readonly \      (after the capacity bind)
```

Template `3dc97680…7770` (1952 bytes). Rendered: `1a01a7d7eb6cede1ca4d406278fa03e4beabd86231a7dfacc5556ab92139aace`, 2108 bytes. The timer (`dc81e21b…4ba`, 289 bytes) and the alert unit (`0653bf41…ce2f`, 414 bytes) are RDR's, verbatim. The render applies RDR's substitution grammar (host paths `^/[A-Za-z0-9._/-]+$` clean, container targets `^/c3po-[a-z0-9][a-z0-9-]*$` not `/c3po-capacity`/`/c3po-reader` and distinct, image by ID, network not `host`/`none`/`bridge`/`container:*`), the exact placeholder counts, the isolation rules (configuration directory, journal root, source root, capacity root: none equal to, inside or around another bind source), and fails if any `@` survives.

## 3. Values, and where each comes from (all copied by command)

| Placeholder | Value | Source |
|---|---|---|
| `IMAGE_ID` | `sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb621` | e3-20261004-a receipt, `effects.units[0].substitutions` (RDR: "the same ID as the producer unit"); l1-20261003-a precheck image (revision label `dd4ec4bb`) |
| `HOST_DATA_ROOT` | `/mnt/day-d-data` | RDR; K10 (`install_release`), K13 |
| `HOST_JOURNAL_ROOT` / `CONTAINER_JOURNAL_ROOT` | `/var/lib/c3po-bar/journal` / `/c3po-bar-journal` | the installed producer unit (e3; read back by l6-20261004-a), checked again on the host in step 3 |
| `HOST_CAPACITY_ROOT` | `/var/lib/c3po-capacity` | e2-20261003-b provision ledger (`CAP_ROOT`) |
| `HOST_SOURCE_ROOT` | `/var/lib/c3po/r2d2-v2-source-20261005` | Codex #429 5985768668 (yes to the placement proposed in 5985753675), decision 6 (#429 5985748037, text sha256 `4b169599…9c55` = `W/codex-six-design-decisions-20261004.txt`); K4-E0 revision 4 creates it |
| `CONTAINER_SOURCE_ROOT` | `/c3po-source` | **chosen here** (K4 Q-K4-9: "a line of the sheet / B2 render"); the value K4's tests use |
| `HOST_CONFIG_DIR` | `/etc/c3po-reader` | e2-20261003-b provision ledger (`RDR_CONFIG`, `RDR_DOCKER_CLI`) |
| `NETWORK` | `c3po_c3po_internal` | W1 preflight l5-20261004-a: `network.inspect.name`, the network the `db` and the worker are attached to (compose `c3po_internal`, project `c3po`) |

The brief named the reader provision receipt as `43be27f5…`; by command that metadata hash is **e1-20261003-b** (supervisor directories, journal root included). The reader's directories are **e2-20261003-b** (`60d9af30…`): `/etc/c3po-reader`, `/etc/c3po-reader/docker-cli`, `/var/lib/c3po-reader` (where the alert unit writes its marker), the capacity tree. Neither created `/etc/c3po-reader/launcher` (K4 mode LAUNCHER, A8, does).

## 4. Cross-family constants (read, never edited; state at the time of reading, 2026-10-05 ~00:45Z)

| Constant | Here | Consumer | Agrees |
|---|---|---|---|
| unit names `c3po-reader.service`, `.timer`, `c3po-reader-alert.service` in `/etc/systemd/system`, 0:0 0644 one link | effects | K13 (`SERVICE_UNIT`, `TIMER_UNIT`, `ALERT_UNIT`, file checks), K13r | yes |
| reader unit SHA-256 for K13 `files.reader_service` / K4 PINS `reader_unit_sha256` | `1a01a7d7…aace` (2108 B) | K13 plan, K4 PINS plan (binder copies from this receipt) | to bind |
| timer / alert SHA-256 | `dc81e21b…4ba` / `0653bf41…ce2f` | K13 `files.reader_timer`, `files.reader_alert` | yes (K13 tests use the RDR bytes) |
| producer unit SHA-256 | `662c57b9…bc06` (constant here) | K13 `files.producer_service`, K4 PINS `producer_unit_sha256` | yes |
| five read-only binds `  --mount type=bind,source=S,target=T,readonly \` (data→`/app/day-d-data`, journal→`/c3po-bar-journal`, capacity→`/c3po-capacity`, source root→`/c3po-source`, launcher dir→`/c3po-reader`) | rendered | K13 `unit_text_checks` (op.py of 21:20 BRT: five pairs, source target signed, every `--mount` counted), K4 PINS `journal_and_mounts`/`bind_source`, K13r `.Mounts` (five binds) | yes (K13 revision 2 DESIGN.md still says four; its op.py says five) |
| image twice, no `@` | rendered | K13 `READER_UNIT_IMAGE_NOT_THE_PIN` | yes |
| producer journal line and `--journal-root /c3po-bar-journal ` once | read on the host | K13, K4 PINS | yes |
| `C3PO_R2D2_V2_SHADOW_SOURCE_DIR` = `/c3po-source` | `CONTAINER_SOURCE_ROOT` | K4 PINS (pins.env), K13 (pins check, `SOURCE_TARGET` grammar) | to sign on the sheet: pins.env must name `/c3po-source` |
| `C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR` = `/c3po-bar-journal` | `CONTAINER_JOURNAL_ROOT` | K4 PINS, K13 | yes |
| `C3PO_R2D2_V2_SHADOW_RELEASE_FILE` under `/app/day-d-data/…` (K10 installs `/mnt/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json`) | data bind | K4 PINS, K13 | yes (but see Q-1) |
| `C3PO_R2D2_V2_CAPACITY_CONFIG_FILE` = `/c3po-capacity/config/week.static.capacity.json` | capacity bind | K4 PINS | yes |
| launcher `/etc/c3po-reader/launcher/reader_launcher.py` → `/c3po-reader/reader_launcher.py` | bind + command | K4 LAUNCHER (A8), K13, K13r (main command) | yes |
| `secret.env`, `pins.env`, `activation.env` in `/etc/c3po-reader` (ExecCondition + `--env-file`) | rendered | K3 (A7), K4 PINS (B6), K13 ACTIVATE (`activation.env` 2053f3f6…) | yes |
| `DOCKER_CONFIG=/etc/c3po-reader/docker-cli` | rendered | e2 (created, empty), K13 (0:0 0700 check) | yes |
| container name `c3po-reader`, network `c3po_c3po_internal` | rendered | K13 (scan), K13r | network not checked by them |
| alert marker `/var/lib/c3po-reader/failed.<UTC>` | verbatim | e2 (directory) | yes |
| daemon-reload owner | `GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01` | K13 ACTIVATE (`enable --now`) | see Q-3 |

## 5. Deviations, with reasons

- **D-1 The fifth bind (template change).** RDR's unit has four binds and its repository test pins them; decision 6 moved the source root off the data volume, so the unit must bind it. The two insertions live only in this source (the opsart files are untouched); RDR's own test of the unit text would refuse these bytes. K13, K13r and K4 PINS already expect the fifth bind.
- **D-2 No alias-link scan.** HOSTOPS01's scan reads the text of every `*.service`/`*.timer` link in the lookup directories. The frozen core has no `readlink`, and an operation part may make no system call of its own (CORE rule 4). Rather than a new generation, the request must cite a `GO_READONLY_HOSTOPS_PRECHECK_01` receipt of the same boot: l1-20261003-a scanned the three reader names alias links included and found nothing (boot `50d356a1…`, the boot of e3). Everything else of the scan is HOSTOPS01's: same names, drop-in forms, own dependency directories, enablement links, shadowing, leftovers, unavailability. An alias created after that precheck is not seen; K13's `systemctl show` (FragmentPath, DropInPaths) is the next look.
- **D-3 No `findmnt`.** As in K13: the journal and the data volume are compared by device numbers of signed rows and held descriptors, not by mount source or filesystem type.
- **D-4 Bind sources not opened here.** The journal root and the data volume are walked (RDR operation 2 guards). The capacity root, the source root and the launcher directory are not: the source root (K4-E0) and the launcher directory (A8) may not exist when B2 runs, and a unit file binds nothing until K13 starts it. K4 PINS walks the source and journal chains; K13 walks the launcher and release chains at activation.
- **D-5 Values are constants, not request members.** A request signs only rows, unit expectations, leftovers and the boot; the values, templates and producer identity are bytes of the source. A different placement is a new source and a new review.
- **D-6 RDR operation 2 says the installation "runs `systemctl daemon-reload`".** Not here (HOC 6.2, PLAN §3.1 item 1): the manager is reloaded by K13's `enable --now`.
- **D-7 RDR's readback items** (`systemctl is-enabled`, an optional skipped `systemctl start`) are not done here: this source starts no process. K13 and K13r read the manager.

## 6. Open questions for Codex

| # | Question |
|---|---|
| Q-1 | **Decision 6 and the data-volume bind.** `/mnt/day-d-data` (uid 1000) stays a bind source of the reader (release file, `C3PO_R2D2_MICROSTRUCTURE_RAW_DIR`): it does not meet decision 6. This source declares it in its scope and walks it with an open root; K13r reports it as `not_root_controlled_sources`. Accept by name for this epoch, or require the release (K10) and the raw directory elsewhere — which would change these bytes? (Same question as K4 Q-K4-8.) |
| Q-2 | `CONTAINER_SOURCE_ROOT=/c3po-source`: confirm, so that pins.env (B6) and K13/K13r plans sign the same value. |
| Q-3 | Units installed without a reload; K13 ACTIVATE requires `LoadState=loaded` before its `enable --now` (K13 Q-3). If B11 (supervisor activation) reloads first, the reader units load then. Is that order, or K13 accepting `not-found` with the signed hash, the intended path? |
| Q-4 | Evidence for Monday: which read-only receipt of the boot of the run gives `unit_rows`, `journal_rows` and `data_rows`? l1-20261003-a has the unit directory chain and `/var/lib`; the journal leaf row comes from e1's ledger; the data volume rows from W1. Same boot required (`evidence_boot_id_sha256`). |
| Q-5 | D-2: is the alias scan of l1-20261003-a (same boot) sufficient, or must a new precheck of the same day be cited? (No readlink in the frozen core; a new generation would be needed for this source to do it itself.) |
| Q-6 | The network `c3po_c3po_internal` is `internal: true`: the reader reaches only `db` (its need). Confirm it is the intended network (RDR: "the existing compose network on which `db` resolves"). |

## 7. Tests (counts in `VALIDATION.json`)

`tests/test_conformance.py` (the core's 121), `tests/test_reader_units.py` (templates against RDR bytes; the render, every value refusal and placement rule; the producer facts; every plan refusal; the complete run with its exact mutating calls; every precheck refusal with the host unchanged; precedence; scan limits; budget edges; continuation over units signed present and acknowledged leftovers; every failure of an effect and what it leaves; the guards of K13 and K4 PINS applied to the render), `tests/test_native.py` (the source's own Native on a private tree with real lstat/open/read/write/fsync/link/unlink by descriptor, a real race at a final name, a real process death after a link and inside a write, and what the next precheck reports). `tests/unit_texts.py` holds the RDR and producer bytes copied by command, each with its hash. Mutation: `mutation/mutants.py` (one mutant per effects member and per refusal, the constants, the scan, the effects; coverage checked against the source), records `MUTATION_RUN.json` (3.9) and `MUTATION_RUN.py312.json` (3.12). The Linux-root CI job was **not run**.

## 8. Reproduce (offline)

```
cd <this directory>
/usr/bin/python3 -B seal.py check                          # SEAL_OK
/usr/bin/python3 -B ../core/assemble.py --check .          # BUILD_EQUAL
/usr/bin/python3 -B -m pytest -p no:cacheprovider -q tests  # and with the 3.12 interpreter
HOSTOPS_MUTATION_WORKERS=4 /usr/bin/python3 -B mutation/mutate.py run
HOSTOPS_MUTATION_PYTHON=<3.12> HOSTOPS_MUTATION_RECORD=MUTATION_RUN.py312.json /usr/bin/python3 -B mutation/mutate.py run
```

## 9. What the first mutation run changed

The first complete run (3.9, 237 mutants) left 11 survivors. Three were checks implied by another check, now removed with their mutants: `values[name]!='/'` (the host-path grammar needs a character after `/`), `network.startswith('container:')` (`:` fails the network grammar), and HOSTOPS01's `if own&set(seen): TEMPORARY_NAME_OCCUPIED` (an acknowledged leftover cannot carry this run's own temporary name: the name is keyed by the GO hash, which covers the acknowledgement). One mutant was equivalent (a space in the host-path grammar, refused by `clean_path`) and is replaced by one the tests kill (`=`). Seven were missing tests, now written: a producer of the same size with one byte changed; a producer whose read object is not the lstat'ed one; a precheck refusal keeping its code with little time left; a leftover acknowledged with another identity; a temporary that cannot be removed stopping the run; the success criterion; the receipt reductions.

## 10. Revision 2: Codex's answer to Q-1 and Q-2 (#429 5986698996)

No byte of the source, the build or the tests changed; only this section was added and the seal rewritten. Revision 1 is kept unchanged beside this directory (`../reader_units.rev1-7b08f933/`).

- **Q-1, accepted by name. Residual, recorded explicitly:** the reader's bind of the data volume `/mnt/day-d-data` (owned by uid 1000) does **not** meet decision 6 (#429 5985748037 item 6: every bind source and its ancestors root-controlled). Codex accepts it for this epoch by name, read-only only, and only for two uses: the M1 release file (`C3PO_R2D2_V2_SHADOW_RELEASE_FILE`, installed by K10 under `/mnt/day-d-data/r2d2-v2-release-20261005/`) and the raw microstructure directory (`C3PO_R2D2_MICROSTRUCTURE_RAW_DIR`). The bind in these units is `--mount type=bind,source=/mnt/day-d-data,target=/app/day-d-data,readonly`. What stays open: a non-root writer of the volume could replace what the reader reads through this bind between the checks at activation and the reads (K13 walks the release chain and hashes the release file; nothing re-checks the raw microstructure tree). Any other use of the data-volume bind is outside this acceptance.
- **Q-2, confirmed:** `CONTAINER_SOURCE_ROOT=/c3po-source`, bound read-only from `/var/lib/c3po/r2d2-v2-source-20261005`, a source on a root-only chain.
- Q-3 to Q-6 remain open.
