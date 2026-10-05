# K8 — the eve delivery E6 (hostops02 write family `k8_eve`), epoch R2D2-V2-SHADOW-2026-10-05

Fable, 2026-10-04 (UTC by command at the start of the work: 21:10Z = 18:10 BRT). Offline only: no host, no network, no GitHub, no push, no docker. Nothing in this directory was run on the host, bound, signed or reviewed by anyone but its author. Every hash below was taken by command.

`W` = the shared work directory (this family's grandparent: `W/fable-k8-20261004/k8_eve`); `S` = the author's session scratchpad, where the opsart checkout and the extracted release tree were read (not part of this family); `core` = `W/hostops02-sealed/core` (generation `4c24c5cf…d0d6`, read, never edited); `DOC:`/`CAP:` = `S/opsart/c3po/deployment/capacity-day/README.documents.md` / `README.md`; `NOTE` = the K9 interface note.

## 0. What E6 is, from the sources

| Source (sha256 by command) | What it fixes for K8 |
|---|---|
| `W/fable-epoch03-masterplan-20261002/MASTER_PLAN.md` (`b3cf9540…cf2b`), rows E6, C#23 | "Eve delivery: thirteen signed files and the payload file assembled on the host", one WF operation, BUILD K8, after the commitment, one UTC day; "the thirteen files travel in the payload bytes, their hashes in the signed request" |
| ORD:16 (`ORDEM_EPOCA_03.rev2.md`, `1a5253bf…a118`) | "Os documentos do dia (contrato, registro do template do dia, GOs, registro de publicação e, de cada janela, a configuração e a visão de veto) são entregues na véspera; o arquivo de payload do dia é montado no servidor, na mesma entrega, a partir da lista causal confirmada, com recibo sem símbolos" |
| DOC "What the tool writes", "The payload file" (`d1628d08…03df`) | the roots of each file; the payload `session=<day>.json` = `{"contract","causal"}`; the delivery must refuse unless the list's hashes equal the contract's `causal_scope` and the contract bytes are the signed ones; its receipt carries no symbol |
| CAP "What the host payload must provide" (`1c8485aa…4f94`) | the capacity tree is bound read-only at `/c3po-capacity`; the AnchoredRoot identities pin device and inode of every component |
| NOTE §5.7 rule 9, §10.5 (`ab5159be…96c`, pinned by the signed Act B `ab241993…aaaf`) | E6 follows `commit_result`; K8 reads `Dd/causal/commitment.private.json` by fixed path and checks it against the commit receipt; E6 band 17:38–20:55 BRT (A2-18 for later) |
| `W/codex-n8-placement-20261004.txt` (`d30f7f90…2c53`) | `k9_root=/var/lib/c3po/r2d2-v2-k9-20261005`, a chain controlled by root alone |
| Codex decision 6 (#429 comment 5985748037, relayed by the coordinator; not read here) | every bind source / written path and all its ancestors root-controlled: no open root, no uid-1000 ancestor, gid 0, no setgid; the K9 day directory `/var/lib/c3po/r2d2-v2-k9-20261005/days/<D>`. K8 complies as built: the signed rows `/ → …/days` are validated with no open root, uid 0, gid 0, no group/other write, no setgid (`validate_plan`); every directory K8 holds below them (`days/<D>`, `causal`, `receipts`) and every directory it writes into (`/var/lib/c3po-capacity` and its four roots, ancestors `/`, `/var`, `/var/lib` = the first three signed rows) must be 0:0 mode exactly 0700 (no setgid). K8 does not touch the epoch source root |
| provisioning request `beb45945…a510` (`W/once-e2-20261003-b`, receipt KNOWN_COMPLETE, 03/10 16:42Z) | `/var/lib/c3po-capacity` and its roots `config documents payload go`, root:root 0700, on the root filesystem (`/var/lib` device 66306) |
| draft `W/fable-k9runner-20261004/k9_runner.py` (in progress by another session; `b5950b99…fc40` when last read) and K9R's DESIGN §5 (`6677312f…2796`) | what the commit step leaves: `causal/commitment.private.json` = canonical(`build()['commitment']`), `causal/build_audit_receipt.json` = canonical(`build()['audit_receipt']`), both 0600, directories 0700, and `receipts/commit_launch.RECEIPT.json` (`K9_STEP_RECEIPT_V1`, 16 members) naming both by sha256 under `outputs` |
| release tree dd4ec4bb (`S/docs03/recert03/export/dd4ec4bb.tar`, `61bf5dd5…7660`) | `r2d2_v2_capacity_wiring.py:27-37` reads `payload/session=<day>.json` (keys exactly `contract`,`causal`) and `go/session=<day>.admission.json`; `r2d2_v2_capacity_authority.py:44-60` binds `causal_scope` to `causal` and `list_sha256 == digest(symbols)`; `r2d2_v2_capacity_anchored.py:36-50` reads a root file only if regular, owned by the effective uid, one link, no group/other bit, ≤ 4 MiB; `r2d2_v2_causal_emitter.py:213-251` `build` returns `{commitment, audit_receipt}`; `r2d2_v2_store.py:21-27` canonical/digest |

### The thirteen signed files (real tool output, `capacity_day_documents.py` `888a48e6…d183`, `layout()`)

With three windows (A2: J1, J2, J3; D4 `PRE_DELIVERED`, ORD:17 "pré-emitido e entregue na véspera"):

| # | Key | Root | Name |
|---|---|---|---|
| 1 | `template` | documents | `session=<D>.template.md` |
| 2 | `go_admission_record` | documents | `session=<D>.go-admission.md` |
| 3 | `go_bar_manifest_record` | documents | `session=<D>.go-bar_manifest.md` |
| 4 | `publication_bar_manifest` | documents | `session=<D>.publication-bar_manifest.md` |
| 5–7 | `veto_view:<w>` | documents | `session=<D>.view-<w>.md` |
| 8 | `go_admission` | go | `session=<D>.admission.json` |
| 9 | `go_bar_manifest` | go | `session=<D>.bar_manifest.json` |
| 10–12 | `capacity_config:<w>` | config | `session=<D>.<w>.capacity.json` |
| 13 | `contract` | — | not written as a file: it has no root, the loader never reads it; it is carried **whole** (its canonical bytes) into the payload file |
| + | payload | payload | `session=<D>.json` = canonical `{"contract": <13>, "causal": {epoch, session, status "AVAILABLE", symbols, list_sha256, commitment_sha256}}`, assembled on the host |

Measured on the synthetic fixture: the thirteen signed files are 30,876 bytes; the bound request is 49,185 bytes (< 65,536). With one or two windows the set is 9 or 11 signed files; the source accepts 1 to 3 windows (`K8_MAX_WINDOWS`), the signer sees which in the effects.

### Signed vs taken from the commitment

- **Signed (bytes in the request, sha256 and size in the authority and GO effects):** the twelve files and the contract. Also signed: the day, the window names, the K9 days chain rows, the identity rule, the evidence boot.
- **Taken on the host, by fixed path, from what the day's K9 commit step left:** the ordered list (`commitment.list`), and from it `list_sha256 = sha256(canonical(list))` and `commitment_sha256 = sha256(commitment file bytes)` (the file is canonical, so this equals `digest(commitment)`). They are accepted only if (a) the commit receipt is COMPLETE, of this epoch/day/phase/operation/Act B key/package/revision, and names both files by sha256; (b) both files' bytes have those hashes; (c) the commitment is of this epoch and day, its list is ≤ 550 distinct names of the producer grammar `[A-Z0-9][A-Z0-9.-]{0,19}` and carries its own digest; (d) its digest and its list's digest are the signed contract's `causal_scope`; (e) the audit receipt is the build event of exactly this commitment. **The payload file's hash is never signed and never reported**: it is a commitment to the list (CAP:332); the signers see its path, mode and shape only.

## 1. The family

`spec.py` (`STEM HOSTOPS02_K8_EVE_DELIVERY`, parts `core parents files`), `op.py`, `build/` (written by `core/assemble.py`, never edited), `tests/`, `mutation/`, `seal.py`, `CONTRACT.txt` (what a signer and a binder use), `VALIDATION.json` and `SHA256SUMS` (written by `seal.py`).

| | |
|---|---|
| `OPERATION` | `GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01` |
| `WRITES_ALLOWED` / `ACTIVATION_ALLOWED` | True / False |
| `DATE_CLASS` | `WRITE_SESSIONS` (10-05 … 10-10 UTC); the eve band is judged by `perform` (§3) |
| `MAX_GATE_SPAN_SECONDS` | 900 |
| `EVIDENCE_OPERATIONS` | `GO_READONLY_HOSTOPS02_K9_PHASE_READ_01` (the K9R TREE read of the same boot supplies the rows `/ → …/days`) |
| Success | `METADATA_ONLY_REQUIRES_REVIEW` / `EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK`, exit 0 |
| Plan members | `day`, `windows`, `contract`, `files`, `days_parent`, `identity_rule`, `evidence_boot_id_sha256` |

**The one copy from the core.** The core's `create_file` admits only `FILE_NAME = [A-Za-z0-9][A-Za-z0-9._-]{0,127}`, which has no `=`, and every name the loader reads has one. The core is frozen and rule 12 forbids rebinding its names, so `op.py` carries `k8_create_file`: the core's function with three mechanical changes (name and docstring; `k8_named_in` for `named_in`; nine locals prefixed `k8`), produced by `tests/k8copy.py` and compared byte for byte with the core's text by `tests/test_k8_copy.py`. `k8_named_in` admits only `session=2026-10-0[6-9].<suffix>` names. The core's 29 mutants of `create_file` are ported to the copy (`mutation/mutants.py`, `K*`), plus one for the name rule. Everything else (`remove_own_temporary`, `readback_file`, `Pinned`, `walk_pinned`, `read_regular`, `free_bytes`, `mutate`, `seal`) is the core's, unchanged.

## 2. What `perform` does, in order

Pure, before the first gate: decode and judge the signed bytes (`k8_delivery`, also run by `validate_plan` so a bad request never spends a GO): day ∈ {10-06…10-09}; 1–3 distinct window names; exactly the layout's keys; each file strict base64 of bytes with the signed sha256 and size; total ≤ 40,960 bytes; the contract canonical JSON with its seven keys and a `causal_scope` of this epoch and day; every window's config canonical, pinning the day's four records (name and sha256) and its own view (`veto_views == {D: …}`), all windows pinning the same seven chain documents and the same three roots at `/c3po-capacity/<root>`; both GO files `{"go": …}` of this epoch, day and phase.

Then, everything looked at before the first creation (any refusal here leaves the host untouched; tested for every code):

1. executor 0:0 (`EXECUTOR_IDENTITY`); the window inside `[D−1 20:00Z, D 09:00Z]` (`WINDOW_NOT_IN_THE_EVE_OF_THE_DAY`; before any host call); umask 077; boot (`EVIDENCE_FROM_EARLIER_BOOT`).
2. walk the signed rows `/ → /var/lib/c3po/r2d2-v2-k9-20261005/days` (no open root; uid 0, gid 0, no group/other write, no setgid on any row, else refused in `validate_plan`), and `/ → /var/lib` (the first three rows).
3. hold `/var/lib/c3po-capacity` and its four roots: each a real directory, 0:0, mode exactly 0700, opened `O_NOFOLLOW` by the held parent, the descriptor the object the lstat saw (`CAPACITY_DIRECTORY_ABSENT / _NOT_PRIVATE / _CHANGED_DURING_PRECHECK`).
4. hold `days/<D>`, `receipts`, `causal` the same way (`K9_DIRECTORY_*`).
5. read the commit receipt (≤ 256 KiB), the commitment (≤ 64 MiB) and the audit receipt (≤ 64 KiB): each regular, 0:0, 0600, one link, unchanged during the read (`COMMIT_RECEIPT_ABSENT`, `COMMITMENT_ABSENT`, `K9_FILE_NOT_PRIVATE`, `FILE_CHANGED_DURING_READ`); judge them (`COMMIT_RECEIPT_INVALID / _NOT_COMPLETE / _NOT_OF_THIS_STEP / _NOT_OF_THIS_PACKAGE / _WITHOUT_THE_COMMITMENT`, `COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT`, `COMMITMENT_INVALID`, `COMMITMENT_NOT_OF_THIS_DAY`, `COMMITMENT_LIST_INVALID`, `COMMITMENT_NOT_THE_CONTRACT_SCOPE`, `LIST_NOT_THE_CONTRACT_SCOPE`, `AUDIT_RECEIPT_NOT_BOUND`); assemble the payload bytes in memory.
6. read the seven chain documents the configs pin from `documents` (B5 delivered them): present, private, the pinned bytes (`CHAIN_DOCUMENT_ABSENT / _NOT_PRIVATE / _NOT_AS_PINNED`).
7. every one of the 13 destination names absent (all looked at; one refusal `DESTINATION_PRESENT` listing the keys).
8. the three root identities: `sha256(canonical([["c3po-capacity",dev,ino],[root,dev,ino]]))` with the host's numbers, compared with what the configs pin. Recorded per root; refused (`CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG`) only under the signed rule `REFUSE_ON_MISMATCH` (§6, Q-3).
9. free bytes on the tree's filesystem ≥ 4 MiB (`CAPACITY_FREE_SPACE_BELOW_FLOOR`); ≥ 15 s left (`BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT`).

Effects: 13 exclusive creations, in the order of the table (documents, go, config, payload last), each by `k8_create_file` into its held root, 0600; then every file read back by descriptor and every held directory proved again (the capacity root's proof walks the signed rows to `/var/lib`, the day directory's the rows to `days`). A failure stops the run; REFUSED only while nothing succeeded (the core's rule), otherwise PARTIAL.

**What a later read finds** (tested at every host call: `classify` in `tests/k8.py`): `F<n>` = the first n files of the order delivered, possibly `F<n>_TEMPORARY` (the next file's temporary alone) or `F<n>_LINKED` (the last file still has its temporary as a second name). The states only move forward and every one is reached.

**There is no second attempt and no repair in the family.** A day with any of its names present is refused (`DESTINATION_PRESENT`); a partial delivery leaves that day without capacity documents (the writer refuses), the session runs without bars (ORD:16), and removing the leftovers is not built (like C2/C3 of the master plan).

## 3. Windows, dates, budget, size

- A2 rev3 E6 band: 17:38–20:55 BRT of the eve (20:38–23:55Z, UTC day D−1); with Codex's "yes" on A2-18 also 00:00–05:55 BRT (03:00–08:55Z of D). K8 accepts `[D−1 20:00Z, D 09:00Z]` (17:00 BRT eve to 06:00 BRT of D), before D0 (07:26) and J1 (07:38); the binder narrows it to the signed band. A window never crosses 21:00 BRT (the core's rule).
- Earliest use: the Tuesday 06/10 eve (Monday 05/10 evening) at the earliest, after `commit_result` (G18 ≈ 19:10, G19 ≈ 20:10 BRT; NOTE §5.7 rule 9). Monday 05/10 has no K9 list and no E6 (`DAY_INVALID` for 10-05).
- Budget: no command is started; 13 files of ≤ 18 KB plus one readback each; the precheck reads and parses up to 64 MiB of commitment. Measured on the workstation only: a synthetic 40,001,497-byte commitment parsed, re-serialized and hashed in 0.63 s. The real commitment carries base64 of the registry and of the daily contract; its size on the host is unmeasured (Q-6).
- Size: the 40,960-byte limit keeps the bound request below 65,536 (tested: the largest admissible delivery gives a request ≤ 63,488 bytes).

## 4. The receipt

Carries: per signed file path, sha256, size, mode, owner, links; the contract's sha256; for the payload file only path, mode, owner, links and booleans (`bytes_equal_the_assembled_bytes`, `hash_and_size_withheld`); `causal`: three booleans incl. `list_empty` (D12: an empty committed list is delivered; the writer then ends `MANIFEST_SYMBOLS_EMPTY`, terminal for the day); the three identity booleans and the rule; the precheck rows (metadata only). Never: a symbol, a count of the list, the payload file's hash or size (its ledger row has `bytes`, `sha256_signed`, `sha256_observed` set to null and `hash_and_size_withheld` true), the audit receipt's hash. The commitment's digest appears only as the contract's public `causal_scope` in the effects. Tested on the four-name and the 550-name days.

## 5. What the tests do (synthetic only)

`tests/fixtures/DAY_SETS.json` was made by `tests/make_fixtures.py` with the backend venv of the opsart checkout: the real `capacity_day_documents.py` over synthetic inputs (the helpers of its own test file: synthetic chain, synthetic hashes), roots pinned to the emulated host's inodes, three days: 2026-10-06 (four synthetic names), 2026-10-07 (550 synthetic names), 2026-10-08 (empty list). Deterministic (two runs byte-identical). Suites: `test_conformance.py` (the core's 121), `test_k8_eve.py` (emulated host: literal effects, three days, one/two windows, every precheck refusal with an untouched host, every plan refusal before any claim, hostile states after the precheck, death at every host call, expiry at every gate, escape, second request), `test_k8_copy.py` (the copy equals the derivation; the name rule), `test_native.py` (the source's own Native with real syscalls on a temporary tree: the exact calls, refusals that leave the real tree as it was, a real race, real process deaths at six points). Counts and both interpreters: `VALIDATION.json`.

## 6. Deviations from the sources, and why

1. **The contract is not written as a file of its own.** ORD:16 lists it among the documents "entregues na véspera"; DOC says it "goes to the host delivery, which assembles the payload file from it". No root holds it and nothing reads it; it is delivered as the `contract` member of the payload file, byte for byte. If Codex wants it also as a file, a fifth location must be named (Q-1).
2. **K8 copies one core function** (`create_file` → `k8_create_file`) because the frozen core cannot create a name with `=` (§1). The copy is mechanical and pinned by a test; no new core generation.
3. **The commitment file is the bare commitment, not `{commitment, audit_receipt}`**: NOTE §3.3 says "the confirmed commitment as `build` returned it"; the draft runner writes `build()['commitment']` and the audit receipt beside it. K8 follows the runner and checks both (Q-2).
4. **Evidence is the K9R TREE read**, not hostops01's PRECHECK: TREE is the same-boot read on the eves that signs `/ → …/days` (it contains `/var/lib`). The capacity tree's own rows are not signed: K8 holds them by name with exact owner/mode and compares the configs' AnchoredRoot identities (Q-3, Q-4).
5. **No PAYLOAD_TOO_LARGE refusal**: the bound (40,960 + 550 × ≤ 23 bytes) is far below `MAX_FILE_BYTES` and the copy refuses above it anyway.

## 7. Open questions for Codex

- **Q-1** Contract as its own file (deviation 1): enough inside the payload file, or a named location?
- **Q-2** Commitment file format (deviation 3) and the receipt member set: K8 requires exactly the 16 members K9R requires and both `outputs` keys; the runner and K9R must keep them.
- **Q-3** Identity rule: is the host-side AnchoredRoot identity (`[["c3po-capacity",dev,ino],[root,dev,ino]]` with the host's numbers) equal to the one A5/IDENT printed in the container (bind mount shows the source's device and inode)? If A5's numbers are on record and equal, sign `REFUSE_ON_MISMATCH`; otherwise `REPORT_ONLY` and read the booleans.
- **Q-4** Which read signs the rows: K9R TREE's `days` chain of the same boot. If Codex prefers the capacity tree's rows signed too, a read must print them (none does today).
- **Q-5** The day's contract hash must equal `documentary.contract_sha256` of each window's REQUEST (DOC:9, 237); that is a binder rule (K8 signs the contract bytes; K12's envelope names the same hash). Not built.
- **Q-6** Real commitment size (registry and daily contract in base64): read and parsed in memory within the 60 s budget; unmeasured on the host.
- **Q-7** A2-18 (E6 after 21:00 BRT): K8 accepts until 06:00 BRT of D; the band is the binder's.
- **Q-8** No recovery: a PARTIAL E6 loses that day's capacity documents (names occupied). Is that acceptable, or is a reconciliation/removal source wanted (unbuilt)?

## 8. Proven, emulated, unproven

- Real on the workstation (macOS, ordinary user reported as root): open/write/fsync/link/unlink by `dir_fd` with `O_EXCL|O_NOFOLLOW` on `=` names, reads `O_NOFOLLOW`, a real race at the final name, real process deaths.
- Emulated only: uid 0, device numbers, every errno injection.
- **Unproven:** the Linux-root CI job with this directory (not run); real host paths and owners; real K9 runner output; bind-mount identity equality (Q-3); real commitment size (Q-6). Not reviewed by Codex. Not bound.

## 9. Reproduce

```
cd W/fable-k8-20261004
/usr/bin/python3 -B core/assemble.py --check k8_eve            # BUILD_EQUAL
cd k8_eve
/usr/bin/python3 -B seal.py check                               # SEAL_OK
/usr/bin/python3 -B -m pytest -p no:cacheprovider -q --basetemp ../k8_eve.work/t tests     # and with W/night23-test-venv/bin/python
/usr/bin/python3 -B mutation/mutate.py check                    # anchors
HOSTOPS_MUTATION_PYTHON=<python> HOSTOPS_MUTATION_RECORD=<record> /usr/bin/python3 -B mutation/mutate.py run
```
