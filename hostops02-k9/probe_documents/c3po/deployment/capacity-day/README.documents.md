# Capacity day — the document tool

Offline candidate. Nothing built by this tool has been delivered to a host, signed, published in the channel or dispatched.

**Unverified on the host.** `capacity_day_documents.py` runs on the reviewer's machine and never touches a host, a container, a database or the network. Everything this document says about what happens to its output afterwards (delivery into the capacity tree, the roots at `/c3po-capacity`, the container that reads them, the host payload) comes from the code and from offline tests. None of it was observed on the production host or on a Docker engine. "Not verified" near the end lists it together.

The tool is a deployment script, **outside the pinned implementation package**: nothing under `c3po/backend/app` changes because of it and `implementation_package_sha` does not move. It imports the packaged code of the checkout it sits in and, before it writes a byte, passes the records, the view, the contract and the GOs through the packaged validators (the capacity config and the envelope are the exceptions, see "What is checked before a byte is written"). The tool can be corrected offline without a new release.

On the host the same package validates again **what it reads**, and a defect of the tool in any of that is a refusal at `prepare-capacity-day`: the config, the four pinned records, the view, both GOs, and in the contract `owner_sha`, `order`, `policy`, `template`, `causal_scope` and each plan's `status`, `proposal` and `proposal_sha` (plus `missing_bindings` of the admission plan). It does **not** read the other fields of a plan (`schema`, `execution_authorized`, `diff`, `missing_bindings` of a consumer plan, an extra key), an extra key beside `go` in a GO file, or the bytes of the contract and GO files as such. A reviewer's probe changed those one by one and the packaged code accepted each change. Nothing in the repository consumes those fields today. They are compared only here (`verify` requires every plan to be, in full, what the packaged assembler computes, and every JSON file to be canonical) and, for the contract, by the host delivery, which has to compare the contract's bytes with `documentary.contract_sha256` of the REQUEST because no packaged code will.

`README.md` in this directory describes `manifest_writer.py`, the script that reads these documents inside the container.

## Open decisions

Each one is an input or a switch. None is closed by this tool, and no input has a default: a missing value is a refusal.

| # | Decision | Where it enters the tool |
| --- | --- | --- |
| **D1** | Reader launcher accepted, or worker run directly | Nowhere. The documents are the same for either reader. Only the static config of `static-config` is read by the reader, and its bytes do not depend on which process reads it. |
| **D3** | Compose `r2d2-worker` run with capacity required | `static-config` writes one file. If the answer is yes, the compose worker reads **the same file by the same path and hash** as the reader (through its own read-only mount of the capacity tree); the tool does not write a second one. If no, nothing changes here. |
| **D4** | Veto view delivered the evening before, or emitted inside its window | `d4_view_mode`: `PRE_DELIVERED` or `IN_WINDOW`. The view bytes and the pin are identical in both modes. Only the place changes: `documents/` (delivered with the rest) or `emitter/` (handed to whoever writes it into the documents root at the view instant). |
| **D6** | Number and times of the windows per session | `d6_windows`: an ordered list, one entry per window, New York wall clock. One window is accepted, nine is the limit. The times are checked against the two phase windows, the cutoff and the writer's parking cap. |
| **D11** | Which document hashes fill `recertification_receipt_sha`, `wind_down_28_receipt_sha`, `input_receipts_sha`, and the windows of `quote_refresh` / `quote_capture` | The `d11` block: three hashes, and for each of the two phases either a window (`not_before`, `not_after`) or the digest of one (`phase_window_sha`). **Nothing can check these three hashes**: the packaged code requires a SHA-256 and commits whatever it is given, and two of them swapped are accepted here and on the host. The tool refuses only what typing or an empty command leaves behind (see "Hashes"). It also assumes one thing about the answer: the three slots are three different documents, and none of them is another object these inputs already name (release, package, chain documents, authority, …), except that a slot may equal the policy's `c8_receipt_sha` or `head_go_sha`. If D11 is closed otherwise, that one comparison in `check_epoch_inputs` changes. |
| **D12** | A day whose committed list is empty | Not an input. The tool recognises the digest of an empty list in `list_sha256`, builds the day and says so: `list` is `EMPTY` in its output line and in `SUMMARY.json`. On the host the admission is then committed with no symbol and the writer refuses the manifest (`README.md`, D12). Whether such a day is dispatched at all is not decided here. |
| **Order object** | What the object behind Act B's `order_sha` is, and what `owner_sha` is the hash of | The `order` input. **Nothing in the repository defines either.** The packaged code reads four keys of it (`owner_sha`, `epoch`, `authorized_sessions`, `capacity`) and requires `owner_sha` to be a SHA-256; the shape used by the tests comes from a test fixture. Act B's `order_sha`, every view and all four plans bind the digest of this object, so `templates` cannot run and Act B cannot be drafted until it is frozen: who authors it, what `owner_sha` hashes and which other keys it carries. Beyond the four keys the tool accepts only hashes, clocks and constants (see "Refusals"). |
| **Writer's GO mode** | Whether the dispatch tells the writer to require the delegated form of GO:bar_manifest (`--require-go-mode`, `README.md`) | `dispatch.writer_require_go_mode`: `DELEGATED_ACT_B` adds `--require-go-mode DELEGATED_ACT_B` to `writer_argv`; `NOT_REQUIRED` leaves the packaged rule. The day's documents are the same either way; only the REQUEST and its GO differ. |

## What the tool writes

One run of `day` writes the documents of **one session day and one window** into a new directory. The day's files are byte-identical whichever window is asked for; the window's files differ.

| File | What it is | Goes to |
| --- | --- | --- |
| `contract/session=<day>.contract.json` | The day's contract: `owner_sha`, `order`, `policy`, `template`, `causal_scope`, the admission plan and the three consumer plans (`bar_manifest`, `quote_refresh`, `quote_capture`), each with its ten bindings, computed by the packaged assembler. The list of the day is present only as `commitment_sha256` and `list_sha256`. | The host delivery, which assembles the payload file from it (see "The payload file"). |
| `documents/session=<day>.template.md` | The day's `TEMPLATE` record: the day's entry of `act_b.templates`, verbatim. | documents root |
| `documents/session=<day>.go-admission.md` and `go/session=<day>.admission.json` | GO:admission, mode `INDIVIDUAL`: the pinned record and the 13-field GO the loader reads. | documents root, go root |
| `documents/session=<day>.go-bar_manifest.md` and `go/session=<day>.bar_manifest.json` | GO:bar_manifest, mode `DELEGATED_ACT_B`: record and GO. | documents root, go root |
| `documents/session=<day>.publication-bar_manifest.md` | The publication record of GO:bar_manifest. Its SHA-256 is the `publication_receipt_sha` inside that GO. | documents root |
| `documents/session=<day>.view-<window>.md` (or `emitter/…` with `IN_WINDOW`) | The veto view of the window: `VERIFIED`, no veto, no revocation, `observed_at` = the instant the view opens, `valid_until` = that plus `view_valid_seconds`. | documents root, the evening before or at the view instant (D4) |
| `config/session=<day>.<window>.capacity.json` | The window's capacity config: identity, calendar pin, release and package hashes, the three root pins, the eleven document pins (seven chain documents and the four records above) and the day's view pin. | config root |
| `envelope/session=<day>.<window>.request.json`, `…go.json` | Dispatch REQUEST and GO for operation `GO_CAPACITY_DAY_03`. **Proposed shape: no code in this repository reads either file.** They carry the config path and hash, the clocks, the writer's arguments and the hashes of every document above. | the dispatcher (Codex's side) |
| `SUMMARY.json` | Index of the directory: role of each file, every hash a GO text needs, the clocks in UTC, whether the list is empty, the calendar line given as input, the hashes of the two input files and of the tool itself, and what the self-check did and did not check. `verify` rebuilds all of it from the other files, except the two input hashes. | stays with the reviewer |
| `SHA256SUMS` | One line per file. Its own SHA-256 names the whole set. | stays with the reviewer |

The day's files are delivered once. A second or third window of the same day adds only its own view and config to the capacity tree (and its own envelope to the dispatcher): the delivery creates files exclusively, and the other files of that window's directory are the ones already there, byte for byte.

Every JSON file is canonical (sorted keys, compact, no trailing newline). Two runs with the same inputs give the same bytes.

**Instrument symbols.** The session inputs cannot carry the list: two hashes stand for it and the key set is closed (see "The payload file"). The two objects that are copied whole into the contract, `order` and `policy`, are the only place where someone could put names, a secret or an account value. Beyond the keys the packaged code reads, the tool accepts in them only hashes, clocks, dates, constants with an underscore, booleans and null, and no list (see "Refusals"). That is a restriction of shape, not a proof about meaning.

`templates` writes `ACT_B_TEMPLATES.json`: the five-day map (`template_shas`, `templates`, `template_set_sha`, `cut_rule`, `order_sha`) that Act B has to carry for these documents to be accepted, plus the five contract templates. `static-config` writes `config/week.static.capacity.json` from its own, smaller input file (see "The static config").

An output file authorises nothing by itself. The records are written in the `ISSUED` state because the packaged parser accepts no other; they acquire authority only when a capacity config pins their hashes and an authorised dispatch names that config's hash.

## Who signs or publishes what, and when

All of it is authored by Fable on the **evening before** the session, after that day's causal list is committed (Sunday evening for Monday), and delivered by Codex under the five-session authority with Fable's GO by hash. Nothing here is signed by the owner per day.

| Document | Signature or publication | When |
| --- | --- | --- |
| `ACT_B_TEMPLATES.json` | Not signed itself. Its content is copied into Act B, which Codex, Fable and the owner sign. | Weekend, before Act B is drafted |
| `week.static.capacity.json` | Fable's GO by hash for its delivery; its hash enters `pins.env`. The hash of `pins.env` is in turn an input of `day` (`dispatch.pins_env.sha256`), which is why `static-config` does not read the epoch inputs. | Weekend, once the chain documents, the release hash and the root identities exist |
| `TEMPLATE` record | None of its own: the authority is Act B. | Evening before |
| GO:admission (record and GO file) | Fable's individual GO. The plan declares Fable's per-day dispatch GO to be the individual GO for admission; the dispatch GO written here carries `admission_go_sha256` for that reason. | Evening before |
| GO:bar_manifest (record, GO file, publication record) | Fable, delegated under Act B. **Published in the channel** at the instant given as `bar_manifest_published_at`; the code requires that instant to be at least 15 minutes before the phase window opens. | Evening before |
| Veto view | Authored by Fable ahead of its own `observed_at`. It states "no owner veto and no revocation"; the owner's veto is exercised by withdrawal of the dispatch (D4). | Authored the evening before; delivered then, or emitted at the view instant |
| Window capacity configs (one per window) | None of their own: each hash is named by its dispatch REQUEST. | Evening before, all windows of the day |
| Contract | None of its own: every GO binds the hash of one of its plans. | Evening before |
| Dispatch REQUEST and GO | Fable publishes the hash of the GO; the GO file says `UNSIGNED` and is nothing until then. | Evening before, one pair per window |

`bar_manifest_published_at` is fixed before the build, because the bytes carry it. The publication is then made at that instant; if it slips, the day is built again with the real instant. No code can see the channel: a record whose instant is not the real one is a false record that every validator accepts.

## Inputs

Three JSON files, each read by its own command. Each has a fixed key set: a missing or an unknown key is a refusal. Values are strings, integers, booleans, lists and objects in printable ASCII; a number with a fraction is refused. An input file that is a symbolic link is refused.

| File | Schema | Read by |
| --- | --- | --- |
| Static inputs, once | `R2D2_CAPACITY_DAY_STATIC_INPUTS_V1` | `static-config` |
| Epoch inputs, one file for the five sessions | `R2D2_CAPACITY_DAY_EPOCH_INPUTS_V1` | `day` |
| Session inputs, one file per session day | `R2D2_CAPACITY_DAY_SESSION_INPUTS_V1` | `day` |

The **static inputs** are the eleven keys marked **S** below and nothing else: what a capacity config is made of. They can all exist on the weekend. The **epoch inputs** are the same eleven, with the same values, plus six more: the ones that exist only later (the policy and its hash, D11, D4, the dispatch facts) and `act_b_sha256`, which repeats a chain pin. `static-config` refuses an epoch inputs file (`DOCUMENTS_STATIC_FIELDS`): it never asks for a value that does not exist yet, so nobody has to invent one to run it.

### Epoch inputs and static inputs

| Key | | Content | Exists |
| --- | --- | --- | --- |
| `schema` | S | the constant of the file | now |
| `order` | S | The object whose digest is Act B's `order_sha` (see "Open decisions"). It must carry `owner_sha`, `epoch`, `authorized_sessions` (the five sessions) and `capacity` 550. Any other key is lowercase and holds a hash, a clock, a date, a constant with an underscore, a boolean, null or an object of those. | when the order object is frozen |
| `policy` | | The body of the live policy (`R2D2_V2_LIVE_POLICY_V1`, mode `LIVE`). A policy with a `symbols` key is refused. Its twelve known keys are checked by the packaged policy check when the plans are computed; `c8_receipt_sha` and `head_go_sha` also pass the placeholder check. Any other key is restricted like the order's. | after the weekend |
| `policy_sha` | | Digest of `policy` as the assembler computes it: SHA-256 of its canonical JSON. This is **not** necessarily the SHA-256 of the installed policy file; the two are equal only if that file is the canonical JSON itself. | after the weekend |
| `release_sha` | S | SHA-256 of the installed release file. For `day` it must equal `policy.release_sha`. | on the weekend |
| `package_sha` | S | `implementation_package_sha` of the final head. Must equal **the package of this checkout** (run the tool from a checkout of the deployed revision) and, for `day`, `policy.package_sha`. | after the final head |
| `calendar_pin_receipt` | S | The whole line printed by the calendar-pin script **inside the pinned image** (see "The calendar pin"): `status`, `epoch`, `calendar_version`, `calendar_pin_sha`, `package_sha`, `document_order_sha`. Every field must equal what this interpreter computes. | after the deploy |
| `act_b_sha256` | | SHA-256 of the Act B document. Must equal `chain_pins.ACT_B.sha256`. | after Act B is signed |
| `chain_pins` | S | File name and SHA-256 of the seven chain documents as delivered into the documents root: `CODEX`, `FABLE`, `DUDU`, `ACT_B`, `B_CODEX`, `B_FABLE`, `B_DUDU`. | after Act B is signed |
| `capacity_roots` | S | `config`: `path`. `documents`, `payload`, `go`: `path` and `identity`. Paths are the **container** paths. The identities are the ones printed in two containers by the host rehearsal. | after the host rehearsal |
| `d11` | | `recertification_receipt_sha`, `wind_down_28_receipt_sha`, `input_receipts_sha`, `quote_refresh`, `quote_capture` (D11). | when D11 is closed |
| `phase_windows` | S | `admission` and `bar_manifest`, each `not_before` and `not_after`, New York wall clock `HH:MM:SS`. | now (plan: 06:15:00 to 09:20:00) |
| `d4_view_mode` | | `PRE_DELIVERED` or `IN_WINDOW` (D4). | when D4 is closed |
| `d6_windows` | S | List of `name` (lowercase), `start_not_before`, `view_opens_at`, New York wall clock (D6). | when D6 is closed |
| `view_valid_seconds` | S | Life of a view, 1 to 10. The packaged reader refuses more than 10. | now (plan: 10) |
| `max_wait_seconds` | S | The writer's `--max-wait-seconds`, 1 to 900. A window whose view opens later than this after `start_not_before` is refused. | now (plan: 900) |
| `dispatch` | | Host and authority facts for the envelope, below. | after the weekend |

`dispatch`:

| Key | Content |
| --- | --- |
| `authority_sha256` | SHA-256 of the owner-signed five-session authority. |
| `payload_sha256` | SHA-256 of the host payload bytes Codex accepted. |
| `writer_sha256` | SHA-256 of `manifest_writer.py` as authorised. |
| `writer_require_go_mode` | `DELEGATED_ACT_B` or `NOT_REQUIRED` (see "Open decisions"). |
| `image_id` | `sha256:<64 hex>`, read on the host after the deploy. |
| `build_sha` | The 40-hex revision. Must equal `policy.code_revision`. |
| `network` | The compose network that reaches the database. `host` and `none` are refused. |
| `host_binding_sha256` | The dispatcher's host binding. |
| `pins_env` | `path` and `sha256` of the reader's `pins.env`. That file carries the hash of the static config, so this value exists only after `static-config` has run and `pins.env` has been written. |
| `secret_env_path` | Path of the reader's `secret.env`. **A path only.** The tool never reads that file and has no input for its content. |
| `docker_config` | The empty docker CLI configuration directory. |
| `mounts` | List of `source`, `target`, `readonly`. Exactly one writable mount, whose target is `manifest_directory`; every capacity root must lie under a read-only target. For this epoch the list has four entries: the data volume, the producer's journal root at the producer unit's container path, the capacity tree and the manifest directory (`README.md`, "What the host payload must provide"). A writable journal bind is refused like any second writable mount. **The tool cannot tell whether the journal bind is present or names the right directory**: the journal directory is a line of `pins.env`, of which the tool has only the hash. That comparison is the host payload's. So are the checks of the journal's filesystem, owner and mode: the REQUEST and the dispatch GO carry only `source`, `target` and `readonly` for a mount, with no field for a filesystem line or a device number, so the expected values are in the payload bytes (bound by `payload_sha256`) or in the document behind `host_binding_sha256`, which this directory does not define (`README.md`, "The journal bind"). |
| `manifest_directory` | Container path of the manifest directory. |

### Session inputs (`R2D2_CAPACITY_DAY_SESSION_INPUTS_V1`), one file per session day

| Key | Content | Exists |
| --- | --- | --- |
| `schema` | the constant above | now |
| `day` | The session date, one of the five. | now |
| `causal_scope` | `commitment_sha256` and `list_sha256` of that day's committed causal list, copied from its publication record (the public fields of `V2_CAUSAL_LIST_PUBLICATION_V1`). **Two hashes; never the list.** A `list_sha256` equal to the digest of an empty list is accepted and reported (D12). | each evening, after the list is committed |
| `bar_manifest_published_at` | UTC instant `YYYY-MM-DDTHH:MM:SS+00:00` at which GO:bar_manifest is published. Between 15 minutes and 4 days before the phase window opens. | each evening |
| `view_evidence_sha` | One SHA-256 per window name: the `evidence_sha` of that window's view. Which document that is the hash of is for the signatories; the code requires a SHA-256 and nothing else. | each evening |

### Inputs that only exist after the weekend

The release hash, the policy and the policy hash, the package hash of the final head, the Act B hash with the seven chain pins, the capacity root identities, the calendar line read in the image, the image ID, the hash of `pins.env`, the authority hash, the payload and writer hashes and the host binding. Until all of them exist no day can be built. In order:

1. `templates` needs only the order and can run as soon as the order object is frozen.
2. `static-config` needs the static inputs: the release hash, the package hash, the calendar line, the seven chain pins and the root identities.
3. `pins.env` is written with the hash `static-config` printed. Only then does `dispatch.pins_env.sha256` exist.
4. `day` needs everything, each evening, with that day's hashes.

### Hashes

**Hashes are produced by command and pasted, never typed.** Two checks stand behind that rule, and both are narrow:

- A value is refused (`DOCUMENTS_INPUT_<NAME>`) if it has fewer than five distinct hexadecimal digits (`aaaa…`, `0000…0001`), if it is one block repeated (`deadbeef…`, `0123456789abcdef…`), or if it is the SHA-256 of no input or of an empty JSON value (`[]`, `{}`, `null`, `""`, each with or without a final newline), which is what a pipeline prints when the file it was meant to hash was absent.
- One value in two slots that name different things is refused (`DOCUMENTS_INPUT_HASH_REUSED`): the release, the package, the calendar pin, the two order hashes compiled into the package, the seven chain documents, the three root identities, the policy and its two receipts, the authority, the payload, the writer, the host binding, `pins.env`, the image, this tool's own file, the three D11 slots (with the exception stated under D11), a quote window digest, and the day's commitment and list hashes.

**No check can tell a wrong hash that looks real from the right one.** A hash of the wrong file, two real hashes swapped between two slots, or a made-up value with ordinary digits pass both checks. `view_evidence_sha` passes the first check only: the same evidence may serve several windows, and what it is evidence of is for the signatories. The synthetic values of the repository tests are of that kind (each is the SHA-256 of a label) and are accepted by design.

## The calendar pin

Every config and every plan carries the calendar pin: a digest of the session details of the five days **and of the version string of the calendar library**. The package hash does not cover that library, and `backend/requirements.txt` allows a range of versions (`exchange-calendars>=4.13,<5`). A reviewer's machine with another version computes another pin; every document would then be refused in the container, `CAPACITY_CONFIG_CALENDAR` at the config load. The tool therefore takes the line printed in the image as an input (`calendar_pin_receipt`) and compares every field of it with what its own interpreter computes: another package, epoch or order is `DOCUMENTS_CALENDAR_RECEIPT`, another library version or pin is `DOCUMENTS_CALENDAR_PIN`. The line is recorded in `SUMMARY.json`.

**Where the line came from cannot be checked offline.** A line computed on the reviewer's machine satisfies the comparison by construction, and the tool cannot tell it from one printed in the image; `SUMMARY.json` says so (`calendar_pin`: `EQUAL_TO_LOCAL_PROVENANCE_NOT_CHECKED`). `templates`, which needs only the order, prints no pin, so the tool never hands out the value it later asks for. The proof that the image computes this pin is on the host: the run below, and the rehearsal that loads the static config in the image.

The line is read once, after the deploy, by one run of the pinned image with no mount and no network, the script on standard input:

```
shasum -a 256 calendar-pin.py
DOCKER_CONFIG=<docker cli dir> docker run --rm -i --pull never --init --user 0:0 --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges <IMAGE_ID> python -I -B - < calendar-pin.py
```

`calendar-pin.py` is exactly the lines between the two markers, each ended by a newline. Its SHA-256 is `5a6066ae2925453a0def335d8f8ac7e802e149b56cf9e61ea3fe8843fe582b5f`. A repository test extracts these lines, checks that hash and executes them against the real modules. The hash that binds a run is the one in its authorisation.

<!-- calendar-pin-script:begin -->
```python
import json, sys
APPLICATION_ROOT = '/app'
sys.path.insert(0, APPLICATION_ROOT)
try:
    from app.r2d2_v2_calendar import ShadowCalendar
    from app.r2d2_v2_capacity_authority import calendar_pin
    from app.r2d2_v2_earnings_package import implementation_package_sha
    from app.r2d2_v2_epoch_assembler import DOCUMENT_ORDER_SHA, EPOCH, SESSIONS
    calendar = ShadowCalendar()
    receipt = {'status': 'CALENDAR_PIN', 'epoch': EPOCH, 'calendar_version': calendar.version,
               'calendar_pin_sha': calendar_pin(calendar, {'authorized_sessions': list(SESSIONS)}),
               'package_sha': implementation_package_sha(), 'document_order_sha': DOCUMENT_ORDER_SHA}
except Exception as error:
    print(json.dumps({'status': 'CALENDAR_PIN_REFUSED', 'code': type(error).__name__}, sort_keys=True))
    raise SystemExit(1)
print(json.dumps(receipt, sort_keys=True))
```
<!-- calendar-pin-script:end -->

The line it prints holds the pin, the library version, the package hash of the image and the order hash compiled into it: the same run confirms `package_sha`. It reads no file outside the image and no environment. This run was not executed in a container anywhere *(unverified)*. A wrong pin fails closed in the container (`CAPACITY_CONFIG_CALENDAR` at the config load): the cost of a pasted local line is a refusal on the host, not a wrong acceptance.

## Command lines

Run from the repository root of a checkout at the deployed revision, with the interpreter of the backend environment (the one that has the backend requirements installed). `-I` keeps the environment and the current directory out of the import path; the tool adds the backend directory of its own checkout (`APP_ROOT`, the single constant near its top) and refuses (`DOCUMENTS_APP_ROOT`) if the `app` package it imported came from anywhere else.

The input files and the output are the reviewer's private working files. Keep them **outside the checkout** (nothing in `.gitignore` covers them) in a private directory, here `$WORK`. The tool creates only the last component of an output path: the parent must exist.

```
WORK=<a private directory outside the checkout>
mkdir -m 700 "$WORK/OUT"

# once, before Act B is drafted
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py templates \
  --order-file "$WORK/ORDER.json" --output-directory "$WORK/OUT/act-b-templates"

# once, on the weekend: the reader's static config
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py static-config \
  --static-inputs "$WORK/STATIC.json" --day 2026-10-05 --window primary \
  --view-evidence-sha <64 hex> --output-directory "$WORK/OUT/static"

# each evening, once per window of the next session
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py day \
  --epoch-inputs "$WORK/EPOCH.json" --session-inputs "$WORK/2026-10-05.json" --window primary \
  --output-directory "$WORK/OUT/2026-10-05.primary" --chain-directory "$WORK/CHAIN"

# at any time: re-check a directory that was written earlier
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py verify \
  --directory "$WORK/OUT/2026-10-05.primary" --chain-directory "$WORK/CHAIN"

shasum -a 256 "$WORK/OUT/2026-10-05.primary/SHA256SUMS"
(cd "$WORK/OUT/2026-10-05.primary" && shasum -a 256 -c SHA256SUMS)
```

- `--output-directory` must not exist (`DOCUMENTS_OUTPUT_EXISTS`) and its parent must (`DOCUMENTS_OUTPUT_PARENT`). The tool creates it (0700, files 0600) and never writes into an existing one.
- `--chain-directory` is a directory holding the seven chain documents under the file names of `chain_pins`. Each file is hashed against its pin and the day's GOs are verified by the packaged documentary authority over the real signed chain. `day` **requires** it. A reviewer's probe showed why: without the chain the tool wrote a complete directory for two chain pins swapped, for an order or a policy other than Act B's and for another release, all of which the host refuses.
- `--draft-without-chain` takes the place of `--chain-directory` for a build before the chain exists. The line and `SUMMARY.json` then say `documentary_authority` `NOT_CHECKED`. **Only a directory whose line says `documentary_authority` `VERIFIED` may be delivered**; the delivery GO text should say so.
- Standard output is one JSON line whatever the arguments: `status` (`WRITTEN`, `VERIFIED`, `REFUSED`, `UNVERIFIED`), on success the day, the window, the file count, the SHA-256 of `SHA256SUMS` and of the capacity config, `list` (`EMPTY` or `NOT_EMPTY`) and `documentary_authority`, and on a refusal a constant `code`. Exit 0, 3 (refused) or 1 (unverified). No path, no input value and no exception text is printed; a wrong argument is `DOCUMENTS_ARGUMENTS_INVALID`, never the argument itself. There is no help text (`-h` is a wrong argument) and no abbreviated option.

## The static config

The long-running reader (and the compose worker, if D3 is yes) uses one capacity config for the week. Restoring a committed binding reads only the Act A and Act B chains, but the packaged config loader refuses a config without a `TEMPLATE` pin and without at least one view pin. `static-config` therefore pins the seven chain documents, the `TEMPLATE` record of one anchor day and the view of one anchor window. Those two extra files do not have to exist when the config is loaded (the loader checks the shape of a pin, not the file), and the bytes of both are the ones `day` later writes for that day and window **if the same `--view-evidence-sha` is used**; a repository test compares them.

`static-config` reads the static inputs file and nothing else. The `dispatch` block, `d11`, D4, the policy and the Act B hash are not among its inputs, because several of them cannot exist when it runs: `pins.env` carries this config's hash, so the hash of `pins.env` is known only afterwards, and the five-session authority is signed later still. The values the two files share (the eleven keys) must be the same in both; nothing compares the two files, but a config built from other values has another hash, and the hash is what `pins.env` and each REQUEST name.

## The payload file

The loader reads `session=<day>.json` from the payload root: `{"contract": …, "causal": …}`, where `causal` carries the day's ordered list. **This tool does not write that file and cannot**: it never receives the list. It is assembled on the host, by the delivery, from the committed causal-list file and `contract/session=<day>.contract.json`. The delivery must refuse unless the list's own hash and the commitment hash equal the contract's `causal_scope`, and unless the bytes of the contract file it was handed hash to `documentary.contract_sha256` of the day's REQUEST (the packaged code does not read every field of a plan, see the top of this document); its receipt carries no symbol. That payload is Codex's side and is not in this repository.

`list_sha256` is the SHA-256 of the canonical JSON of the ordered list and `commitment_sha256` the digest of the commitment object, as `r2d2_v2_causal_list.py` computes them (lines 197 and 236–238); the packaged contract check recomputes the first from the list in the payload file. That the published record of a real day carries exactly these two values was read from the code, not from a host record.

## What is checked before a byte is written

`day` builds everything in memory and then runs, on those bytes:

- the packaged `normalize_document` on the four records and the packaged `PinnedVetoReader` on the view: accepted at the instant it opens and one microsecond before it closes, refused one microsecond earlier and at `valid_until`;
- the packaged `validate_contract` on the contract, with an empty stand-in for the list. With a list that is not empty it **must** pass every check and fail at the last one (`CAPACITY_CAUSAL_BINDING`), which only the host can complete; passing is a refusal (`DOCUMENTS_SELF_CHECK_CONTRACT`). With an empty list (D12) the same call must pass completely, and `SUMMARY.json` says `VALIDATED_WITH_EMPTY_LIST`;
- the packaged assembler again: each of the four stored plans must equal, in full, the plan computed from its own bindings (`DOCUMENTS_SELF_CHECK_PLANS`);
- the packaged `validate_go` on both GOs against their plans, at the view instant;
- with `--chain-directory`: the packaged `DocumentAuthority` (`act_b`, `check_binding`, `verify_go`) over the real chain documents, the four records and the view;
- its own comparisons, which are necessary conditions of the packaged `verify_go` and need no chain: each GO against its record, the `TEMPLATE` record and the publication record; every pin in the config against the bytes it pins; every JSON file canonical, and nothing beside `go` in a GO file;
- the envelope: the REQUEST and the dispatch GO must be, field for field, what the tool writes from the documents (day, epoch, window, config file and hash, the four inline environment values, the clocks, the writer's arguments, the twelve documentary hashes) and from the host facts the REQUEST itself states, which are checked for shape only;
- the index: day, window, roles, hashes and clocks are rebuilt from the files and must equal what the builder recorded (`DOCUMENTS_SELF_CHECK_INDEX`);
- the tripwire for instrument-shaped strings (see "Refusals").

`verify` reads `SHA256SUMS`, requires the directory to hold exactly the listed files with the listed hashes, as regular files (a symbolic link is refused), and runs the same checks again on a `day` directory. It then rebuilds `SUMMARY.json` from the other files and from the running tool and requires the stored bytes to be equal (`DOCUMENTS_SUMMARY_MISMATCH`; a directory written by another version of the tool is `DOCUMENTS_SUMMARY_TOOL`). A directory whose `SUMMARY.json` says `documentary_authority` `VERIFIED` is verified over the chain again or refused (`DOCUMENTS_CHAIN_REQUIRED`).

**What `verify` cannot tell**, and names in its line:

- `inputs` `NOT_COMPARED`: the hashes of the two input files in `SUMMARY.json` are taken as stated. The inputs are not at hand.
- The host facts: in the envelope the image, the network, the mounts, the two environment files, the docker directory, the authority, payload, writer and host binding hashes, the window's position and its start; in the config the paths and identities of the three roots. They come from the inputs and from nowhere else; a directory in which one of them was changed, with every hash that depends on it carried along and `SHA256SUMS` written again, is `VERIFIED`.
- Therefore the comparison that binds a directory to a build is the reviewer's: `sha256sums_sha256` of the `verify` line against the line the build printed. The complete check, when the inputs are at hand, is to build again into a new directory and compare the two `sha256sums_sha256`; the bytes are deterministic.
- On a `templates` or `static-config` directory `verify` can only compare the listing and the tool's hash, and its line says so (`content` `LISTING_ONLY`).

Not checked by the tool: the packaged `CapacityConfig` is **not** loaded, because it opens the real roots and compares their identities, which only exist on the host. The repository tests load it, on temporary roots.

## Refusals

A refusal prints one line with a constant code and writes nothing. Codes that start with `DOCUMENTS_` are the tool's own; any other code is the packaged validator's, passed through unchanged (for example `POLICY_NOT_EPOCH_WIDE`, `DOCUMENT_BINDING`, `AUTHORITY_UNVERIFIED_OR_VETOED`).

| Code | Meaning |
| --- | --- |
| `DOCUMENTS_STATIC_FIELDS`, `DOCUMENTS_EPOCH_FIELDS`, `DOCUMENTS_SESSION_FIELDS` | A key of the input file is missing or unknown (for example an epoch inputs file given to `static-config`). `DOCUMENTS_STATIC_SCHEMA`, `DOCUMENTS_EPOCH_SCHEMA`, `DOCUMENTS_SESSION_SCHEMA`: the `schema` is not the file's constant. |
| `DOCUMENTS_INPUT_<NAME>` | That input is missing, malformed, or a placeholder hash (see "Hashes"). |
| `DOCUMENTS_INPUT_HASH_REUSED` | One hash in two slots that name different things. |
| `DOCUMENTS_FREE_FORM_KEY`, `DOCUMENTS_FREE_FORM_VALUE` | The order or the policy holds, beyond its known keys, a key that is not a lowercase name, or a value that is not a hash, a clock, a date, a constant with an underscore, a boolean, null or an object of those. A list, a number and any other text are refused. |
| `DOCUMENTS_INPUT_JSON`, `DOCUMENTS_INPUT_NOT_ASCII`, `DOCUMENTS_INPUT_TYPE`, `DOCUMENTS_INPUT_FILE` | The file is not strict JSON (duplicate key, fraction, non-finite), holds a non-ASCII or control character, an unsupported value, or cannot be read (absent, not a regular file, a symbolic link, larger than 1 MiB). |
| `DOCUMENTS_PACKAGE_MISMATCH`, `DOCUMENTS_CALENDAR_RECEIPT`, `DOCUMENTS_CALENDAR_PIN`, `DOCUMENTS_APP_ROOT` | The checkout, the image line or the interpreter is not the one the documents are for. |
| `DOCUMENTS_POLICY_HASH`, `DOCUMENTS_POLICY_SCOPE`, `DOCUMENTS_ORDER_SCOPE`, `DOCUMENTS_ACT_B_HASH`, `DOCUMENTS_BUILD_REVISION` | Two inputs that must agree do not. |
| `DOCUMENTS_DAY_NOT_AUTHORIZED`, `DOCUMENTS_WINDOW_UNKNOWN` | Not one of the five sessions; not one of the `d6_windows`. |
| `DOCUMENTS_ADMISSION_WINDOW_LATE`, `DOCUMENTS_VIEW_OUTSIDE_PHASE_WINDOW`, `DOCUMENTS_VIEW_AFTER_CUTOFF`, `DOCUMENTS_WINDOW_WAIT`, `DOCUMENTS_WINDOWS_OVERLAP`, `DOCUMENTS_PHASE_WINDOWS_NOT_DISTINCT`, `DOCUMENTS_GO_NOTICE` | Clocks the packaged code or the writer would refuse: admission opening after the open, a view outside a phase window or after open minus 10 minutes, parking longer than `max_wait_seconds`, overlapping windows, two phases with one window digest, a publication less than 15 minutes (or more than 4 days) before the window. |
| `DOCUMENTS_DISPATCH_WRITABLE_MOUNT`, `DOCUMENTS_DISPATCH_CAPACITY_MOUNT` | The mounts are not "manifest directory writable, everything else read-only, capacity roots under a read-only mount". |
| `DOCUMENTS_CHAIN_FILE`, `DOCUMENTS_CHAIN_HASH`, `DOCUMENTS_CHAIN_REQUIRED` | A chain document is absent from `--chain-directory`, or its bytes are not the pinned ones; `verify` was run without the chain on a directory that says `VERIFIED`. |
| `DOCUMENTS_SELF_CHECK_…`, `DOCUMENTS_DIGEST_NAMESPACE`, `DOCUMENTS_PLAN_UNBOUND` | The tool's own output failed one of its comparisons: a defect of the tool (or, under `verify`, a directory that was changed). |
| `DOCUMENTS_SYMBOL_SHAPED_VALUE` | The tripwire, below. |
| `DOCUMENTS_OUTPUT_EXISTS`, `DOCUMENTS_OUTPUT_PARENT` | The output directory exists; its parent does not. |
| `DOCUMENTS_SUMS_…`, `DOCUMENTS_SUMMARY_SCOPE`, `DOCUMENTS_SUMMARY_TOOL`, `DOCUMENTS_SUMMARY_MISMATCH` | `verify` found a changed, missing or extra file or a symbolic link; a directory of another package or of another version of the tool; a `SUMMARY.json` that is not what the files give. |
| `DOCUMENTS_ARGUMENTS_INVALID` | A command-line error, including `-h` and an abbreviated option. |
| `DOCUMENTS_FILE_UNAVAILABLE`, `DOCUMENTS_UNVERIFIED` | Exit 1, status `UNVERIFIED`: the output directory could not be created or written for a reason other than the two above, or an error with no constant code. The text of the error is not printed. A directory left behind by a failed write has no `SHA256SUMS` and is not used. |

**The order and the policy.** These two objects are copied whole into the contract, which is handed to the host delivery. The session inputs and the rest of the epoch inputs have closed key sets and typed values; these two do not, because the packaged code reads only some of their keys and the order object is not yet defined. The tool therefore restricts what else they may hold: a key is a lowercase name, and its value is a SHA-256 (or a 40-digit revision), a clock, a date, a constant with an underscore, the epoch name, a boolean, null, or an object of those. No list, no number and no other text. A reviewer's probe had put a comma-joined string of names, a list of lowercase names, a database address and an account value into them and found each in the contract file; each is now `DOCUMENTS_FREE_FORM_VALUE`. What the restriction does not do: a 64-digit value is accepted as a hash whatever it is, so a secret of that shape, or a name spelled as a key or as a constant with an underscore, is not seen. If the frozen order carries something else (free text, a number), the tool refuses it and has to be changed before it is used.

**The tripwire.** Behind that restriction, before anything is written, every string of every output file, under every key, is compared with the instrument grammar of the capacity code (`[A-Z0-9][A-Z0-9.-]{0,19}`); a string of that shape that is neither a date nor one of the tool's dozen constants (`GO`, `FABLE`, `LIVE`, …) stops the run. The single exemption is the REQUEST's own `writer_argv` (its wait is a bare number), every entry of which is compared with its expected value instead. This is a tripwire, not a proof: a list hidden in another shape would pass it, and one real ticker spells `GO`.

## Not verified

Nothing in this list was observed.

- Every host fact the inputs stand for: the root identities, the image ID, the network, the environment file hash, the paths. The tool checks their shape, never their truth.
- The window config loaded by the packaged `CapacityConfig` **on the real roots** at `/c3po-capacity`. The tests load the tool's bytes on temporary roots whose identities were measured there.
- The calendar pin read in a container of the pinned image, and that the reviewer's interpreter then computes the same plans as the image.
- The dispatch REQUEST and GO: their shape is this tool's proposal. The host payload that would read them is not in this repository, and nothing validates them except the tool's own comparisons. One field is exercised: a test drives `manifest_writer.py` with the `writer_argv` of the REQUEST, up to a published manifest.
- The host assembly of the payload file and its refusal on a different list.
- That the hashes given for D11 are the hashes of the right documents, and that `view_evidence_sha` points at evidence anyone can produce. More generally, that any pasted hash is the hash of the right thing: the placeholder and reuse checks catch typing, empty commands and one value in two slots, nothing else.
- The order object: its shape here is the one of a test fixture (see "Open decisions").
- That the calendar line given as input was printed in the image and not computed locally.
- That the writer accepts `--require-go-mode` as this tool writes it: the cross-check below runs it against the `manifest_writer.py` of this checkout, and skips that case if the script has no such option.
- The real chain: the tests use seven synthetic chain documents in the evidence format. The packaged authority also accepts Act A signatures in the two legacy JSON formats; no test here builds those.
- That the cutoff and the parking cap in this tool (open minus 10 minutes; 900 seconds) are the writer's. They are the same numbers today; nothing ties the two files together.
- A real PostgreSQL store: `prepare-capacity-day` runs in the tests against the package's in-memory store.
- What a reader does with the static config before the day's dispatch has committed. Read from the code: such a reader can restore a committed binding on any of the five days, but it cannot derive one (`CAPACITY_VETO_DAY_UNBOUND` on a day other than the anchor day, `VETO_STALE` on the anchor day outside the anchor view), and a collector cycle that reaches the derivation without a committed binding marks that session's admission as blocked. Whether a cycle can reach that point before the dispatch is the reader's question, not this tool's.

## Offline verification

`c3po/backend/tests/test_r2d2_v2_capacity_day_documents.py` loads the tool by path and runs it through `main()`.

- **Round trip, five sessions by three windows.** The files the tool wrote are copied, unchanged, into private temporary roots. The real `CapacityConfig` loads the window's config from them; the real `CapacityLoader` and `prepare_capacity_day` commit the day's binding inside the view (admission GO read from the go root, verified by the real `DocumentAuthority` through the config); the real `validate_go` then passes GO:bar_manifest against the plan in the committed binding, and refuses it one second after the view closes. Every plan in the contract is recomputed by the real `plan`, and the real `validate_contract` accepts the contract with the list.
- **Refusals.** Each key of the epoch and session inputs removed, set to null and set to the empty string, and each key of the static inputs removed; more than eighty malformed values, each with its expected code; nothing written in any of them.
- **Hashes.** The digests of no input and of the empty JSON values, repeated blocks and repeated digits in each kind of slot, including the policy's two receipts; one value in two slots, thirteen pairs; a D11 slot equal to a policy receipt is accepted.
- **The order and the policy.** Sixteen shapes of names, secrets and numbers in the two objects, each refused, through `day` and through `templates`; an order and a policy with further hashes, clocks and constants are accepted and reach the contract unchanged. With the input check disabled, names under any key (including `writer_argv`) stop at the tripwire.
- **Determinism.** Two runs byte-identical; the day's files identical across the three windows.
- **Tampering on the host side.** A changed record, view, GO file or config, and a contract changed in a field the package reads, are refused by the packaged code (`VETO_HASH_MISMATCH`, `AUTHORITY_UNVERIFIED_OR_VETOED`, `PHASE_WINDOW_MISMATCH`, `PHASE_WINDOW_HASH`, `CAPACITY_CONSUMER_UNBOUND`, `GO_PLAN_HASH`, `CAPACITY_CONFIG_HASH`); a view rewritten to carry a veto and pinned again is refused by the veto itself.
- **`verify`.** Any changed, missing or extra file and a symbolic link are refused. With `SHA256SUMS` written again and every dependent hash carried along: a contract changed in a field the package reads is refused by content; six changes of plan fields the package does not read are refused here (and the same test shows the packaged contract check accepting them); a GO file with a second key or other bytes for the same GO; forty-three changes of the REQUEST (a writable journal bind among them) and fourteen of the dispatch GO; a second key in a pin or in a root of the config; sixteen changes of `SUMMARY.json`; a draft whose `SUMMARY.json` was changed to say `VERIFIED` is refused without the chain. One test pins what `verify` cannot tell: a changed host fact of the REQUEST, a changed root identity of the config and a changed input hash, carried along, are `VERIFIED` with another `sha256sums_sha256`; so is a REQUEST whose journal bind was removed or moved under the data volume.
- **Switches.** `IN_WINDOW` gives the same view bytes under `emitter/`, and the prepare passes once the file appears; one window; a quote window given as a digest; the writer's GO mode; an empty list (D12).
- **The chain.** `day` without `--chain-directory` and without `--draft-without-chain` is a wrong command line. Two chain pins swapped: written as a draft, refused over the chain (`DOCUMENT_APPROVAL`).
- **Cross-check with the writer.** For the three windows of one day, and once more with `--require-go-mode`, `manifest_writer.py` of this directory is loaded by path and run with the arguments of the REQUEST over the delivered documents: its own wiring, pre-flight, parking, both gates, the packaged `prepare-capacity-day` and the publication are real, and it ends in `PUBLISHED_VERIFIED` with the manifest of the test's list. Replaced: the collector factory (the packaged capacity collector over the in-memory store, with no release file, sources or journal catalog), the clock and the manifest directory. This couples the test file to the sibling script: after any change of `manifest_writer.py` this file is run again.
- **Static config.** Built from the static inputs alone, with nothing of the dispatch, D11 or the policy; an epoch inputs file is refused. Loaded by the real `CapacityConfig` with only the seven chain documents delivered; it restores the committed bindings of the first and the last session.
- **The script.** Run as a subprocess under `python -I -B`; `-h` and an abbreviated option give the one refusal line; its imports are the standard library and the packaged modules, with no settings, environment, network or process module; the calendar-pin script of this document is extracted, hashed and executed.

What is synthetic in those tests: the seven chain documents, every hash that stands for a release, a receipt, an authority or a host fact, the release object, the store (in memory), the clock, and four made-up instrument names that exist only in the payload file the test assembles in the host's place.
