# L12-HOST v3.3f: changes from v3.3

Fable subagent, Saturday 10/10/2026. Nothing was run on any host; no push, no network, no SSH. Every hash below was
computed by command (`shasum -a 256` / `hashlib`). No symbol and no private content is printed or stored here (the
Codex inputs are cited by path and sha256 only). This is not a GO, not a grid election, not a registry, not a seal of
the Codex verifier and not a host certification.

## 1. Base

- Byte copy of the sealed v3.3 set `fable-l12host-v33-20261010` (top `SHA256SUMS` `bc4581ab982b7046a54b43c099e6f5a78363b45cc82d21495afe0866422fcd60`, family
  `l12host/SHA256SUMS` `5c3f5f4f7d121846a61d1b33528b0163be4c70b29b534118a28fa9017efd1f05`), both seals verified before the copy: only the 99 files of its top
  `SHA256SUMS` plus that file (no `review-tmp/`). The v3.3 directory and every Codex directory were only read.
- Codex inputs implemented (read-only; the #429 comments by id: D-NET 6097884984, host evidence 6097680267, REAL files
  6098005680):

| Input | sha256 | Used for |
|---|---|---|
| `codex-epoch04-k9-real-verifiers-20261010-r2/ext/k9_verifiers04.py` | `0e7ce65e74dc9074ed9d3fc1724a5f57271d4503da353c85f964cd40822508e5` | R2 verifier (ORIGINAL_PINS, ABI) |
| `codex-epoch04-k9-real-verifiers-20261010-r2/DELIVERY.private.md` | `4ca80a8420cdbc638de0daa1895e164f298290368edffa3c7cca89e1b61acbb7` | R2 DELIVERY (required files) |
| `codex-epoch04-k9-real-verifiers-20261010-r1/DELIVERY.private.md` | `55977218e9b597a800515834adf3ff7973437e1c108572074a92c3a96d91ee5b` | R1 DELIVERY (required files) |
| `codex-epoch04-saturday-install-docs-questions-20261010-r1/ADDENDUM.private.json` | `ef81d52aa5867abc83755fb72bc0b5c5b60bcc06067f402249103bb21acb6303` | ADDENDUM, section 8_KILL |
| `codex-epoch04-saturday-install-docs-questions-20261010-r1/DECISIONS.private.json` | `0629e52f32da1703c50286d54478ef683a72b7a63e084961850fc7ebc8aece49` | DECISIONS, D_NET |
| `codex-epoch04-saturday-human-ordered-decisions-20261010-r1/ITEM4.body.txt` | `c64fad3bc9dbf40dcdc7933adc542194dcd314ffe21860ce542948e92ae601ec` | #429 item 4 body (D-NET) |
| `codex-epoch04-saturday-go-grid-decisions-20261010-r1/GO_FORM_SPEC.private.json` | `bd43257825cc491cdd691696b336ad39e240a6bcb9555653d03109e69619ffd5` | GO form |
| `codex-epoch04-saturday-go-grid-decisions-20261010-r1/V33_FAMILY_REAL_SPEC_PLACEMENT.private.json` | `f6132719b2fb5588354e2f8f3de3e7c39caae1b7f91d9e4117fa49d40233d93e` | family vs REAL SPEC placement |
| `codex-epoch04-saturday-human-ordered-decisions-20261010-r1/FAMILY_REAL_SPEC_PROOF_SCOPE.private.json` | `e8401027b0d8767f669fdb60f949372575ea3e22cd4241081904943bd7ab19e6` | family / REAL proof scope |

## 2. What changed (family; every other family byte is v3.3's: 48 of 58 files, incl. `vendor/`, `reference/`, the runner, the generator and the engine `l12host_effect.py`)

| File | v3.3 sha256 | v3.3f sha256 | Why |
|---|---|---|---|
| `l12host/CONTRACT.md` | `0f445d96ac7fcca227079aeeb5c861d1eceb730edafb872df3c4e2725b2db10e` | `ac271006727d963f1113c80a6a03cab9713b189a6bc1db3cb88ca1ed433eb04e` | section 0-quater (v3.3f), L2 closed, I2 ruled |
| `l12host/bind_l12host.py` | `12c9bdb29fa4528721ea5a62c95d2ccffeaa449432e5ea419d43b768d92b5e2f` | `24e25a5e4f36c9616072849afcec509369a174f928611d3ca97b49e690e56104` | the owner's question names the two unit networks |
| `l12host/l12host_runtime.py` | `c698e773c37c60b7702423fcb325ee17a48b4e83ff7653a20d9c2f654ee14bdf` | `b50ef0d3f3c0581deadc560225b2eaacd9fbb2a60efbc94ac9aee49453bc93d3` | D-NET constants; physical K9 class pin; per-unit networks + L2 pins; REAL-file constants, `k9_real_source`, `k9_effect_rows`, `validate_k9_real` (physical) |
| `l12host/linux_systemd_proof.py` | `1b9a4d1027254a41be54de80c42c939fda23a8f79abf7c708719bfb8965a0723` | `8082383389b5b908dec6cdfde34355d7d90b2fd436855b8161b1903c896474eb` | proof lots under the v3.3f pins (D-NET, synthetic REAL K9 files), check `v33f_pins_signed_in_the_proof_lots`, schema V33F |
| `l12host/lots/DOWN.SPEC.DRAFT.json` | `e0f06bbb3254d682effdb37a9a73e1f3fa576ec96a7713eb6f8f6d5b8457a959` | `b6ded3700fc78166a24d8a1c5d803aadefe66bd95cf94b6b60c4e89e85144103` | network values (K9 classes, reader and supervisor units) |
| `l12host/lots/UP.SPEC.json` | `0038355f8a0da67dd4ba2e7ca961cbda779fcf25786d0998f146980c86f956f4` | `e9f588cd33cde710b8e00dc81bfdb6c62c3e27a6f5d350b7fcfd48337a4beef3` | network values (+ the 2 decoder provenance hashes that follow their rows) |
| `l12host/lots/build_specs.py` | `3c75ee840e6b63b32ecd4ffdb6dd930862f5a84c4c5b0a98a5e8aba3bc1550cd` | `78b936304637be9d8de9132ed28c46841e8e35d5f3eb80a0dd0b219dbfb765b3` | D-NET NETWORKS / UNIT_NETWORKS; REAL K9 inputs (flags, bindings, copy, F1 extended); KILL record + `kill-record`; `validate` re-binds; synthetic REAL fill-ins / fixtures |
| `l12host/tests/test_lots_patch_v34.py` | `e7243b6d213bb088baf8a25b6d4c50a953da8504c17dd5351c16b203ff8a3846` | `37213bf0bd2c23afc46ecb40537c491f4c90a3a50f7b06c5a37378f9db0c7eaa` | helpers pass D-NET + SYNTHETIC REAL K9 inputs; 2 verifier-placeholder refusals re-targeted (17 tests) |
| `l12host/tests/test_v33.py` | `a7b7c3bf553fa3123ed41328f431b3c68c96666c9b878b6490723f491e868259` | `11b056812db5f0819675201ee3389d70590c6fc90e84e3755db24bd85c15ba2b` | CLI argv: D-NET names, --k9-* inputs (14 tests) |
| `l12host/tests/test_v33f.py` | (new) | `7e2e6fee6a630c48297586f5223be867da8ff35d0ef1c6cb7781fc4bbadd973e` | new: 15 tests |

Outside the family: `.github/workflows/l12host-v33-proof.yml` (`bd83913273ce622d21d627cc5f9bfe08c747efc79f216675995a03a26de1a9e2`) renamed to
`.github/workflows/l12host-v33f-proof.yml` (`0bdc7a72f09133fcda3f80e7f56433e30538e29275c42b1bc6206a51cab5c99b`: branch `ops/fable-l12host-v33f-proof-20261010`, artifact
`L12HOST_V33F_OWN_LINUX_PROOF`, results `/tmp/l12host-v33f-proof-results`, both Python steps run the four suites,
timeouts unchanged), this file, and `evidence/v33f/` (new). `CHANGES_V33.md` and the earlier evidence are kept as history.

## 3. The five items

### 3.1 D-NET (Codex #429 6097884984) and 3.2 L2

| Network | Constant (`l12host_runtime`) | Value | Pinned where |
|---|---|---|---|
| K9 class PROVIDER | `K9_NETWORKS_EPOCH04["PROVIDER"]` | `bridge` | k9 section (physical, `K9_NETWORKS_NOT_DNET`), every PROVIDER row (`K9_NETWORK_NOT_THE_CLASS_ONE`) |
| K9 class DATABASE | `K9_NETWORKS_EPOCH04["DATABASE"]` | `c3po_c3po_internal` | same |
| K9 class DATABASE_AND_PROVIDER | `K9_NETWORKS_EPOCH04["DATABASE_AND_PROVIDER"]` | `c3po_db_loopback` | same |
| K9 class NONE | row grammar | `none` | unchanged |
| reader unit `c3po-reader-e04` | `READER_NETWORK_EPOCH04` | `c3po_c3po_internal` | physical `SESSION_READER_NETWORK_NOT_DNET` |
| supervisor unit `c3po-massive-e04` | `SUPERVISOR_NETWORK_EPOCH04` | `c3po_db_loopback` | physical `SUPERVISOR_NETWORK_NOT_DNET` |

`c3po_default` is accepted nowhere in physical mode. The unit rows differ from v3.3's single-network shape ONLY in the
`--network` word (test `test_session_rows_differ_from_the_single_network_shape_only_in_the_network_word`).
`host`/`bridge`/`default`/`container:*` stay refused by the unit grammar (`UNIT_DOCKER_NETWORK_INVALID`). The REAL writer
refuses other `--network` values (`REAL_NETWORKS_NOT_DNET`). FIXTURE (non-physical) lots keep any grammar-legal names.

### 3.3 K9 REAL files

Declared per REAL lot (UP and DOWN), copied byte for byte into the REAL dir and `SPEC.files` (so AUTHORITY.files and
the REQUEST the owner signs):

| Signed relative path | Input flag | Source of the name |
|---|---|---|
| `ext/k9_verifiers04.py` | `--k9-verifier F --k9-verifier-sha256 HEX` | DELIVERY; the verifier checks `files["ext/k9_verifiers04.py"]` |
| `k9/VERIFIER_POLICY_04.json` | `--k9-policy F` (that lot's registry) | verifier `POLICY_REL`; GO form `reviewer_registry` |
| `k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json` | `--k9-review F` | verifier `CURRENT_REVIEW_REL` |
| `k9/K9_GO_04.PUBLICATION.json` | `--k9-publication F` | verifier `PUBLICATION_REL`; GO form `publication` |
| 8 originals: `act_b`, `B_CODEX`, `B_FABLE`, `B_DUDU`, `ACTA_DUDU`, `template_file`, `release`, `policy` | `--k9-original NAME=F` (8) | names and sha256 = the verifier's literal `ORIGINAL_PINS`; path = the registry's `originals[name].file` (the R2 source fixes no path) |
| (unchanged) `ext/k9_runner04.py`, `k9/K9_04_STEP_SET_REQUEST.json`, `k9/K9_GO_04.json` (GO form `go`), `k9/<op>.json` | plans dir / GO | v3.3 |

Callbacks: `k9_approval → ext/k9_verifiers04.py:verify_approval`, `k9_original → …:verify_original`,
`k9_step → …:verify_step`. Writer refusals happen before any directory is created; runtime refusals (physical: bind,
preview-stage, preview, every slot) before any effect. The codes are listed in CONTRACT.md 0-quater. F1 extended: the
DOWN must carry the UP dir's verifier, review, publication, originals and records byte-identical and a registry equal
except `lot`.

### 3.4 KILL record (Codex ADDENDUM 8_KILL)

`records/KILL_CHANGED_ROWS.json` (and `records/K9_04_STEP_SET_MANIFEST.json`) in every REAL dir, listed in its
`SHA256SUMS`, not in the SPEC; byte-identical between the UP and DOWN dirs of one plans run; re-derived byte for byte by
`validate --out-dir`; printed before any REAL write by `build_specs.py kill-record`. Canonical JSON,
schema `L12HOST_K9_KILL_CHANGED_ROWS_V1`:

```
{schema, formula: "min(generator_timeout_seconds, budget_seconds - 65); 65 = 20 docker margin + 15 gate allowance + 30 lateness slack",
 capture_rule: "DOWN capture_launch keeps its generator timeout (655) under the shell ceiling 750 s and the plan budget 690 s",
 ruling: "Codex ADDENDUM 8_KILL APPROVE_FORM_MIN_GENERATOR_KILL_BUDGET_MINUS65_FOR_CURRENT_CANDIDATE_ROWS_ONLY",
 request: {k9_request_sha256, grid, grid_slots_sha256}, go_sha256,
 provenance: {derived_by, builder_sha256, generator_sha256, generator_manifest_sha256, runner_sha256, layout_sha256,
              networks, secrets_root},
 rows: [12 x {operation, target, target_kind, slot, lot, plan_sha256, budget_seconds,
              generator_row, generator_row_sha256, generator_timeout_seconds,
              timeout_rule (MIN_GENERATOR_BUDGET_MINUS_65 | CAPTURE_GENERATOR_KILL_KEPT), derivation, timeout_seconds,
              timeout_changed, changes [[field, old, new], ...], row, row_sha256,
              transport {effect_kind CONTAINER, engine_mode ATTACHED, engine_sha256, inner_kill_seconds,
                         docker_margin_seconds 20, effect_floor_seconds, argv}}]}
```

`row_sha256` is the K9 decoder's provenance binding and must be the registry's `effect_sha256` (writer:
`REAL_K9_POLICY_EFFECT_NOT_THE_DERIVED_ROW`; runtime: `K9_REAL_REGISTRY_OPERATION_NOT_SIGNED`). Timeouts (unchanged
from v3.1): prove/commit/publish 565 → 535, collect 865 → 835, components 2365 → 2335, sources 4465 → 4435,
preflight 265 → 235, acquire 4165 → 4135, execute 1165 → 1135, bind 35, stage 20, capture 655 (kept).

### 3.5 GO form

Installed paths `k9/K9_GO_04.json`, `k9/K9_GO_04.PUBLICATION.json`, `k9/VERIFIER_POLICY_04.json` are the runtime's
names (test `test_go_form_installed_paths` compares them with the Codex form read-only when present). The writer checks
the publication's 14 form keys, schema, GO binding, equal times and body hashes; the GO's own form is left to the Codex
verifier at use (open item).

## 4. Runs (macOS, this build; temp outside ~/Documents: the system temp dir under /var/folders)

All on the sealed family `4108eb7b8003df12ebff1a7828b204f0c58c3b26382f13a908e5d51f92071e44` (read before and after every run, unchanged). First set: both Pythons
concurrently (14:23–14:48 UTC = 11:23–11:48 BRT), three full runs each, every run = the four suites in sequence
(`evidence/v33f/probes/run_suites_v33f.py` v1 `eebc8959…`). Python 3.12 run 3 had ONE failure in the unchanged
`tests/test_l12host.py`: `Review.test_extended_ceiling_kills_the_group_and_is_uncertain` (an UP FIXTURE extended step
whose gate hangs until the 70 s ceiling; timing / group-cleanup class; a non-physical UP path where none of the
v3.3f runtime additions run: they are physical-only or the DOWN session rows); the v1 harness kept no traceback. The test then passed 4/4 when run four at a time, and a second set of three full runs on
Python 3.12 alone (14:51–15:15 UTC = 11:51–12:15 BRT, harness v2 which keeps failure excerpts) passed 3/3:
run 1: test_l12host.py 81/0/0/1, test_lots_patch_v34.py 17/0/0/0, test_v33.py 14/0/0/0, test_v33f.py 15/0/0/0; run 2: test_l12host.py 81/0/0/1, test_lots_patch_v34.py 17/0/0/0, test_v33.py 14/0/0/0, test_v33f.py 15/0/0/0; run 3: test_l12host.py 81/0/0/1, test_lots_patch_v34.py 17/0/0/0, test_v33.py 14/0/0/0, test_v33f.py 15/0/0/0 (tests/failures/errors/skipped; all_ok True, family seal unchanged True).

| Check | Python 3.12.14 (venv) | Python 3.9.6 (/usr/bin) |
|---|---|---|
| `tests/test_l12host.py` | 2/3 runs ok; 81 tests, 0 failures, 0 errors, 1 skipped; 81 tests, 1 failures, 0 errors, 1 skipped | 3/3 runs ok; 81 tests, 0 failures, 0 errors, 1 skipped |
| `tests/test_lots_patch_v34.py` | 3/3 runs ok; 17 tests, 0 failures, 0 errors, 0 skipped | 3/3 runs ok; 17 tests, 0 failures, 0 errors, 0 skipped |
| `tests/test_v33.py` | 3/3 runs ok; 14 tests, 0 failures, 0 errors, 0 skipped | 3/3 runs ok; 14 tests, 0 failures, 0 errors, 0 skipped |
| `tests/test_v33f.py` | 3/3 runs ok; 15 tests, 0 failures, 0 errors, 0 skipped | 3/3 runs ok; 15 tests, 0 failures, 0 errors, 0 skipped |
| `per run` | 7.8-7.9 min; family seal unchanged: True | 8.2-8.6 min; family seal unchanged: True |
| `build_specs.py validate` (in-family) | output `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610` (v3.3: `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610`) | `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610` |
| `gen_k9_plans04.py check --grid D` | output `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302` (v3.3: `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302`) | `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302` |
| `verify_family.py` | SEAL_EXACT, 58 files, 15 pins, seal 4108eb7b… | SEAL_EXACT, 58 files, 15 pins |
| mutation checks (`probes/mutants_v33f.py`, scratch copies, `test_v33f.py`) | 25/25 killed | 25/25 killed |

The Codex R2 verifier (`0e7ce65e74dc9074ed9d3fc1724a5f57271d4503da353c85f964cd40822508e5`) and the GO form were read READ-ONLY by two tests (AST / one key); on CI they skip.

Evidence (`evidence/v33f/`):

| File | sha256 |
|---|---|
| `evidence/v33f/MUTANTS_V33F_PY312_DARWIN.json` | `40f131095f990d1419f86ab5e52fe43649ada3a3147ae1dde9dff9b5f4b5453d` |
| `evidence/v33f/MUTANTS_V33F_PY39_DARWIN.json` | `66380b5c5922c9d224ce5212a5616fd7872e275f2ab358455f9fbb88e4262b1c` |
| `evidence/v33f/V33F_TEST_NAMES_PY312_DARWIN.txt` | `98e394efdb3f2bb51b67da5c59de251be061c58a6ab4cd832ecc59636ac0bf5b` |
| `evidence/v33f/V33F_TEST_NAMES_PY39_DARWIN.txt` | `1d7f3cc0771882c8b027f1b800c95cb1db4b28490041ecc22ed4044b5c7b8784` |
| `evidence/v33f/V33F_TEST_RERUN_PY312_DARWIN.json` | `05281cea5ae420f35a123b5b14a768aa6860ff31dac562b59e7340bc1b34725d` |
| `evidence/v33f/V33F_TEST_RUNS_PY312_DARWIN.json` | `05e2f6ec0ac79ae60ccda2eeec1db15f5375fa3204403ccfa43d4ba0f764b1ae` |
| `evidence/v33f/V33F_TEST_RUNS_PY39_DARWIN.json` | `eab30319345e56b6004692c0c20291b4196e2a5119f1cd875bb0dfa0906d8e6e` |
| `evidence/v33f/checks/GEN_CHECK_D_PY312.txt` | `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302` |
| `evidence/v33f/checks/GEN_CHECK_D_PY39.txt` | `238df1a19738c89ac8b5b8a58412de329f5e917fc202fc52b860951052787302` |
| `evidence/v33f/checks/SPECS_VALIDATE_PY312.json` | `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610` |
| `evidence/v33f/checks/SPECS_VALIDATE_PY39.json` | `4284c295510fd08ae0c5d2856c3b7254949fe0512b43f322613bf198d05ec610` |
| `evidence/v33f/checks/VERIFY_FAMILY_PY312.json` | `cf52e5d45675ff608fe13e3845f5791c7537a8d233ffd5c07d11e3c8a7713aaa` |
| `evidence/v33f/checks/VERIFY_FAMILY_PY39.json` | `cf52e5d45675ff608fe13e3845f5791c7537a8d233ffd5c07d11e3c8a7713aaa` |
| `evidence/v33f/probes/mutants_v33f.py` | `eba0bc5283104d1b4b224f621eb4940270bd8ccf8c92622175dd53183f3669cf` |
| `evidence/v33f/probes/run_suites_v33f.py` | `66d88d28f834ff0102579024d42532d115d44b2f026a993732be069cb41df8d7` |

## 5. Seals

- Family `l12host/SHA256SUMS`: `4108eb7b8003df12ebff1a7828b204f0c58c3b26382f13a908e5d51f92071e44` (58 files, 15 vendor pins, `verify_family.py` `SEAL_EXACT` on
  3.12.14 and 3.9.6). A W signed for v3.3 (`5c3f5f4f7d121846a61d1b33528b0163be4c70b29b534118a28fa9017efd1f05`) does not cover v3.3f.
- Top `SHA256SUMS` seals every file of this delivery including this one (its own hash is reported outside).

## 6. Open items

- Codex R2 `approval_check` takes the effect from `authority.effects[role]`; the DOWN `capture_launch` is an EXTENDED
  CAPTURE step whose row is `authority.extended.steps[...].effect`, so R2 as delivered would refuse the capture's
  approval (`K9_REAL_EFFECT_NOT_REGISTERED`). Codex to rule or patch (this family registers the extended row).
- Ordering: the registry's `effect_sha256` must equal the rows `kill-record` prints (D-NET networks, secrets root and
  KILL included); the REAL write needs the Codex-sealed verifier (the delivered empty allowlist is refused by design).
- The writer does not validate the GO's own form or the publication's author fields (left to the Codex verifier).
- The two pre-existing tests helpers changed (`test_lots_patch_v34.py`, `test_v33.py`): same test counts, D-NET names
  and synthetic REAL inputs; two refusal expectations re-targeted (the verifier is a flag now, not a value).
- The Linux proof has not run on v3.3f (no push from here); its UP lot now signs SYNTHETIC REAL K9 files and D-NET
  networks (offline physical bind tested). The REAL callback integration on the final sealed Codex bytes
  (ISOLATED_REAL_MODULE_LOAD, REAL_CALLBACK_INTEGRATION) needs its own run.
- `validate --out-dir` re-derives the KILL record with the layout it is given: use the layout of the write.
- The in-family DRAFT `_comment` texts are v3.1's (they still mention D-NET as pending); only network values changed.
- macOS timing / group-cleanup flakes under concurrent load: one `OUTER_GROUP_CLEANUP_UNCERTAIN` (vendored
  OuterLimiter; CONTRACT 0-bis C1) in a pre-seal smoke run, and one failure of
  `Review.test_extended_ceiling_kills_the_group_and_is_uncertain` in the sealed first set (section 4; reason not
  captured, not reproduced in 4 + 3 later runs). Both are in non-physical FIXTURE paths v3.3f does not touch; not
  addressed here.
- One earlier mutation pass (3.9, before the probe checked that every mutant parses) had one invalid mutant
  (`builder_act_b_pin_unchecked` produced a syntax error); fixed, and both recorded passes (3.12, 3.9) have 25/25
  parsing mutants killed.
