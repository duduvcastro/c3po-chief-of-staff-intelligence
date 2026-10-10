# L12-HOST v3.3: changes from v3.2

Fable subagent, Saturday 10/10/2026. Nothing was run on any host; no push, no network, no SSH. Every hash below was
computed by command (`shasum -a 256` / `hashlib`). No symbol and no private content is printed or stored here. This
is not a GO, not a grid election and not a host certification.

## 1. Base

- Byte copy of the sealed v3.2 set `fable-l12host-v32-20261009` (top `SHA256SUMS`
  `ee1b9f39f62079f8008c0ffdd0e0bf3824894858e5d8028484d4fae48ce4e593`, family `l12host/SHA256SUMS`
  `625d244b538e36a270c1d5136dfb87a067a9950eeb4beac35d6505e7eb3cceb7`), both seals verified before the copy: only the
  75 files listed in its top `SHA256SUMS` plus that file. Not copied: `review-tmp/`, `PREV_BUILD_AND_REVIEW_REPORTS.md`,
  `LINUX_DIAG_NOTE.md`. The v3.2 directory, the lots-patch directory and the aborted v3.3 directory were only read.
- Merged: the reviewed lots patch `fable-l12host-lots-patch-20261010` (its `SHA256SUMS` verified; review verdict GO
  with one condition, F1).

## 2. Root cause of the v3.2 Linux proof failure (S1 `UNIT_START_FAILED`, reader unit `not-found`)

Proven by the 1-minute bisect on ubuntu-24.04 / systemd 255.4-1ubuntu8.17, copied byte for byte into
`evidence/v33/s1_bisect/` (its own `SHA256SUMS.txt` verified):

| File | sha256 |
|---|---|
| `bisect.sh` | `8b97db28d55e67c6ba2a2b66b85314316bb6b0cfbca2bc2812dab4327f660d87` |
| `env.txt` | `2eff33df5f2d864bbd37c574c1d161a143465c9fbb11c7494fc436605fd5d0f9` |
| `results.txt` | `857b1332dfa1d80d8769a3baf922b39f7df0037f81c96bcdd82fc2d72d00f723` |
| `s1bisect.yml` | `d365271d71190724c23122e95a082c62fa1003815a4c7eba5c951a1d00fec0f1` |

- The reader's exact transient-unit property set, run with `systemd-run`: with `RequiresMountsFor` including
  `/mnt/day-d-data` → rc 1 `A dependency job for <unit>.service failed`, `LoadState=not-found` (`b-full`, `b-nocond`);
  `RequiresMountsFor=/mnt/day-d-data` alone reproduces it (`b-rmf-mnt-only`); without that path it runs (`b-nomnt`,
  `b-neither`); `ExecCondition` (1 or 3 lines, `ExecConditionEx`) is no factor (`b-cond1`, `b-condex`).
- On the runner `/mnt` has an fstab-generated `mnt.mount` (Azure resource disk), `LoadState=loaded`,
  `ActiveState=failed`, and `/mnt/day-d-data` is a plain directory on `/` (`env.txt`): `RequiresMountsFor` adds
  `Requires=mnt.mount`, whose failed start fails the dependency job.
- Real host (read-only check 10/10/2026 09:34 BRT): systemd 255.4; `/mnt/day-d-data` is its own ext4 mount
  (`/dev/nvme1n1`, fstab `defaults,nofail`); `mnt-day\x2dd\x2ddata.mount` loaded/active/mounted; `mnt.mount`
  `LoadState=not-found`. The production reader unit is not affected; the defect was in the proof harness. The reviewed
  reader unit row (`reference/c3po-reader.service`, `bind_l12host.session_unit_rows`) is unchanged.
- Diagnostic gap: the engine dropped systemd-run's rc and stderr on failure, so the RESULT carried no reason.

## 3. What changed (family files; every other family byte is v3.2's, incl. `vendor/`, `reference/`, the runner)

| File | v3.2 sha256 | v3.3 sha256 | Why |
|---|---|---|---|
| `l12host/l12host_effect.py` | `46948fca9ebe25220c6035e1d3266ea814610793cb58255b77efed399eecaac3` | `5dc4cdc8cdd1f0c575d85a782c61133822f2837b710db94dd181821409da9e30` | item 5: `unit_start_failure` on a failed UNIT_START |
| `l12host/l12host_extended.py` | `36cd087bccb2cab283c1accf6a76b366a1f89d01dac5c476877e9d057d9f1e53` | `c7f3d8a116598f35ba2f139db11dd21d9405303449de0b75ca4f9a3983ef2b9f` | item 5: the worker writes it as a slot diagnostic |
| `l12host/l12host_runtime.py` | `d4f774590800618547ad482c011161223ddad99f8713f74d7e8daedb2be4670c` | `c698e773c37c60b7702423fcb325ee17a48b4e83ff7653a20d9c2f654ee14bdf` | item 5: `Shell.unit_diag`, `diagnostic_line` (RESULT `diagnostics`) |
| `l12host/linux_systemd_proof.py` | `643d9190067e66d6920d7bae5cbc04ef88a5d4c86848c9e6581f2bbfd290fa26` | `1b9a4d1027254a41be54de80c42c939fda23a8f79abf7c708719bfb8965a0723` | items 3, 4: host mirror + checks, failure dumps |
| `l12host/tests/kit.py` | `65845a276462795b95977f167a60c009dc0f0f7a5b9c2a7475f42aadbfad6f7d` | `7e8b737765664b73d1a8a75c4a86a1150311f4a0d6d89b6d44c371b12a2afa69` | item 6: faithful fake `systemd-run` |
| `l12host/tests/test_v33.py` | (new) | `a7b7c3bf553fa3123ed41328f431b3c68c96666c9b878b6490723f491e868259` | items 2, 5, 6, proof helpers: 14 tests |
| `l12host/lots/k9tools/gen_k9_plans04.py` | `2b08ee13b7c748dbf84278ba01efb56d16b95490c2811902106765eaf4e7a31c` | `66af6c9e3b85215a1d5c44c91ef588dbc7e94d04aa96300fcc979684416e51cf` | item 1: lots patch, byte-identical |
| `l12host/lots/DOWN.SPEC.DRAFT.json` | `b9cd104ed33173775bb065bc1ff9ba649f9cce28f704f9e9376dbce68fbede98` | `e0f06bbb3254d682effdb37a9a73e1f3fa576ec96a7713eb6f8f6d5b8457a959` | item 1: lots patch, byte-identical |
| `l12host/verify_family.py` | `a7ddb8fe36b3a89451a9acfb83b0fa242fa5260e5d091e482a23e423b7593161` | `915a90729211f64cb80a6e9f2b4a6f519f6f9832e9f66d340cbe9b676abacabb` | item 1: lots patch, byte-identical (generator pin) |
| `l12host/lots/build_specs.py` | `e58f2b8ca5b886cd8ec37f2ee8f342d83a9542e46849d0b3b8a17e40f3b1ecb4` (patch: `60be3582…`) | `3c75ee840e6b63b32ecd4ffdb6dd930862f5a84c4c5b0a98a5e8aba3bc1550cd` | items 1, 2: lots patch + F1 + LOW 6 |
| `l12host/tests/test_lots_patch_v34.py` | (new; patch: `2781c746…`) | `e7243b6d213bb088baf8a25b6d4c50a953da8504c17dd5351c16b203ff8a3846` | items 1, 2: lots patch; its DOWN helper passes the UP REAL dir (F1) |
| `l12host/CONTRACT.md` | `79bd6320af300fe8f2453bb1fd17ce5b92401d8238999fdc097b70a6e5e188cd` | `0f445d96ac7fcca227079aeeb5c861d1eceb730edafb872df3c4e2725b2db10e` | item 8: section 0-ter |

Outside the family: `.github/workflows/l12host-v32-proof.yml` (`881c99bf…`) → `.github/workflows/l12host-v33-proof.yml`
(item 7), this file, and `evidence/v33/` (new). The v3.2 evidence files are kept unchanged as history.

### Item by item

1. **Lots patch merged** (`files/*` copied over the tree): L-01 closed grid choice C/D in `gen_k9_plans04.py`, L-02 DOWN
   PO at 06:01:30 BRT, L-06 REAL specs written outside the family; `verify_family.py` pins the new generator.
2. **Review condition F1 + LOW 6** (`build_specs.py`): `write --lot DOWN` requires `--up-real-dir` and refuses before any
   write unless grid id, K9 request, GO, runner and capture_launch plan bytes are the UP REAL spec's (one code per
   mismatch; then the UP dir is re-validated whole). Because the UP spec does not carry the capture plan, the REAL UP
   dir now also holds `cross_lot/capture_launch.json` (its own plans run's capture plan; in its `SHA256SUMS`; not named
   by the UP spec; `validate` binds it to the dir's request, GO and grid). LOW 6: `validate --out-dir` makes a relative
   DIR absolute (function and CLI) and refuses a non-directory as `REAL_SPEC_DIR_NOT_A_DIRECTORY`.
3. **Proof harness host mirror**: before any UP/DOWN work, a loaded and not-active `mnt.mount` loses its `/mnt` fstab line
   (daemon-reload + reset-failed → `not-found`, like the host; an active one is left and the check fails);
   `/mnt/day-d-data` becomes its own fstab mount (tmpfs 64 MiB, `defaults,nofail`) → `mnt-day\x2dd\x2ddata.mount`
   loaded/active/mounted. `host_mirror` section and checks `mnt_mount_not_found_like_host`,
   `day_d_data_mount_active_like_host`. Comment cites the bisect hashes.
4. **Proof failure dumps** (bounded, printable): `systemctl show` of both units and the R0/S1 slot services, epoch-04
   unit files/units, last 200 journal lines of the S1 slot service and both units; taken before the cleanup and after
   an exception.
5. **Engine diagnostics**: same code `UNIT_START_FAILED`, same status (`UNCERTAIN`), same `transport_at`/`child_*`
   fields, same effect accounting; one extra key `unit_start_failure` (exit code, stdout/stderr sha256 + size, first
   300 bytes of systemd-run's stderr as printable ASCII) only on that refusal; the slot RESULT `diagnostics` lists
   `UNIT_START_FAILED:<class>:rc=…:stderr_sha256=…:stderr_bytes=…:stderr=…`.
6. **Faithful fake `systemd-run`**: `mount_units` (path → `failed`/`active`); a failed unit on a `RequiresMountsFor`
   path or prefix → rc 1 + the systemd 255 message, unit never loaded.
7. **Workflow** `l12host-v33-proof.yml`: branch `ops/fable-l12host-v33-proof-20261010`, artifact
   `L12HOST_V33_OWN_LINUX_PROOF`, results `/tmp/l12host-v33-proof-results`; both Python steps run the three suites;
   interpreters and the 30/30/95 step timeouts kept; every step timed, job 200 min ≥ 195 min sum (v3.2 review LOW 3).
8. **CONTRACT.md** section 0-ter (root cause with the evidence hashes, host check, fixes, lots patch merged, F1, LOW 6,
   open items); this file in the seal.

## 4. Runs (macOS, this build; temp outside ~/Documents)

All on the sealed family `5c3f5f4f…` (unchanged before/after every run). The two Pythons ran concurrently
(13:03–13:28 UTC = 10:03–10:28 BRT), three full runs each, every run = the three suites in sequence. Temp parent:
`$HOME` (outside `~/Documents`, not a File Provider domain; the kit refused the world-writable `/private/tmp` and
`/tmp` candidates); nothing left behind.

| Check | Python 3.12.14 (venv) | Python 3.9.6 (/usr/bin) |
|---|---|---|
| `tests/test_l12host.py` (unchanged, 81) | 3/3 runs: 81 tests, 0 failures, 0 errors, 1 skipped (Linux procfs) | 3/3 runs: same |
| `tests/test_lots_patch_v34.py` (17) | 3/3 runs: 17, 0, 0, 0 skipped | 3/3 runs: same |
| `tests/test_v33.py` (new, 14) | 3/3 runs: 14, 0, 0, 0 skipped | 3/3 runs: same |
| per run | 112 tests, 0 failures, 0 errors, 1 skipped; 7.6–7.9 min | same; 8.1–8.4 min |
| `build_specs.py validate` (in-family) | `UP_SPEC_VALID_WITH_FILL_INS` 11 slots (P4 reported not ok: the DRAFT3 record), `DOWN_DRAFT_VALID_WITH_FILL_INS` 8 slots, PO 09:01:30Z; output `4284c295…`, byte-identical to the lots review's | same bytes |
| `gen_k9_plans04.py check --grid C` / `--grid D` | `SCHEDULE_OK` (rc 0), engine sha256 `5dc4cdc8…` (the v3.3 engine), slots `8da175ae…` / `4497a1ec…` | same bytes |
| `gen_k9_plans04.py check --grid DRAFT3_REJECTED` | `REFUSED START_WINDOW_NOT_ALLOWED:publish_launch` (rc 2) | same |
| `verify_family.py` | `SEAL_EXACT`, 57 files, 15 pins | same bytes |
| mutation checks (`evidence/v33/MUTANTS_V33_PY312_DARWIN.json`, scratch copies) | 10/10 mutants killed: engine key removed, excerpt unbounded, worker diag removed, fake refusal removed, fake prefix walk removed, F1 cross-check removed, capture comparison removed, LOW 6 absolute path removed, dump prefix filter removed, mirror check weakened | — |

Evidence (`evidence/v33/`): `V33_TEST_RUNS_PY312_DARWIN.json` `ca63c982…`, `V33_TEST_RUNS_PY39_DARWIN.json` `1fd58f72…`,
`V33_TEST_NAMES_*_DARWIN.txt` `022853bd…` (identical, 112 names), `MUTANTS_V33_PY312_DARWIN.json` `dbabc86f…`,
`checks/` (validate, generator checks, verify_family on both Pythons), `probes/mutants_v33.py`, `s1_bisect/`.
One earlier mutation pass found the LOW 6 test passing with the function-level fix removed (the CLI also makes the
path absolute); the test now also calls `check_real` with a relative path, and the final pass above kills it.

## 5. Seals

- Family `l12host/SHA256SUMS`: `5c3f5f4f7d121846a61d1b33528b0163be4c70b29b534118a28fa9017efd1f05` (57 files, 15 vendor
  pins, `verify_family.py` `SEAL_EXACT` on 3.12.14 and 3.9.6). This is the seal Saturday's W would sign (the v3.2 seal
  `625d244b…` is superseded).
- Top `SHA256SUMS` seals every file of this delivery including this one (its own hash is reported outside).

## 6. Open items

- The Linux proof has not run in this build (no push from here). The two new mirror checks are first observed on the
  runner; an ACTIVE `mnt.mount` on another runner image makes the proof red by design (it never unmounts a live disk).
- The mirror uses tmpfs, not ext4 (the unit dependency semantics are the same).
- Host facts not covered by today's read-only check but used by the engine for the reader's mount source: `/` and
  `/mnt` root-owned and not group/other-writable (`safe_ancestors`); the owner of `/mnt/day-d-data` itself is not
  checked.
- F1 is enforced at `write`; `validate --out-dir` of a DOWN dir alone does not repeat the cross-check (no
  `--up-real-dir` for `validate`).
- The lots-patch decisions for Codex stand (PATCH.md §6: elect C or D, accept the generator bytes and the added keys,
  engine executed by path, PO overlap); the generator's manifest now records the v3.3 engine sha256 `5dc4cdc8…`.
- Pre-existing macOS flake classes (v3.2 C1 / PATCH.md §6.10) are not addressed here; see section 4 for what these runs saw.
