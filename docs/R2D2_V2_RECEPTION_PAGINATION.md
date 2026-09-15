# Reception-cut pagination — PR #408

Status: implementation awaiting exact-head re-audit; **not operational GO**. This is not an operational
release or permission to merge/subscribe. Design reference:
`98da894d51fc6af7f011c6f0764604000e183b6651172dca072433b5251d9720`.
It supersedes the earlier staging proposal; there is no staging or second cursor.

The reader freezes all retained file sizes, takes per-file prefixes of
`max(1, 16384 // pending_files)` complete frames, and uses the minimum reception
horizon W (drained files have an infinite horizon). Each file delivers its
contiguous prefix through W. The existing event ordering is unchanged. A
transaction commits events, skipped-frame receipts and the one raw cursor.
Continuation pages reuse the same ephemeral file-size snapshot and validate
file identities, offsets and boundary witnesses. Appends wait for the next
cycle. Failed commits leave their page reproducible from the retained bytes.

Each cycle admits at most 16 pages, stopping admission of another page after
500ms. This is not a hard runtime cap on an individual page/transaction. The
first page retains session/capture behavior; continuation pages only apply
source events. Each page records the actual observation time. A clock that has
not advanced defers continuation rather than manufacturing a later timestamp
or changing the portfolio's simultaneous-priority check. Capture is not repeated
for each page. Actual clock, capture/close boundaries and late event behavior
therefore remain part of the required operational review.

No-symbol provider frames are `RAW_NON_TICK`; invalid complete frames are
quarantined. A receipt records code, disposition, byte offset/length and SHA.
These frames advance the byte offset but not the decoded-event sequence, so
status frames do not manufacture an EVENT_SEQUENCE_GAP. SOURCE_CURSOR binds
the skipped list/hash and page counts in the same commit. `received_at`
regressions produce counted, locatable `RAW_RECEIVED_AT_DECREASED` notices;
the cursor retains the maximum observed reception timestamp across restart.
Unknown/invalid reception has no economic event; it is quarantined and provides
no clock/coverage proof. Incomplete appends still defer the affected joint page.
Oversized complete records are hashed in a streaming pass without retaining
arbitrarily large frame bodies. Neither skipping nor decoding proves a complete
tape, regular BAR coverage, or live capacity.

## Qualified guarantees accepted by Fable

Disposition SHA256
`849d6879ff0f11ba6bb8af4268a40d3ca93b2301b386e2808ef77d8161699488`
qualifies the original design without requiring an allocation change:

- **Reception-prefix closure** (fechamento por prefixo de recepção): for the
  writer's nondecreasing reception stream, all retained files deliver their
  contiguous prefix through the same W. The comparison is to a schedule of
  snapshots at those cuts, not one uncut snapshot containing later arrivals.
  `test_reception_prefix_closure_and_equivalent_cut_snapshot_schedule` builds
  cut-size snapshots independently from original frame timestamps/lengths and
  compares exact envelopes, cursors and full collector state SHA at targets
  1/2/3/7, including a trade with an earlier event clock. Both runs use identical
  actual observation clocks; neither substitutes W for the collector clock.
- **Monotonic progress** (progresso monotônico): each nondeferred page consumes
  at least one frame, offsets never decrease, and draining terminates. With
  initial share=max(1,target/F), the qualified bound is the sum over files of
  ceil(pending/share); a drained file can subsequently increase the share.
  `test_monotonic_progress_and_qualified_convergence_bound` covers uneven and
  multiple-file inventories. Balanced 49,152 valid frames still need exactly
  three 16,384-record pages. Three pages is not the universal bound.
- **Complete tied groups** (grupo empatado íntegro): 16,384 is a target. A group
  at W stays together and `target_exceeded` records oversized pages. The test
  `test_tied_reception_group_is_complete_and_target_exceeded_is_counted` checks
  both page membership and the count of pages exceeding the target. A page
  already in progress is not preempted at500ms; operational latency/retention
  still need observation before activation.

The earlier `test_design_counterexample_*` tests remain as regressions against
reintroducing the rejected universal claims: late arrivals can change ordering
versus an uncut snapshot; fixed shares can take more than three pages. Those
results no longer constitute unresolved design objections after this disposition.
Nonmonotonic reception remains a counted writer diagnostic/late-arrival case,
not fabricated feed completeness. It is tested separately, including restart.
Other regressions cover replay after discard/failed commit, transient append,
P5 cursor integrity, non-tick/quarantine continuation and actual clock checks.

## Read-only real spool decoding

An entire quote part from 2026-09-04 was decoded in memory on the existing host,
using the local decoder and its validation dependencies. No host file, database,
configuration, container or subscription was changed. No provider call was made.
Only aggregate counts and hashes were returned.

- Bytes: 268435460; frames/decoded events: 1070516.
- Regular events: 1070515; nonregular: 1; quarantine/non-tick in this part: 0.
- Part SHA256: `bc1b8465ee5b5688c20d0693e29bcfd639754d798e157cbdd77140e83fab9691`.
- Decoded envelope-sequence SHA256: `02d8febffe728894df53fc43630b5bbbe3f1fb6a95e6722fcda0cb7a7a022f8a`.
- Decoder module SHA256: `cce815088756c11d5a50dc9b2fb5d158c86869ec20de888bea722ac00e69018c`.

This proves that part's decoding, not every retained part or live feed. File
identity/size/mtime were checked before and after the decoding pass. The raw
receipt also lists all in-memory module hashes; the frame iterator is unchanged
from that read (subsequent reader edits remove an unused budget constant/docs).
