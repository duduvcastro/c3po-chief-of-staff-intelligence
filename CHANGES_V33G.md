# L12-HOST v3.3g: changes from v3.3f

Fable subagent, Saturday 10/10/2026. Nothing was run on any host. There was no push, no network and no SSH. Every
hash below was computed by command (`shasum -a 256` / `hashlib`). No symbol and no private content is printed or stored
here; the issued D chain and its inputs are cited by path and sha256 only. This is not a GO, not an election of grid E,
not a registry, not a seal of the Codex verifier and not a host certification.

## 1. Base and inputs

- Byte copy of the sealed v3.3f set `fable-l12host-v33f-20261010` (top `SHA256SUMS`
  `33514ce8f04ce53c037f4764bd7702c12ed3f7ede85927896a0523cc1c5f5d34`, family `l12host/SHA256SUMS`
  `4108eb7b8003df12ebff1a7828b204f0c58c3b26382f13a908e5d51f92071e44`). Both seals and all 116 listed files were
  verified before the copy, and only those files plus `SHA256SUMS` were copied. The v3.3f directory, the grid-E patch
  directory and the issued D run were only read.
- Grid-E patch `fable-l12host-gride-patch-20261010` (its `SHA256SUMS`
  `b2ce08ddf2ecc33ad7f84905fded09b0a1dca9cc9bb7b77c859fbdcb1aaf0be7` verified; `PATCH.md`
  `9b8198dc9fef86429c2c816851e0c3e045b136f0eae1764aa11ed82006fe7ee6`). The patch was built on v3.3, not v3.3f. It was
  merged as its adversarial review says:
  - Three whole files: `lots/k9tools/gen_k9_plans04.py` `04379aa605f6de319b3e48bb4a312f7de037d9f1300cbfbec8810e080f962051`,
    `verify_family.py` `06cf89e6583c4ca0b334e7cca89c9155475039a9c529a60201a3f4bfd163b634` and `tests/test_grid_e.py`
    `ec01092682a0ab9c57a75242d7b4e7be62cfa63f6e373b326f0f3544638bd254`. One test of `tests/test_grid_e.py` was then
    flipped (section 2). The v3.3f bases of the first two files equal v3.3's. Applying the patch's own diffs
    (`ebdd9fe91ef11508601710e9116137670b5f888516aaf07303d19b612c9f2207`,
    `3c4aa852d6954635553b2fe364d1f78d8816688d7d9de934759fdd92ef43f4ef`) to the v3.3f generator `66af6c9e…` and to
    `verify_family.py` `915a9072…` gives exactly `04379aa6…` and `06cf89e6…`.
  - `tests/test_lots_patch_v34.py` takes only the patch's 2-line hunk (diff
    `26ebb1af7dc8ec41fae7e459bbe6617a260ace03e457537bbce0b4253f32243b`; the L-01 literals become C/D/E) over v3.3f's
    own `37213bf0…`. The result is `c852c2a27f1b142fc95771f0db87c15b20abed236a50b94194eb7bb86c6ef9de`.
  - The patch's `derived/` seals (valid only over v3.3) were not used. Its GO tool copy (`k9go04-tool-patch/`) is not
    part of the family.

## 2. What changed

Family: 53 of the 58 v3.3f files are byte-identical. Unchanged files include `vendor/`, `reference/`, the runner, the
engine `l12host_effect.py`, the runtime, the extended executor, bind, install, the kit, the Linux proof script, the
in-family DRAFT specs and the inputs. One file is new, so the family has 59 files.

| File | v3.3f sha256 | v3.3g sha256 | Why |
|---|---|---|---|
| `l12host/CONTRACT.md` | `ac271006727d963f1113c80a6a03cab9713b189a6bc1db3cb88ca1ed433eb04e` | `ab49c7f7cb3484d6fc4cb144f50dbab4e43ccb1dabdc0f3ccf7faf11cf8133d4` | title v3.3g; new section 0-quinquies (`--grid C\|D\|E`, generator `04379aa6…`, E reserve, D unchanged, ELECTED_GRIDS, X2 and the critical window, workflow, tests) |
| `l12host/lots/build_specs.py` | `78b936304637be9d8de9132ed28c46841e8e35d5f3eb80a0dd0b219dbfb765b3` | `781dcf0a24a3f2fe80ec61a5e1603474e9a50b3f3adf2bddf536bf3e30dcb5b9` | `ELECTED_GRIDS = ("C", "D", "E")` (root decision, review finding 2); docstring (C/D/E, a v3.3g paragraph). No other line changed |
| `l12host/lots/k9tools/gen_k9_plans04.py` | `66af6c9e3b85215a1d5c44c91ef588dbc7e94d04aa96300fcc979684416e51cf` | `04379aa605f6de319b3e48bb4a312f7de037d9f1300cbfbec8810e080f962051` | grid-E patch, whole file (GRIDS['E'], ELECTABLE C/D/E, docstring) |
| `l12host/verify_family.py` | `915a90729211f64cb80a6e9f2b4a6f519f6f9832e9f66d340cbe9b676abacabb` | `06cf89e6583c4ca0b334e7cca89c9155475039a9c529a60201a3f4bfd163b634` | grid-E patch, whole file (generator pin) |
| `l12host/tests/test_lots_patch_v34.py` | `37213bf0bd2c23afc46ecb40537c491f4c90a3a50f7b06c5a37378f9db0c7eaa` | `c852c2a27f1b142fc95771f0db87c15b20abed236a50b94194eb7bb86c6ef9de` | the patch's 2-line hunk only (17 tests) |
| `l12host/tests/test_grid_e.py` | (new; patch `ec01092682a0ab9c57a75242d7b4e7be62cfa63f6e373b326f0f3544638bd254`) | `54716443a5e3a0ed1a0e1d10559a48db37883c813a357a38a4d569c698663cde` | 11 tests; the one test that asserted the old tuple was flipped and extended (below), plus a docstring note |

Outside the family:

- `.github/workflows/l12host-v33f-proof.yml` (`0bdc7a72f09133fcda3f80e7f56433e30538e29275c42b1bc6206a51cab5c99b`) was
  renamed to `.github/workflows/l12host-v33g-proof.yml`
  (`b2cca713f771d16ac93f76b3ffeb7bd79ddfaacab2bc0f460be2297c909c1bd1`). It uses branch
  `ops/fable-l12host-v33g-proof-20261010`, artifact `L12HOST_V33G_OWN_LINUX_PROOF` and results
  `/tmp/l12host-v33g-proof-results`. Both Python steps also run `tests/test_grid_e.py`
  (`TEST_GRIDE_RESULT_PY{312,39}.json` / `TEST_GRIDE_NAMES_PY{312,39}.txt`), even after an earlier suite fails, like the
  other suites. Its issued-D-dir test skips there. The concurrency group was renamed; the steps, interpreters and
  timeouts are v3.3f's. A text diff against the v3.3f workflow (after renaming v33g to v33f) shows only the header
  comment and the two added suite lines.
- This file and `evidence/v33g/` are new. `CHANGES_V33.md`, `CHANGES_V33F.md` and the earlier evidence are kept as
  history.

**The flipped test.** `GridE.test_real_writer_refuses_e_plans_without_its_own_reviewed_change` asserted
`bs.ELECTED_GRIDS == ("C", "D")` and the refusal `REAL_PLANS_GRID_NOT_ELECTED` (detail `E`). It is now
`GridE.test_real_writer_builds_and_validates_e_up_and_down_lots`, which checks the following:

- `ELECTED_GRIDS == ("C", "D", "E")`.
- A plans run of grid E (TEST-ONLY act B / GO) becomes a REAL UP through `write_real`, with the SYNTHETIC REAL K9
  inputs of the run (as the lots suite does), D-NET networks and owner deadline 19:20:00Z. The result is `UP`, grid
  `E`, `slots_sha256 65839e19…`, every start window ok, P1/P4/X1/X2/X3/X7 at 19:26/20:26/20:38/21:26/00:26/02:26Z, and
  margins P1–X2 460/1540/640/460/1540/460. The KILL record's request grid is `E`.
- The CLI `validate --out-dir` returns `REAL_SPEC_DIR_VALID UP E`.
- The REAL DOWN of the same run, written with `--up-real-dir` of that UP, is `DOWN` grid `E` with every window ok and
  `up_cross_check` grid `E`, `byte_identical`. Its `validate` returns `REAL_SPEC_DIR_VALID DOWN E`.
- No automatic migration: an E DOWN over a REAL D UP is `REAL_DOWN_GRID_NOT_THE_UP_ONE`, detail `["D", "E"]`, and
  nothing is written.

The physical `bind_l12host.build_lot` runs before and after each write. Mutation probe
(`evidence/v33g/probes/mutants_v33g.py`): 5/5 single-literal mutants of `build_specs.py` are killed by this test alone,
on both Pythons, and the control passes. The mutants are `ELECTED_BACK_TO_C_D`, `ELECTED_ADDS_DRAFT3`,
`WRITE_ELECTS_ONLY_C_D`, `VALIDATE_ELECTS_ONLY_C_D` and `F1_GRID_CHECK_DROPPED`.

## 3. D unchanged, E end to end (scratch proofs; outputs only in the scratchpad `v33g2-*` directories)

**D request and plans from the REAL issued inputs.** The v3.3g generator's `plans --grid D` was run with the app tree
de96aee9 (scratchpad `stagetmp/wt-de96/c3po/backend`, read only) and act B `fable-actb04-issued-20261010/ADENDO_EPOCA_04.md`
(`23d5099e…`). It used the family's certified release `5fd6eadb…` and policy `6757e791…` and the issued GO
`fable-k9go04-issued-20261010/k9/K9_GO_04.json` (`757c3096…`). The script is `evidence/v33g/probes/d_real_regen_compare.py`
and the output is `evidence/v33g/D_REAL_REGEN_COMPARE_DARWIN.json`.

| Run | request | 12 plans vs issued `final-plans/plans` | runner | manifest |
|---|---|---|---|---|
| family engine `5dc4cdc8…`, Python 3.9.6 and 3.12.14 | `efb94cf20ae8dccd2d2a6c7d258d0577ff6eb9b8fd1b0f235328d8256296822f` = issued | all 12 byte-identical | identical | `8d5b48dc…`: differs from the issued `974eb8aa…` ONLY in `engine_rule.sha256` (`5dc4cdc8…` vs `46948fca…`) |
| `--engine` = the v3.2 engine copy `46948fca…` (`fable-k9go04-family-20261010/l12host/l12host_effect.py`), both Pythons | `efb94cf2…` | all 12 identical | identical | `974eb8aa100798b856c5f1246d88e37705336a4a7550bc6a28b108f86af91b50`: the whole 15-file tree is byte-identical to the issued `final-plans/` |

`tests/test_grid_e.py` with `L12_ISSUED_D_DIR` set to that directory also reproduces the issued originals
(`test_d_originals_reproduced_from_the_issued_dir`, passed on both Pythons).

**D REAL lots: v3.3g writer vs v3.3f writer.** The probe is `evidence/v33g/probes/real_lots_probe.py`. It used
TEST-ONLY act B / GO, SYNTHETIC REAL K9 inputs and the same CLI argv for each family. The outputs are
`REAL_LOTS_PROBE_V33{F,G}_PY{39,312}_DARWIN.json`, `D_REAL_COMPARE_PY{39,312}_DARWIN.json` and
`KILL_DIFF_D_{UP,DOWN}_PY{39,312}_DARWIN.json`.

- The D plans dir (15 files) is byte-identical between the v3.3f and v3.3g generators. So are the synthetic REAL
  inputs (13 files).
- REAL UP D (31 files) and REAL DOWN D (27 files): same file set. Every file is byte-identical except
  `records/KILL_CHANGED_ROWS.json` and the `SHA256SUMS` that lists it.
- In the KILL record, the ONLY differing JSON paths are `/provenance/builder_sha256` (`78b93630…` → `781dcf0a…`) and
  `/provenance/generator_sha256` (`66af6c9e…` → `04379aa6…`). Every `row_sha256` is equal, and these are the
  registry's `effect_sha256`. KILL record `4db38c6d…` (v3.3f) → `f3162711d33ce4e35372e7afdc1d3521b87476fba1ccafb8d4f95469314652ec`
  (v3.3g), the same on both Pythons. The UP spec `01a2c697…` and DOWN spec `114181b2…` are equal.
- Both writers `validate` their D dirs `REAL_SPEC_DIR_VALID`, and both DOWNs have `up_cross_check` `byte_identical`.

**E REAL lots end to end through the CLI (v3.3g).** The probe ran on both Pythons. `plans --grid E` gives `PLANS_OK`.
`write --lot UP` gives `REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY` (spec `859b1c88…`, 31 files, all windows ok; P1 19:26:00Z
margin 460 … X2 21:26:00Z margin 460, X3–X7 the fixed instants). `write --lot DOWN --up-real-dir` gives the same status
(spec `6e95865e…`, 27 files, cross check grid E, byte_identical). `validate` of both gives `REAL_SPEC_DIR_VALID`, grid
`E`. The E KILL record is `31379d18946da8f9c34f1ca72280ea60a93eac918caf649bca3b3e446c1c3fe2`, the same in the UP and
the DOWN. As a contrast, the v3.3f writer refuses the same E plans with `REAL_PLANS_GRID_NOT_ELECTED` (detail `E`,
nothing written), and the v3.3f generator refuses `check --grid E` with `GRID_NOT_IN_THE_CLOSED_CHOICE`.

## 4. X2 under E and the critical window (for Codex)

Under E, X2 `sources_launch` starts at 18:26:00 BRT. Its start window `[18:26:00, 18:27:45]` is allowed, with margin
460 s. Its budget runs to 19:41:00 BRT (run_not_after 19:40:30), which is across the engine's 18:58:40–19:25:59
critical band. In this family the band is consulted only on start instants:

- `validate_slots` under `validate_authority`, on the slot table's `at`;
- `Shell.slot_window`, at the slot start;
- the core `operation_gate`;
- the engine's `before_effect`, just before a transport.

A case-insensitive grep of the engine, runtime, extended executor, decoder, bind, install, runner and `vendor/` for
`critical`, `58:40`, `25:59`, `3520` and `1559` finds no running-window rule. Under C and D no slot runs across the
band: D's X2 ends 18:41 BRT. **If E is ever elected, Codex must accept explicitly that X2 runs across the critical
window.** This delivery does not decide it.

## 5. Runs (macOS, this build; temp outside ~/Documents in the system temp dir under /var/folders; probe outputs in the scratchpad)

All runs used the sealed family `604cf4aaad953c0911524200e077a1ea1de08951848d02c1a2e046bf7bebf3d9`, read before and
after every suite and unchanged. Each suite ran ONCE per Python, sequentially: Python 3.12 from 15:49:36Z to 15:57:41Z,
then Python 3.9 from 15:57:41Z to 16:06:26Z (12:49–13:06 BRT). The harness is `evidence/v33g/probes/run_suites_v33g.py`.

| Check | Python 3.12.14 (venv-backend) | Python 3.9.6 (/usr/bin/python3) |
|---|---|---|
| `tests/test_l12host.py` | 81 tests, 0 failures, 0 errors, 1 skipped (448.5 s) | 81 / 0 / 0 / 1 (491.0 s) |
| `tests/test_lots_patch_v34.py` | 17 / 0 / 0 / 0 | 17 / 0 / 0 / 0 |
| `tests/test_v33.py` | 14 / 0 / 0 / 0 | 14 / 0 / 0 / 0 |
| `tests/test_v33f.py` | 15 / 0 / 0 / 0 | 15 / 0 / 0 / 0 |
| `tests/test_grid_e.py` (no `L12_ISSUED_D_DIR`, as in CI) | 11 / 0 / 0 / 1 | 11 / 0 / 0 / 1 |
| `tests/test_grid_e.py` (`L12_ISSUED_D_DIR` = `fable-k9go04-issued-20261010`) | 11 / 0 / 0 / 0 | 11 / 0 / 0 / 0 |
| `verify_family.py` | SEAL_EXACT, 59 files, 15 vendor pins, seal `604cf4aa…` (output `f266c28b…`) | same bytes |
| `build_specs.py validate` (in-family) | `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610` (= v3.3f) | same |
| `gen_k9_plans04.py check --grid D` | `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302` (= v3.3f) | same |
| `gen_k9_plans04.py check --grid E` | `60c031da474063f06e0a7e96186ebdd181392307f1783c0b34030ea39f4cc174` (rc 0, `SCHEDULE_OK … grid=E`) | same |
| `check --grid C` / `DRAFT3_REJECTED` | `843c6c7f…` / `ce28a74f…` (rc 2, `REFUSED START_WINDOW_NOT_ALLOWED:publish_launch`) (= v3.3f) | same |
| mutation probe (flipped test) | 5/5 killed, control passes | 5/5 killed, control passes |

The skipped tests are `test_b1_boot_id_on_real_linux_procfs` (Linux procfs only) and, without the issued dir,
`test_d_originals_reproduced_from_the_issued_dir`. `Review.test_extended_ceiling_kills_the_group_and_is_uncertain`
(the known macOS timing flake of v3.3 / v3.3f) passed in both runs, so it did not need a rerun.

Disclosures:

- A first suite run was started on a pre-final family (seal `7a71b74b…`). It was stopped after a few minutes, with no
  result kept, to correct one sentence of the new `build_specs.py` docstring (it had said every D byte was unchanged;
  the KILL record provenance changes). The family was then resealed and every check and suite above was run on
  `604cf4aa…`.
- A pre-seal smoke run of `tests/test_grid_e.py` (3.9: 11/0/0/1) and pre-seal probe runs were also made. They are
  superseded and not kept.

Evidence (`evidence/v33g/`):

| File | sha256 |
|---|---|
| `evidence/v33g/D_REAL_COMPARE_PY312_DARWIN.json` | `fc0448a6ad427d4332bc1819ab7dd268d9182a09b2fd8c1bf100d884974e3957` |
| `evidence/v33g/D_REAL_COMPARE_PY39_DARWIN.json` | `fc0448a6ad427d4332bc1819ab7dd268d9182a09b2fd8c1bf100d884974e3957` |
| `evidence/v33g/D_REAL_REGEN_COMPARE_DARWIN.json` | `fed14e918e148341f2864a24aad3e0324a1d1221fbb60e9ddd22da3263d00cdd` |
| `evidence/v33g/KILL_DIFF_D_DOWN_PY312_DARWIN.json` | `3f86681fa5e05777c281b20518beba04690e6d0133fd465da0b02303615fc723` |
| `evidence/v33g/KILL_DIFF_D_DOWN_PY39_DARWIN.json` | `3f86681fa5e05777c281b20518beba04690e6d0133fd465da0b02303615fc723` |
| `evidence/v33g/KILL_DIFF_D_UP_PY312_DARWIN.json` | `3f86681fa5e05777c281b20518beba04690e6d0133fd465da0b02303615fc723` |
| `evidence/v33g/KILL_DIFF_D_UP_PY39_DARWIN.json` | `3f86681fa5e05777c281b20518beba04690e6d0133fd465da0b02303615fc723` |
| `evidence/v33g/MUTANTS_V33G_PY312_DARWIN.json` | `dce2996c0ebc1de27bde415189d2c5117b1de65ae2f5abb66f1d4c9c2b46f82d` |
| `evidence/v33g/MUTANTS_V33G_PY39_DARWIN.json` | `b10fa4144379fcdfc7ce0a9fffb209776da59ca84a9183bb3d7b94cbc2c69787` |
| `evidence/v33g/REAL_LOTS_PROBE_V33F_PY312_DARWIN.json` | `6f7b4c6505e3fa6683b4595a336044a25ef8025cb253ddc5c8e6cc9eaf4367c9` |
| `evidence/v33g/REAL_LOTS_PROBE_V33F_PY39_DARWIN.json` | `65f1797540f2a7c11cf7b9227c7988b97a52c37f63f0b0b5ab6331b28ab97be2` |
| `evidence/v33g/REAL_LOTS_PROBE_V33G_PY312_DARWIN.json` | `96acffdd0bfac1723cd38c2a3146f5565c464f3eb0a65b30f9fe4bc6a9b5cf3e` |
| `evidence/v33g/REAL_LOTS_PROBE_V33G_PY39_DARWIN.json` | `43934decb4d0855128af96cf2a6512160ecd74385b3b2253c627c6255fc616cc` |
| `evidence/v33g/V33G_TEST_NAMES_PY312_DARWIN.txt` | `17bc86aae281567ab06e5c907e6005c462454343d86a7c895829fbb32ce40755` |
| `evidence/v33g/V33G_TEST_NAMES_PY39_DARWIN.txt` | `35abc8d947528c8a89cc33efd2c4643211fefea915723d8b731bf85bb075d093` |
| `evidence/v33g/V33G_TEST_RUNS_PY312_DARWIN.json` | `00adafb31acd1a06286434d489486113e0d9f7bf1cd84fb67234922f48ddc5a6` |
| `evidence/v33g/V33G_TEST_RUNS_PY39_DARWIN.json` | `afdb2eb6543faae3f9ed34957069e6cfd911bd951c6ba3b0d67cb466d7ad69f3` |
| `evidence/v33g/checks/GEN_CHECK_C_PY312.txt` / `_PY39.txt` | `843c6c7fb91e5ef5244d575debe4253555b268cd32f4af5fed98dec4c7f7a548` |
| `evidence/v33g/checks/GEN_CHECK_DRAFT3_REJECTED_PY312.txt` / `_PY39.txt` | `ce28a74f2d9be492019408c698e7f825c80a3d0b89a3c8647b4deec1b693a46d` |
| `evidence/v33g/checks/GEN_CHECK_D_PY312.txt` / `_PY39.txt` | `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302` |
| `evidence/v33g/checks/GEN_CHECK_E_PY312.txt` / `_PY39.txt` | `60c031da474063f06e0a7e96186ebdd181392307f1783c0b34030ea39f4cc174` |
| `evidence/v33g/checks/SPECS_VALIDATE_PY312.json` / `_PY39.json` | `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610` |
| `evidence/v33g/checks/VERIFY_FAMILY_PY312.json` / `_PY39.json` | `f266c28bf50e46660ae544b3e8415fb23793b65342b78fdfa5cf15462c8dc6db` |
| `evidence/v33g/probes/d_real_regen_compare.py` | `f1d47aa875ce2df5603dc7b0da8909e0354a3b18253ef1a7817795879c769d10` |
| `evidence/v33g/probes/make_sums.py` | `169992d5f35369b44b310507c3d2ff65ff40124293b529751dd5ab686ac2384b` |
| `evidence/v33g/probes/mutants_v33g.py` | `9a8ac5839cc03891b4fd18e897388e54b665681a2363b3151cef3c44b2c0b1f8` |
| `evidence/v33g/probes/real_lots_probe.py` | `277826bf90385652bfba6521af9d5cd1eb63000ca687de36e285b207860fe64f` |
| `evidence/v33g/probes/run_suites_v33g.py` | `1e00ddb2f67b2fa41626d42e83e4c6adb2abe1fc85ccd1bc084bef94e29b000f` |

## 6. Seals

- Family `l12host/SHA256SUMS`: `604cf4aaad953c0911524200e077a1ea1de08951848d02c1a2e046bf7bebf3d9`. It has 59 files and
  15 vendor pins, and `verify_family.py` returns `SEAL_EXACT` on 3.12.14 and 3.9.6. It was written by
  `evidence/v33g/probes/make_sums.py`, which reproduces both v3.3f seals byte for byte. A W signed for v3.3f
  (`4108eb7b…`) does not cover v3.3g, and neither does the patch's derived seal `f5c7fd0a…` (over v3.3).
- The top `SHA256SUMS` seals every file of this delivery, including this one. Its own hash is reported outside.

## 7. Open items

- E is a capability, not an election. Using E needs its own new election, GO (E deadline per the patch's GO tool:
  19:10:30Z), originals, registry and Codex review, plus Codex's explicit acceptance of X2 across the critical window
  (section 4). The patch's `GRID_SLOTS['E']` (`65839e19…`) is generator-derived, and Codex should confirm it at
  election.
- The D chain is unaffected. The REAL D lots differ from v3.3f's only in the KILL record's builder/generator provenance
  hashes, and in the SHA256SUMS that lists it.
- The issued-D-dir test of `tests/test_grid_e.py` skips in CI, because the issued run is not part of the family. Its
  `MANIFEST_EXTRA_KEY`-type mutants are caught only on this Mac (the patch's note).
- The Linux proof has not run on v3.3g (no push from here). Its script is v3.3f's, and its schema stays
  `L12HOST_V33F_LINUX_SYSTEMD_PROOF`.
- The open items of v3.3f (`CHANGES_V33F.md` section 6) stand.
