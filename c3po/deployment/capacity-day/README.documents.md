# Capacity day — the document tool

Offline candidate. Nothing built by this tool has been delivered to a host, signed, published in the channel or dispatched.

**Unverified on the host.** `capacity_day_documents.py` runs on the reviewer's machine and never touches a host, a container, a database or the network. Everything this document says about what happens to its output afterwards (delivery into the capacity tree, the roots at `/c3po-capacity`, the container that reads them, the host payload) comes from the code and from offline tests. None of it was observed on the production host or on a Docker engine. "Not verified" near the end lists it together.

The tool is a deployment script, **outside the pinned implementation package**: nothing under `c3po/backend/app` changes because of it and `implementation_package_sha` does not move. It imports the packaged code of the checkout it sits in and, before it writes a byte, passes the records, the view, the contract and the GOs through the packaged validators (the capacity config and the envelope are the exceptions, see "What is checked before a byte is written"). On the host the same package validates everything again: a defect of the tool is therefore a refusal at `prepare-capacity-day`, never an acceptance of something the package would refuse, and it can be corrected offline without a new release.

`README.md` in this directory describes `manifest_writer.py`, the script that reads these documents inside the container.

## Open decisions

Each one is an input or a switch. None is closed by this tool, and none has a default: a missing value is a refusal.

| # | Decision | Where it enters the tool |
| --- | --- | --- |
| **D1** | Reader launcher accepted, or worker run directly | Nowhere. The documents are the same for either reader. Only the static config of `static-config` is read by the reader, and its bytes do not depend on which process reads it. |
| **D3** | Compose `r2d2-worker` run with capacity required | `static-config` writes one file. If the answer is yes, the compose worker reads **the same file by the same path and hash** as the reader (through its own read-only mount of the capacity tree); the tool does not write a second one. If no, nothing changes here. |
| **D4** | Veto view delivered the evening before, or emitted inside its window | `d4_view_mode`: `PRE_DELIVERED` or `IN_WINDOW`. The view bytes and the pin are identical in both modes. Only the place changes: `documents/` (delivered with the rest) or `emitter/` (handed to whoever writes it into the documents root at the view instant). |
| **D6** | Number and times of the windows per session | `d6_windows`: an ordered list, one entry per window, New York wall clock. One window is accepted, nine is the limit. The times are checked against the two phase windows, the cutoff and the writer's parking cap. |
| **D11** | Which document hashes fill `recertification_receipt_sha`, `wind_down_28_receipt_sha`, `input_receipts_sha`, and the windows of `quote_refresh` / `quote_capture` | The `d11` block: three hashes, and for each of the two phases either a window (`not_before`, `not_after`) or the digest of one (`phase_window_sha`). The tool cannot tell whether a hash is the hash of the right document; it only refuses a value that is not a SHA-256 or that looks like a placeholder. |

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
| `SUMMARY.json` | Index of the directory: role of each file, every hash a GO text needs, the clocks in UTC, the hashes of the two input files and of the tool itself, and what the self-check did and did not check. | stays with the reviewer |
| `SHA256SUMS` | One line per file. Its own SHA-256 names the whole set. | stays with the reviewer |

The day's files are delivered once. A second or third window of the same day adds only its own view and config to the capacity tree (and its own envelope to the dispatcher): the delivery creates files exclusively, and the other files of that window's directory are the ones already there, byte for byte.

Every JSON file is canonical (sorted keys, compact, no trailing newline). Two runs with the same inputs give the same bytes. **No file contains an instrument symbol**: the tool has no input that carries the list (see "The payload file" and "Refusals").

`templates` writes `ACT_B_TEMPLATES.json`: the five-day map (`template_shas`, `templates`, `template_set_sha`, `cut_rule`, `order_sha`) that Act B has to carry for these documents to be accepted, plus the five contract templates. `static-config` writes `config/week.static.capacity.json` (see "The static config").

An output file authorises nothing by itself. The records are written in the `ISSUED` state because the packaged parser accepts no other; they acquire authority only when a capacity config pins their hashes and an authorised dispatch names that config's hash.

## Who signs or publishes what, and when

All of it is authored by Fable on the **evening before** the session, after that day's causal list is committed (Sunday evening for Monday), and delivered by Codex under the five-session authority with Fable's GO by hash. Nothing here is signed by the owner per day.

| Document | Signature or publication | When |
| --- | --- | --- |
| `ACT_B_TEMPLATES.json` | Not signed itself. Its content is copied into Act B, which Codex, Fable and the owner sign. | Weekend, before Act B is drafted |
| `week.static.capacity.json` | Fable's GO by hash for its delivery; its hash enters `pins.env`. | Weekend, once the chain documents, the release hash and the root identities exist |
| `TEMPLATE` record | None of its own: the authority is Act B. | Evening before |
| GO:admission (record and GO file) | Fable's individual GO. The plan declares Fable's per-day dispatch GO to be the individual GO for admission; the dispatch GO written here carries `admission_go_sha256` for that reason. | Evening before |
| GO:bar_manifest (record, GO file, publication record) | Fable, delegated under Act B. **Published in the channel** at the instant given as `bar_manifest_published_at`; the code requires that instant to be at least 15 minutes before the phase window opens. | Evening before |
| Veto view | Authored by Fable ahead of its own `observed_at`. It states "no owner veto and no revocation"; the owner's veto is exercised by withdrawal of the dispatch (D4). | Authored the evening before; delivered then, or emitted at the view instant |
| Window capacity configs (one per window) | None of their own: each hash is named by its dispatch REQUEST. | Evening before, all windows of the day |
| Contract | None of its own: every GO binds the hash of one of its plans. | Evening before |
| Dispatch REQUEST and GO | Fable publishes the hash of the GO; the GO file says `UNSIGNED` and is nothing until then. | Evening before, one pair per window |

`bar_manifest_published_at` is fixed before the build, because the bytes carry it. The publication is then made at that instant; if it slips, the day is built again with the real instant. No code can see the channel: a record whose instant is not the real one is a false record that every validator accepts.

## Inputs

Two JSON files. Both have a fixed key set: a missing or an unknown key is a refusal. Values are strings, integers, booleans, lists and objects in printable ASCII; a number with a fraction is refused.

### Epoch inputs (`R2D2_CAPACITY_DAY_EPOCH_INPUTS_V1`), one file for the five sessions

| Key | Content | Exists |
| --- | --- | --- |
| `schema` | the constant above | now |
| `order` | The object whose digest is Act B's `order_sha`. It must carry `owner_sha`, `epoch`, `authorized_sessions` (the five sessions) and `capacity` 550. | when Act B is drafted |
| `policy` | The body of the live policy (`R2D2_V2_LIVE_POLICY_V1`, mode `LIVE`). A policy with a `symbols` key is refused. | after the weekend |
| `policy_sha` | Digest of `policy` as the assembler computes it: SHA-256 of its canonical JSON. This is **not** necessarily the SHA-256 of the installed policy file; the two are equal only if that file is the canonical JSON itself. | after the weekend |
| `release_sha` | SHA-256 of the installed release file. Must equal `policy.release_sha`. | after the weekend |
| `package_sha` | `implementation_package_sha` of the final head. Must equal `policy.package_sha` **and the package of this checkout**: run the tool from a checkout of the deployed revision. | after the final head |
| `calendar_pin_sha` | The calendar pin computed **inside the pinned image** (see "The calendar pin"). Must equal the one this interpreter computes. | after the deploy |
| `act_b_sha256` | SHA-256 of the Act B document. Must equal `chain_pins.ACT_B.sha256`. | after Act B is signed |
| `chain_pins` | File name and SHA-256 of the seven chain documents as delivered into the documents root: `CODEX`, `FABLE`, `DUDU`, `ACT_B`, `B_CODEX`, `B_FABLE`, `B_DUDU`. | after Act B is signed |
| `capacity_roots` | `config`: `path`. `documents`, `payload`, `go`: `path` and `identity`. Paths are the **container** paths. The identities are the ones printed in two containers by the host rehearsal. | after the host rehearsal |
| `d11` | `recertification_receipt_sha`, `wind_down_28_receipt_sha`, `input_receipts_sha`, `quote_refresh`, `quote_capture` (D11). | when D11 is closed |
| `phase_windows` | `admission` and `bar_manifest`, each `not_before` and `not_after`, New York wall clock `HH:MM:SS`. | now (plan: 06:15:00 to 09:20:00) |
| `d4_view_mode` | `PRE_DELIVERED` or `IN_WINDOW` (D4). | when D4 is closed |
| `d6_windows` | List of `name` (lowercase), `start_not_before`, `view_opens_at`, New York wall clock (D6). | when D6 is closed |
| `view_valid_seconds` | Life of a view, 1 to 10. The packaged reader refuses more than 10. | now (plan: 10) |
| `max_wait_seconds` | The writer's `--max-wait-seconds`, 1 to 900. A window whose view opens later than this after `start_not_before` is refused. | now (plan: 900) |
| `dispatch` | Host and authority facts for the envelope, below. | after the weekend |

`dispatch`:

| Key | Content |
| --- | --- |
| `authority_sha256` | SHA-256 of the owner-signed five-session authority. |
| `payload_sha256` | SHA-256 of the host payload bytes Codex accepted. |
| `writer_sha256` | SHA-256 of `manifest_writer.py` as authorised. |
| `image_id` | `sha256:<64 hex>`, read on the host after the deploy. |
| `build_sha` | The 40-hex revision. Must equal `policy.code_revision`. |
| `network` | The compose network that reaches the database. `host` and `none` are refused. |
| `host_binding_sha256` | The dispatcher's host binding. |
| `pins_env` | `path` and `sha256` of the reader's `pins.env`. |
| `secret_env_path` | Path of the reader's `secret.env`. **A path only.** The tool never reads that file and has no input for its content. |
| `docker_config` | The empty docker CLI configuration directory. |
| `mounts` | List of `source`, `target`, `readonly`. Exactly one writable mount, whose target is `manifest_directory`; every capacity root must lie under a read-only target. |
| `manifest_directory` | Container path of the manifest directory. |

### Session inputs (`R2D2_CAPACITY_DAY_SESSION_INPUTS_V1`), one file per session day

| Key | Content | Exists |
| --- | --- | --- |
| `schema` | the constant above | now |
| `day` | The session date, one of the five. | now |
| `causal_scope` | `commitment_sha256` and `list_sha256` of that day's committed causal list, copied from its publication record (the public fields of `V2_CAUSAL_LIST_PUBLICATION_V1`). **Two hashes; never the list.** | each evening, after the list is committed |
| `bar_manifest_published_at` | UTC instant `YYYY-MM-DDTHH:MM:SS+00:00` at which GO:bar_manifest is published. Between 15 minutes and 4 days before the phase window opens. | each evening |
| `view_evidence_sha` | One SHA-256 per window name: the `evidence_sha` of that window's view. Which document that is the hash of is for the signatories; the code requires a SHA-256 and nothing else. | each evening |

### Inputs that only exist after the weekend

The release hash, the policy and the policy hash, the package hash of the final head, the Act B hash with the seven chain pins, the capacity root identities, the calendar pin read in the image, the image ID, the hash of `pins.env`, the authority hash, the payload and writer hashes and the host binding. Until all of them exist no day can be built. `templates` needs only the order and can run as soon as the order object is fixed. The per-day hashes exist each evening.

**Hashes are produced by command and pasted, never typed.** A value with fewer than five distinct hexadecimal digits (`aaaa…`, `0101…`) is refused as a placeholder, so a fixture value cannot reach a signed document unnoticed.

## The calendar pin

Every config and every plan carries the calendar pin: a digest of the session details of the five days **and of the version string of the calendar library**. The package hash does not cover that library, and `backend/requirements.txt` allows a range of versions (`exchange-calendars>=4.13,<5`). A reviewer's machine with another version computes another pin; every document would then be refused in the container, `CAPACITY_CONFIG_CALENDAR` at the config load. The tool therefore takes the pin of the image as an input and refuses (`DOCUMENTS_CALENDAR_PIN`) unless its own interpreter computes the same value.

The pin is read once, after the deploy, by one run of the pinned image with no mount and no network, the script on standard input:

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

The line it prints holds the pin, the library version, the package hash of the image and the order hash compiled into it: the same run confirms `package_sha`. It reads no file outside the image and no environment. This run was not executed in a container anywhere *(unverified)*; the host rehearsal that loads the static config in the image proves the same equality a second time.

## Command lines

Run from the repository root of a checkout at the deployed revision, with the interpreter of the backend environment (the one that has the backend requirements installed). `-I` keeps the environment and the current directory out of the import path; the tool adds the backend directory of its own checkout (`APP_ROOT`, the single constant near its top) and refuses (`DOCUMENTS_APP_ROOT`) if the `app` package it imported came from anywhere else.

```
# once, before Act B is drafted
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py templates \
  --order-file ORDER.json --output-directory OUT/act-b-templates

# once, on the weekend: the reader's static config
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py static-config \
  --epoch-inputs EPOCH.json --day 2026-10-05 --window primary \
  --view-evidence-sha <64 hex> --output-directory OUT/static

# each evening, once per window of the next session
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py day \
  --epoch-inputs EPOCH.json --session-inputs 2026-10-05.json --window primary \
  --output-directory OUT/2026-10-05.primary --chain-directory CHAIN

# at any time: re-check a directory that was written earlier
python -I -B c3po/deployment/capacity-day/capacity_day_documents.py verify \
  --directory OUT/2026-10-05.primary --chain-directory CHAIN

shasum -a 256 OUT/2026-10-05.primary/SHA256SUMS
(cd OUT/2026-10-05.primary && shasum -a 256 -c SHA256SUMS)
```

- `--output-directory` must not exist. The tool creates it (0700, files 0600) and never writes into an existing one.
- `--chain-directory` is a directory holding the seven chain documents under the file names of `chain_pins`. It is optional. With it, each file is hashed against its pin and the day's GOs are verified by the packaged documentary authority over the real signed chain. Without it that check is skipped and the output says so (`documentary_authority` `NOT_CHECKED`).
- Standard output is one JSON line: `status` (`WRITTEN`, `VERIFIED`, `REFUSED`, `UNVERIFIED`), on success the day, the window, the file count, the SHA-256 of `SHA256SUMS` and of the capacity config, and on a refusal a constant `code`. Exit 0, 3 (refused) or 1 (unverified). No path, no input value and no exception text is printed; a wrong argument is `DOCUMENTS_ARGUMENTS_INVALID`, never the argument itself.

## The static config

The long-running reader (and the compose worker, if D3 is yes) uses one capacity config for the week. Restoring a committed binding reads only the Act A and Act B chains, but the packaged config loader refuses a config without a `TEMPLATE` pin and without at least one view pin. `static-config` therefore pins the seven chain documents, the `TEMPLATE` record of one anchor day and the view of one anchor window. Those two extra files do not have to exist when the config is loaded (the loader checks the shape of a pin, not the file), and the bytes of both are the ones `day` later writes for that day and window **if the same `--view-evidence-sha` is used**; a repository test compares them.

The static config does not depend on the `dispatch` block, on `d11`, or on any per-day hash, so it does not change when those are completed later. The whole epoch inputs file is still required to run the command.

## The payload file

The loader reads `session=<day>.json` from the payload root: `{"contract": …, "causal": …}`, where `causal` carries the day's ordered list. **This tool does not write that file and cannot**: it never receives the list. It is assembled on the host, by the delivery, from the committed causal-list file and `contract/session=<day>.contract.json`. The delivery must refuse unless the list's own hash and the commitment hash equal the contract's `causal_scope`; its receipt carries no symbol. That payload is Codex's side and is not in this repository.

`list_sha256` is the SHA-256 of the canonical JSON of the ordered list and `commitment_sha256` the digest of the commitment object, as `r2d2_v2_causal_list.py` computes them (lines 197 and 236–238); the packaged contract check recomputes the first from the list in the payload file. That the published record of a real day carries exactly these two values was read from the code, not from a host record.

## What is checked before a byte is written

`day` builds everything in memory and then runs, on those bytes:

- the packaged `normalize_document` on the four records and the packaged `PinnedVetoReader` on the view: accepted at the instant it opens and one microsecond before it closes, refused one microsecond earlier and at `valid_until`;
- the packaged `validate_contract` on the contract, with an empty stand-in for the list: it must pass every check and fail only at the last one (`CAPACITY_CAUSAL_BINDING`), which only the host can complete;
- the packaged `validate_go` on both GOs against their plans, at the view instant;
- with `--chain-directory`: the packaged `DocumentAuthority` (`act_b`, `check_binding`, `verify_go`) over the real chain documents, the four records and the view;
- its own comparisons, which are necessary conditions of the packaged `verify_go` and need no chain: each GO against its record, the `TEMPLATE` record and the publication record; every pin in the config against the bytes it pins; the envelope against the documents;
- the tripwire for instrument-shaped strings (see "Refusals").

`verify` reads `SHA256SUMS`, requires the directory to hold exactly the listed files with the listed hashes, and runs the same checks again on a `day` directory. On a `templates` or `static-config` directory it can only compare the listing, and its line says so (`content` `LISTING_ONLY`).

Not checked by the tool: the packaged `CapacityConfig` is **not** loaded, because it opens the real roots and compares their identities, which only exist on the host. The repository tests load it, on temporary roots.

## Refusals

A refusal prints one line with a constant code and writes nothing. Codes that start with `DOCUMENTS_` are the tool's own; any other code is the packaged validator's, passed through unchanged (for example `POLICY_NOT_EPOCH_WIDE`, `DOCUMENT_BINDING`, `AUTHORITY_UNVERIFIED_OR_VETOED`).

| Code | Meaning |
| --- | --- |
| `DOCUMENTS_EPOCH_FIELDS`, `DOCUMENTS_SESSION_FIELDS` | A key of the input file is missing or unknown. |
| `DOCUMENTS_INPUT_<NAME>` | That input is missing, malformed, or a placeholder hash. |
| `DOCUMENTS_INPUT_JSON`, `DOCUMENTS_INPUT_NOT_ASCII`, `DOCUMENTS_INPUT_TYPE`, `DOCUMENTS_INPUT_FILE` | The file is not strict JSON (duplicate key, fraction, non-finite), holds a non-ASCII or control character, an unsupported value, or cannot be read. |
| `DOCUMENTS_PACKAGE_MISMATCH`, `DOCUMENTS_CALENDAR_PIN`, `DOCUMENTS_APP_ROOT` | The checkout or the interpreter is not the one the documents are for. |
| `DOCUMENTS_POLICY_HASH`, `DOCUMENTS_POLICY_SCOPE`, `DOCUMENTS_ORDER_SCOPE`, `DOCUMENTS_ACT_B_HASH`, `DOCUMENTS_BUILD_REVISION` | Two inputs that must agree do not. |
| `DOCUMENTS_DAY_NOT_AUTHORIZED`, `DOCUMENTS_WINDOW_UNKNOWN` | Not one of the five sessions; not one of the `d6_windows`. |
| `DOCUMENTS_ADMISSION_WINDOW_LATE`, `DOCUMENTS_VIEW_OUTSIDE_PHASE_WINDOW`, `DOCUMENTS_VIEW_AFTER_CUTOFF`, `DOCUMENTS_WINDOW_WAIT`, `DOCUMENTS_WINDOWS_OVERLAP`, `DOCUMENTS_PHASE_WINDOWS_NOT_DISTINCT`, `DOCUMENTS_GO_NOTICE` | Clocks the packaged code or the writer would refuse: admission opening after the open, a view outside a phase window or after open minus 10 minutes, parking longer than `max_wait_seconds`, overlapping windows, two phases with one window digest, a publication less than 15 minutes (or more than 4 days) before the window. |
| `DOCUMENTS_DISPATCH_WRITABLE_MOUNT`, `DOCUMENTS_DISPATCH_CAPACITY_MOUNT` | The mounts are not "manifest directory writable, everything else read-only, capacity roots under a read-only mount". |
| `DOCUMENTS_CHAIN_FILE`, `DOCUMENTS_CHAIN_HASH` | A chain document is absent from `--chain-directory`, or its bytes are not the pinned ones. |
| `DOCUMENTS_SELF_CHECK_…`, `DOCUMENTS_DIGEST_NAMESPACE`, `DOCUMENTS_PLAN_UNBOUND` | The tool's own output failed one of its comparisons: a defect of the tool (or, under `verify`, a directory that was changed). |
| `DOCUMENTS_SYMBOL_SHAPED_VALUE` | The tripwire, below. |
| `DOCUMENTS_OUTPUT_EXISTS`, `DOCUMENTS_SUMS_…`, `DOCUMENTS_SUMMARY_SCOPE` | The output directory exists; `verify` found a changed, missing or extra file, or a directory of another package. |
| `DOCUMENTS_ARGUMENTS_INVALID` | A command-line error. |
| `DOCUMENTS_FILE_UNAVAILABLE`, `DOCUMENTS_UNVERIFIED` | Exit 1, status `UNVERIFIED`: the output directory could not be created or written, or an error with no constant code. The text of the error is not printed. A directory left behind by a failed write has no `SHA256SUMS` and is not used. |

**The tripwire.** The free-form inputs (`order`, `policy`) are copied into the contract. Before anything is written, every string of every output is compared with the instrument grammar of the capacity code (`[A-Z0-9][A-Z0-9.-]{0,19}`); a string of that shape that is neither a date nor one of the tool's dozen constants (`GO`, `FABLE`, `LIVE`, …) stops the run. This is a tripwire, not a proof: a list hidden in another shape would pass it, and one real ticker spells `GO`. The guarantee is structural: no input of this tool carries the list.

## Not verified

Nothing in this list was observed.

- Every host fact the inputs stand for: the root identities, the image ID, the network, the environment file hash, the paths. The tool checks their shape, never their truth.
- The window config loaded by the packaged `CapacityConfig` **on the real roots** at `/c3po-capacity`. The tests load the tool's bytes on temporary roots whose identities were measured there.
- The calendar pin read in a container of the pinned image, and that the reviewer's interpreter then computes the same plans as the image.
- The dispatch REQUEST and GO: their shape is this tool's proposal. The host payload that would read them is not in this repository, and nothing validates them except the tool's own comparisons. One field is exercised: a test drives `manifest_writer.py` with the `writer_argv` of the REQUEST, up to a published manifest.
- The host assembly of the payload file and its refusal on a different list.
- That the hashes given for D11 are the hashes of the right documents, and that `view_evidence_sha` points at evidence anyone can produce.
- The real chain: the tests use seven synthetic chain documents in the evidence format. The packaged authority also accepts Act A signatures in the two legacy JSON formats; no test here builds those.
- That the cutoff and the parking cap in this tool (open minus 10 minutes; 900 seconds) are the writer's. They are the same numbers today; nothing ties the two files together.
- A real PostgreSQL store: `prepare-capacity-day` runs in the tests against the package's in-memory store.
- What a reader does with the static config before the day's dispatch has committed. Read from the code: such a reader can restore a committed binding on any of the five days, but it cannot derive one (`CAPACITY_VETO_DAY_UNBOUND` on a day other than the anchor day, `VETO_STALE` on the anchor day outside the anchor view), and a collector cycle that reaches the derivation without a committed binding marks that session's admission as blocked. Whether a cycle can reach that point before the dispatch is the reader's question, not this tool's.

## Offline verification

`c3po/backend/tests/test_r2d2_v2_capacity_day_documents.py` loads the tool by path and runs it through `main()`.

- **Round trip, five sessions by three windows.** The files the tool wrote are copied, unchanged, into private temporary roots. The real `CapacityConfig` loads the window's config from them; the real `CapacityLoader` and `prepare_capacity_day` commit the day's binding inside the view (admission GO read from the go root, verified by the real `DocumentAuthority` through the config); the real `validate_go` then passes GO:bar_manifest against the plan in the committed binding, and refuses it one second after the view closes. Every plan in the contract is recomputed by the real `plan`, and the real `validate_contract` accepts the contract with the list.
- **Refusals.** Each key of both input files removed, set to null and set to the empty string; more than fifty malformed values, each with its expected code; nothing written in any of them.
- **Determinism.** Two runs byte-identical; the day's files identical across the three windows.
- **Tampering.** A changed record, view, GO file, contract or config is refused by the packaged code (`VETO_HASH_MISMATCH`, `AUTHORITY_UNVERIFIED_OR_VETOED`, `PHASE_WINDOW_MISMATCH`, `PHASE_WINDOW_HASH`, `CAPACITY_CONSUMER_UNBOUND`, `GO_PLAN_HASH`, `CAPACITY_CONFIG_HASH`); a view rewritten to carry a veto and pinned again is refused by the veto itself; `verify` refuses any changed, missing or extra file, and a consistently re-listed change by content.
- **Switches.** `IN_WINDOW` gives the same view bytes under `emitter/`, and the prepare passes once the file appears; one window; a quote window given as a digest.
- **Cross-check with the writer.** For the three windows of one day, `manifest_writer.py` of this directory is loaded by path and run with the arguments of the REQUEST over the delivered documents: its own wiring, pre-flight, parking, both gates, the packaged `prepare-capacity-day` and the publication are real, and it ends in `PUBLISHED_VERIFIED` with the manifest of the test's list. Replaced: the collector factory (the packaged capacity collector over the in-memory store, with no release file, sources or journal catalog), the clock and the manifest directory.
- **Static config.** Loaded by the real `CapacityConfig` with only the seven chain documents delivered; it restores the committed bindings of the first and the last session.
- **The script.** Run as a subprocess under `python -I -B`; its imports are the standard library and the packaged modules, with no settings, environment, network or process module; the calendar-pin script of this document is extracted, hashed and executed.

What is synthetic in those tests: the seven chain documents, every hash that stands for a release, a receipt, an authority or a host fact, the release object, the store (in memory), the clock, and four made-up instrument names that exist only in the payload file the test assembles in the host's place.
