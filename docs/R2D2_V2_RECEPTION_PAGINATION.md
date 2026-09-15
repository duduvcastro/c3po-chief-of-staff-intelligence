# Reception-cut pagination — PR #408

Status: implemented for re-audit, **NO-GO remains**. This is not an operational
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

## Three contradictions requiring disposition before GO

1. **Universal snapshot equivalence is false for late arrivals.** Quote Q has
   `at=received=t`; trade S has `at=t, received=t+1`; another quote is at t+2.
   A full snapshot yields S,Q,Q under the current priority key. Budget-two
   reception pages yield Q followed by S,Q. Tests execute both the source
   ordering and collector and obtain different sequence/state hashes. A
   compatible, ordered pre-open fixture *does* produce identical event and full
   state hashes for page targets 1,3,7,16384. That conditional result is not a
   proof of the universal requirement. The collector receipt clock is never W.
2. **Fixed per-file shares do not guarantee 3 pages for 3 budgets.** Budget two,
   five early quotes in one file and one later trade in the other require five
   pages under the specified min-horizon algorithm. A balanced backlog of
   49,152 valid frames converges in exactly three pages of 16,384. The universal
   claim would require a changed allocation algorithm or a qualified bound.
3. **An indivisible reception group can exceed the page target.** Splitting a
   group with equal reception could hide its STOP in the next page. The reader
   extends through W and records `target_exceeded`, so it never permanently
   refuses that group by volume. This treats 16,384 as a target, not a hard
   memory bound; a very large group can exceed the cycle's intended latency.
   A hard 16,384 cap plus complete ties plus unconditional progress cannot all
   hold for a group of 16,385 records. No production throughput GO is claimed.

Executable counterexamples are in `tests/test_r2d2_v2_raw_source.py` with names
`test_design_counterexample_*`. They assert the contradictions, so their PASS
is **not** evidence that the contradicted requirement passes. Also covered:
cross-feed STOP at W vs after W, equal-reception boundaries, decreasing receipt
clocks, page/cycle caps, exact replay after a discarded or failed second page,
non-tick/quarantine followed by valid tick, and cursor/P5 integrity.

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
