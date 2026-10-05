# K4 modes CHAIN_STATIC, PINS, LAUNCHER and WRITER — private, non-secret deliveries (HOSTOPS02, `k4_files`), candidate revision 1

Offline work only (2026-10-04/05). Nothing here was run on the host, pushed, bound or reviewed by anyone but its author. Hashes and counts are in `VALIDATION.json` and `SHA256SUMS`, written by `seal.py`; where this text and those files differ, the files prevail.
Built on the frozen core, generation `4c24c5cf…d0d6` (`../core`, a symbolic link to `W/hostops02-sealed/core`; read, never edited). Pattern: `W/fable-k4e0-20261004/k4_e0` (K4 mode E0, revision 2) and `W/hostops02-sealed/install_release` (K10).

Abbreviations. `W` = the work directory (the parent of this deliverable, `../..` from this file); `S/opsart` = a checkout of the operations repository at 4a6f767 (the session's scratch copy; tests read it only through `HOSTOPS02_TEST_OPSART_DIRECTORY`). `PLAN` = `W/fable-epoch03-masterplan-20261002/MASTER_PLAN.md`. `RDR` = `S/opsart/c3po/deployment/reader/README.md`. `CAP`/`DOC` = `S/opsart/c3po/deployment/capacity-day/README.md` / `README.documents.md`. `A2` = `W/fable-a2-draft-20261003-rev3/A2_AUTORIDADE_CINCO_SESSOES.md`. `E2` = `W/once-e2-20261003-b/PARAMETERS.json` (provisioning, KNOWN_COMPLETE 2026-10-03). `ACTB` = `W/fable-actb03-20261004` (Act B chain, `reports/VERIFY_FULL.json` = `VERIFY_PASS`, no stand-in).

---

## 0. What it is

One source, `GO_WRITE_HOSTOPS02_K4_FILES_01`, with three **signed modes**; each request carries exactly one (`plan.mode`) and the effects the owner signs name it:

| Mode | Plan row | Creates | Bytes from |
|---|---|---|---|
| `CHAIN_STATIC` | B5 (ORD:22 "entrega única dos documentos da cadeia e da configuração estática de capacidade") | 7 files in `/var/lib/c3po-capacity/documents` (the chain documents, under the names of `chain_pins`) and `week.static.capacity.json` in `/var/lib/c3po-capacity/config` | the chain documents are **compiled into the source** (base64 constants written by `chain_block.py` from ACTB); the static config travels in the request (hash and size signed) |
| `PINS` | B6 (ORD:22 "criação do arquivo de pinos do leitor") | `/etc/c3po-reader/pins.env`, the twelve lines of RDR, rendered by the source from twelve signed values | the values of the request |
| `WRITER` | K12's prerequisite (PLAN C#29; K12 Q4) | `/var/lib/c3po-capacity/config/manifest_writer-<sha256>.py` (0600) | **compiled into the source** (46,977 bytes, sha256 `aeda5b12…d387` = the hash the capacity-day README names; base64 would not fit a signed document); the request signs the hash, which must equal the compiled one |
| `LAUNCHER` | A8 (A1 E6) | `/etc/c3po-reader/launcher/` (0700) and in it `reader_launcher.py` | the request (hash and size signed); reviewed by hash per ORD:31 |

Every file root:root 0600, every directory root:root 0700, created by the core's `files` part (exclusive temporary, unbuffered writes, fsync, exact metadata, `link` to the final name — never replaces —, removal of the temporary proved by identity), relative to a held descriptor of a parent walked from `/` against signed rows, then read back by descriptor inside the run. No process, no secret, no container, no activation, nothing that exists is changed.

## 1. Why one source with three modes, and not three siblings (the choice asked for)

- PLAN:330 defines K4 as "Private deliveries, **modes** LAUNCHER, CHAIN_STATIC, PINS, later WRITER and E0. Exclusive creation, fsync, readback by descriptor". The three share everything that matters for review: parts (`core parents files`), the creation discipline, the precheck shape, the date class, the flags (`WRITES_ALLOWED` true, `ACTIVATION_ALLOWED` false). Three copies of the same ~300 lines would triple the review and the mutation surface for no separation the signature does not already give.
- The separation that §3.2 of PLAN requires (B5 and B6 are two operations, ORD:22) is kept where it is enforced: **each request is one mode, one GO, one owner answer**; the mode is a member of the plan, of the effects of the authority and of the GO; a request of one mode cannot be read as another (`DELIVERY_INVALID`: each mode has its own closed key set, tested).
- C#20 ("no source mixes read and write modes, or tier 0 and tier 1 modes") holds: the three are writes of tier 1.
- E0 stays its own sibling (`W/fable-k4e0-20261004/k4_e0`, rev 2), as sealed: a once-per-epoch root creation under another chain (K9 tree, N-8) whose review is separate and already in progress; nothing in it is reopened.
- **Cost of the choice, stated:** a defect found in one mode after the others were signed changes the payload hash of all three. The modes run in the order B5 → A8 → B6 (B6 reads what B5 and A8 delivered); a defect found in PINS after B5 and A8 ran costs only a new review and a new PINS request, because the earlier receipts stay valid evidence of what is on the host (PINS compares the *bytes on the host* with hashes it signs, not the hash of the source that delivered them).

## 2. What the sources of truth ask, and where each answer lives

| Ask | Source | Here |
|---|---|---|
| B5: seven chain documents and `week.static.capacity.json` | PLAN:184; A2 B5; DOC "What the tool writes", "The static config" | CHAIN_STATIC; names = DOC `chain_pins` / ACTB `CHAIN_NAMES`; config name = DOC `static-config` output |
| The static config pins the seven chain documents, one TEMPLATE, one view | DOC "The static config"; `capacity_day_documents.py` `capacity_config`, `CONFIG_KEYS` | `static_config_of()`: canonical JSON, exactly `CONFIG_KEYS`, schema `R2D2_CAPACITY_BOOTSTRAP_V3`, veto mode, this epoch's identity (exactly the six keys of `validate_identity`, both order hashes 64-hex), the approved release `fc2f64ea…` and package `b5ce527a…`, **the seven pins equal to the compiled documents (file and hash)**, one TEMPLATE pin and one view pin of the same session day, the three roots at `/c3po-capacity/<name>` with a 64-hex identity |
| B6: `pins.env`, twelve names in this order; grammar | RDR "Environment files" item 2 and "Operations 3" | `PINS_NAMES` (test compares with RDR's block), `pins_lines()`: constants (build revision `dd4ec4bb…`, release `fc2f64ea…`, raw dir, `true`, `DISPATCH_AND_DERIVATION_ONLY`, `1.0`), paths `^/[A-Za-z0-9._=/-]+$` with no empty/`.`/`..` component under `/app/day-d-data` (release file two components below; the source dir: section 13), journal `^/c3po-[a-z0-9][a-z0-9-]*$` and not `/c3po-capacity`/`/c3po-reader`, config file exactly `/c3po-capacity/config/week.static.capacity.json`, the two hashes 64-hex, distinct from each other and from the release |
| B6 guards: journal = producer's container journal root and the reader's journal bind target; config hash = SHA-256 of the delivered file; launcher hash = SHA-256 of the installed launcher | RDR "Operations 3" | precheck reads, through signed chains, the static config (0:0 0600 1 link, hash = `C3PO_R2D2_V2_CAPACITY_CONFIG_SHA`, and judged again exactly as CHAIN_STATIC judges it), the launcher directory (0:0 0700, held) and file (0:0 0600 1 link, hash = `C3PO_READER_LAUNCHER_SHA256`), both units in `/etc/systemd/system` (0:0 0644 1 link, hashes signed in the plan), and checks in the unit texts (only command lines: a line beginning with two spaces and ending in ` \`, so a comment cannot satisfy it): one `--mount type=bind,source=S,target=J \` in the producer and one `…,target=J,readonly \` in the reader **with the same S**, exactly one `--journal-root`, equal to `J`, in the producer, and the reader binding `/var/lib/c3po-capacity` at `/c3po-capacity,readonly` and `/etc/c3po-reader/launcher` at `/c3po-reader,readonly` |
| A8: launcher directory 0700 and file 0600 by exclusive creation, under an authorisation that carries its SHA-256 | RDR "The launcher file"; PLAN:182 | LAUNCHER (section 6 for what an existing directory means) |
| K4: exclusive creation, fsync, readback by descriptor | PLAN:330 | the core's `create_directory`, `create_file`, `readback_file`, `readback_directory` |
| A2 bands: Sunday 04/10 13:26–20:30 BRT; Mon–Thu 17:38–20:30 BRT | A2 B5, B6 | `WRITE_EPOCH` (10-03 … 10-10 UTC): the narrowest core class that holds 10-04 and the session evenings; the band is the binder's and the signer's |

## 3. Placement

```
READER_CONFIG_DIRECTORY='/etc/c3po-reader'   CAPACITY_ROOT='/var/lib/c3po-capacity'   UNIT_DIRECTORY='/etc/systemd/system'
```
Three lines of `op.py`; every other path derives from them (tested: each literal occurs once). They are the paths E2 created (root:root 0700: `/etc/c3po-reader`, `/etc/c3po-reader/docker-cli`, `/var/lib/c3po-capacity/{config,documents,payload,go}`) and the paths RDR names. E2 did **not** create `/etc/c3po-reader/launcher` (RDR's operation 1 lists it; E2's table does not): LAUNCHER creates it.

All chains are judged with **no open root**: every component uid 0, not writable by group or other, gid 0, no setgid anywhere (`CHAIN_NOT_ROOT_CONTROLLED`), the receiving parent exactly 0:0 0700 (`PARENT_NOT_ROOT_0700`). The unit directory chain is judged the same way except its leaf mode (0755 on the host).

## 4. Effects, in order (emulated counts in VALIDATION.json and the tests)

- CHAIN_STATIC: 8 × (create temporary, write, link, unlink), 32 mutating calls; the documents root and the config root keep their earlier entries (counted in the precheck: `entries_before`) and gain exactly 7 and 1 (`entries_after`, read back).
- PINS: 1 × (create, write, link, unlink).
- LAUNCHER: mkdir, then 1 × (create, write, link, unlink); the directory is read back with exactly one entry.
The core's index of each file in a run makes each temporary name distinct (`.hostops-<go16>-<n>.partial`).

## 5. Refusals

From the bytes (`validate_plan`, also run by the dispatcher before any claim): `MODE_INVALID`, `DELIVERY_INVALID`, `EVIDENCE_BOOT_UNBOUND`, the chain codes (`CHAIN_ROW_INVALID`, `CHAIN_ROW_UNSAFE`, `PARENT_SETGID`, `CHAIN_NOT_ROOT_CONTROLLED`, `PARENT_NOT_ROOT_0700`, `CAPACITY_CHAIN_DIVERGES`), `STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH`, `STATIC_CONFIG_INVALID|IDENTITY|RELEASE|CHAIN_PINS|ANCHOR|ROOTS`, `PINS_VALUES_INVALID`, `PINS_CONSTANT_MISMATCH`, `PINS_RELEASE_FILE`, `PINS_SOURCE_DIR`, `PINS_JOURNAL_DIR`, `PINS_CONFIG_FILE`, `PINS_HASH_INVALID`, `PINS_HASH_REUSED`, `PINS_BYTES_NOT_THE_SIGNED_HASH`, `UNIT_HASH_INVALID`, `LAUNCHER_BYTES_NOT_THE_SIGNED_HASH`, `CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH`.

On the host, before the first effect (nothing changed): `EXECUTOR_IDENTITY` → `EVIDENCE_FROM_EARLIER_BOOT`/`BOOT_ID_INVALID` → the walks (`PARENT_*`, `NOATIME_UNAVAILABLE`) → per mode: `CHAIN_DOCUMENT_PRESENT`, `STATIC_CONFIG_PRESENT` | `PINS_ENV_PRESENT`, `LAUNCHER_DIRECTORY_{ABSENT,INVALID,CHANGED_DURING_PRECHECK}`, `LAUNCHER_FILE_{ABSENT,METADATA,NOT_THE_SIGNED_BYTES}`, `STATIC_CONFIG_FILE_*`, `PRODUCER_UNIT_*`, `READER_UNIT_*`, `JOURNAL_BIND_MISMATCH`, `READER_UNIT_MOUNTS_MISMATCH` | `LAUNCHER_DIRECTORY_PRESENT` → `FREE_SPACE_BELOW_FLOOR`/`STATVFS_INVALID` → `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` (15 s). A failure of any other kind: `PRECHECK_OS_ERROR` / `PRECHECK_FAILED` (constant codes; no exception text leaves).

After the first effect: REFUSED only while no mutating call succeeded and none is uncertain; otherwise PARTIAL with the ledger; the first file that is not `INSTALLED_DURABLE` stops the run. A temporary the run created and withdrew still makes the run PARTIAL (a create succeeded); `objects_left_by_this_run` then says 0.

## 6. Crash points, second attempts, continuation (revised after the independent read)

A death at every host call (each mode) leaves either nothing (REFUSED) or a prefix of the files, each final name holding exactly the signed bytes, plus at most one temporary of the step that died (tested emulated at every call and natively at four points).

**Continuation.** The first revision refused any target name that existed, which made a PARTIAL B5 or A8 unrecoverable for the epoch: the chain documents' names are fixed by `chain_pins`, and an empty `launcher/` left by a failed file blocked A8 for good (finding 1 of the independent read). Revision 1 as sealed accepts, for every target, a name that is **a regular file, root:root 0600, one link, holding exactly the bytes this run would write** (`PRESENT_EQUAL`: read through the held parent, compared in memory, read back again at the end like a created file); it creates only the missing files; anything else at a target name is the refusal (`CHAIN_DOCUMENT_PRESENT`, `STATIC_CONFIG_PRESENT`, `PINS_ENV_PRESENT`, `LAUNCHER_DIRECTORY_PRESENT`, `LAUNCHER_DIRECTORY_PRESENT_INVALID`). For LAUNCHER an existing `launcher/` is used only if it is root:root 0700, not a link, and holds nothing or exactly the signed file. Nothing that exists is ever replaced; a leftover `.hostops-*.partial` stays and is counted. A second request of the same bytes after a complete run therefore completes with zero mutating calls and says so per file (`created_by_this_run`), instead of refusing. **This is a deviation from PLAN:182 ("exists: refusal") and from PLAN:184 ("a torn file cannot be replaced"); nothing torn is ever accepted (the bytes must be equal), and the owner signs each request anyway.** It is Q-K4-3 for Codex.

## 7. What is signed

`SCOPE`: operation, dates, statement, core generation, flags, epoch, the three modes, the placement, the seven compiled documents (label, file, SHA-256, size), the static config rules (directory, name, schema, limit, release, package, veto mode), the pins rules (path, names, constants, grammars, what is read before), the launcher rules, `FILES_SCOPE`, evidence operations, file contents read, `processes_started: 0`, `never`, limits. Authority and GO carry `effects_of(plan)`: the mode, every file (path, SHA-256, size, 0600, 0:0, one link, ABSENT), the chains (`chain_effects`), for PINS the twelve values and what must be on the host (static config, launcher, both units by hash, the journal target), for LAUNCHER the directory, the evidence boot, five false flags.

## 8. Deviations from the pattern (K4-E0, K10)

1. Three modes in one source (section 1).
2. **Bytes compiled into the source** (the seven chain documents, 36,380 bytes): they exist, are signed and frozen (ACTB `VERIFY_PASS`), and with the static config they would not fit one signed document (65,536 bytes) as base64. The payload hash therefore pins the chain; `chain_block.py check` rebuilds the block from ACTB by command and a test compares every hash with `DURABLE_SHA256SUMS.20261004T171741Z` and `VERIFY_FULL.json`.
3. Two evidence operations (precheck and provisioning), not one: the rows of `/etc/c3po-reader` and of the capacity tree are in E2's ledger.
4. `WRITE_EPOCH`, not `WRITE_SESSIONS` (A2 allows Sunday 10-04 UTC for B5 and B6).
5. One mutation list (own) plus the dispatcher/launcher rows of the core; no carried list.
6. The static config's own correctness (calendar pin, root identities, TEMPLATE and view hashes) is **not** judged: only its shape, epoch, release, package, chain pins and container root paths. The calendar line and the identities come from A5 (PROBE); the binder takes the config bytes from the documents tool's `static-config` output by command.
7. PINS does not read the release file or the source directory on the host (RDR operation 3 does not ask it; RDR operation 4, the activation, and K11 do).
8. PINS proves its four inputs unchanged after the effects (`stat_signature` of each, kept from the precheck, compared by `lstat` through the held parents before the end: `PINS_INPUT_CHANGED`, PARTIAL), answering finding 2 of the independent read.

## 9. Proven, emulated, unproven

- **Real on the workstation** (`tests/test_native.py`): each mode with the source's own Native (real mkdir/open/write/fsync/link/unlink by dir_fd, `O_EXCL|O_NOFOLLOW`, exact flags and modes, an audit hook showing no process, chmod, chown, rename or socket), real refusals (present names, a symbolic link, a mode change, a second hard link, a wrong boot), real process deaths at four points.
- **Emulated only:** uid 0, device numbers, every errno, every death point.
- **Unproven (set 3, not the author's): the Linux-root CI job** with this directory; the host itself (none of the inputs exists yet: the static config needs A5, the launcher needs ORD:31's proofs, the reader units need B2).

## 10. Open questions

| # | Question | Proposal | Who |
|---|---|---|---|
| Q-K4-1 | Evidence: which receipt signs the rows of `/etc/c3po-reader`, `/var/lib/c3po-capacity/{documents,config}` and `/etc/systemd/system` in the boot of the write? E2's ledger has the created rows; the boot must be the write's | a precheck of the same boot (W1 or hostops01 precheck) plus E2's receipt; the binder needs a rule for this operation | Codex, binder |
| Q-K4-2 | Is checking the static config's chain pins, release, package and container root paths in the source acceptable (a correct config built with other root paths would be refused, nothing changed)? | keep | Codex |
| Q-K4-3 | Continuation over files found equal (section 6) instead of a refusal of any existing name | keep (it is the only recovery of a PARTIAL B5 without a removal operation) | Codex |
| Q-K4-4 | Launcher bytes: which hash is authoritative (OPS-CI recorded hash, ORD:31 proofs)? | bind-time input by command from the reviewed file; ≤ 32,768 bytes (today's candidate 17,717) | Codex, owner |
| Q-K4-5 | The `.hostops-*` temporary of a dead run inside `documents/` is a name the packaged capacity loader never reads, but the documents tool's directory listing would see it | accept, or a removal operation | Codex |
| Q-K4-7 | RDR's operation 2 (unit installation) also writes `launcher/reader_launcher.py`. The hostops01 install_units payload (B2) installs unit files only (E3's plan has two units, no launcher), so A8 and B2 do not collide; if B2 is ever built from RDR's operation 2 as written, it must drop the launcher | keep A8 separate | Fable, Codex |
| Q-K4-6 | A2 B6 lists "units e lançador do leitor instalados (A1, E5 e E6)" as preconditions; PINS checks both by hash on the host; the reader units must exist first (B2, hostops01 install_units, not yet run) | order B5 → A8 → B2 → B6 | Fable, owner |

## 11. Reproduce

```
cd W/fable-k4k3k13-20261004/k4_files
shasum -a 256 -c SHA256SUMS && /usr/bin/python3 -B seal.py check
/usr/bin/python3 -B ../core/assemble.py --check .
/usr/bin/python3 -B chain_block.py check
/usr/bin/python3 -B -m pytest -p no:cacheprovider -q tests          # and W/night23-test-venv/bin/python
/usr/bin/python3 -B mutation/mutate.py check
HOSTOPS_MUTATION_SCRATCH=<scratch> [HOSTOPS_MUTATION_PYTHON=<python> HOSTOPS_MUTATION_RECORD=MUTATION_RUN.py312.json] /usr/bin/python3 -B mutation/mutate.py run
```

## 12. The independent read (2026-10-05) and what changed

One adversarial read by a separate agent (read only) on the first build: no blocker. MAJOR 1 (no recovery from a PARTIAL) → continuation, section 6. Minor 2 (PINS inputs not re-proved) → `PINS_INPUT_CHANGED`. Minor 3 (static config judged more loosely than the packaged loader) → exact identity keys, both order hashes and the three root identities 64-hex (the order hashes' values are not compiled: the release tree at hand, opsart 4a6f767, is not dd4ec4bb and its `DOCUMENT_ORDER_SHA` differs from ACTB's, so a value could not be confirmed by command). Minor 4 → the config file name is fixed and the bytes read on the host are judged again. Minor 5 → unit guards read only command lines, one `--journal-root`. Minor 6 → Q-K4-7. Minor 7 (vacuous test assertions) → fixed. Minor 8 (no seal yet) → sealed at the end.

## 13. Added on 2026-10-05: mode WRITER, and Codex decision 6

**WRITER** (coordinator's scope addition; K12 refuses every run without it). K12 (`W/fable-k12-20261004/DESIGN.md` lines 84-85, 117, 365-366) expects `<config root>/manifest_writer-<writer_sha256>.py`, root 0600, one link, with the REQUEST's hash, run in the container as `python -I -B /c3po-capacity/config/manifest_writer-<sha256>.py`. The writer is 46,977 bytes: its base64 plus the rest of a request exceeds the 65,536 bytes of a signed document (K4-E0 measured 60,811 bytes for a 40,960-byte runner), so the bytes are compiled into this source (the `WRITER BLOCK` of `op.py`, written and checked by `chain_block.py` from `S/opsart/c3po/deployment/capacity-day/manifest_writer.py`, whose hash must appear in that README) and the plan carries `writer_sha256`, which must equal the compiled hash (`WRITER_NOT_THE_COMPILED_HASH`). Same discipline as the other modes: signed, root-only chain of the config root, continuation over an equal file, any other object at the name refuses (`WRITER_PRESENT`), the config root read back with its entry count. **Consequence:** a corrected writer is a new K4 payload (new review), exactly as a corrected writer is a new K12 REQUEST hash. ORD:31 (writer reviewed by hash, smoke-tested) still applies before the WRITER GO.

**Codex decision 6** (`W/codex-six-design-decisions-20261004.txt`, sha256 `4b169599…9c55`, by command; #429 5985748037): every docker bind source and all its ancestors root-controlled; the epoch source root is now `/var/lib/c3po/r2d2-v2-source-20261005`.
- What this family creates or references, checked: the capacity tree (`/`, `/var`, `/var/lib`, `/var/lib/c3po-capacity`, `documents` / `config`), the reader directory and `launcher/` (`/`, `/etc`, `/etc/c3po-reader`, `launcher`), the unit directory: **every one is judged with no open root, uid 0, gid 0, no group/other write, no setgid, the receiving leaf root:root 0700** (`private_chain`), and walked by descriptor. Conform.
- **PINS changed:** `C3PO_R2D2_V2_SHADOW_SOURCE_DIR` is no longer under `/app/day-d-data`; it must be a dedicated top-level container target (`/c3po-<name>`, not `/c3po-capacity`, `/c3po-reader` or the journal target), and the installed reader unit must bind `/var/lib/c3po/r2d2-v2-source-20261005` there **read-only**. PINS signs and walks two more chains: the source root (`source_chain`, root-only, leaf 0700) and the journal host root (`journal_chain`, `/var/lib/c3po-bar/journal`, root-only, leaf 0700), holds them to the end, and requires the journal bind source in both units to be exactly `/var/lib/c3po-bar/journal`.
- **Flagged, not this family's to fix:**
  1. The reader unit template of RDR (`c3po-reader.service`) has no bind of the source root: with it as written, PINS refuses `READER_UNIT_MOUNTS_MISMATCH` (tested against the real template). B2's unit bytes must gain `--mount type=bind,source=/var/lib/c3po/r2d2-v2-source-20261005,target=<SOURCE_DIR>,readonly` (a fifth bind; RDR's "four read-only binds" changes).
  2. The reader unit still binds the **data volume** (`/mnt/day-d-data`, uid 1000) at `/app/day-d-data` for the release file (`C3PO_R2D2_V2_SHADOW_RELEASE_FILE`, installed by K10 at `/mnt/day-d-data/r2d2-v2-release-20261005/…`). That bind source is not root-controlled: **it does not meet decision 6**. Moving the release (K10) and the bind is outside this family; PINS keeps the `/app/day-d-data/<dir>/<file>` grammar until that is decided (Q-K4-8).
  3. K12's dispatch binds the same data volume (CAP "Mounts — exactly four").

| # | Question | Who |
|---|---|---|
| Q-K4-8 | Decision 6 vs the data-volume bind of the release file (reader and K12): move the release under a root-only chain (K10 change) or accept by name? PINS follows whichever path the reader unit binds | Codex, owner |
| Q-K4-9 | The container target of the source root (the tests use `/c3po-source`): a line of the Saturday sheet / B2 render | Fable, Codex |
