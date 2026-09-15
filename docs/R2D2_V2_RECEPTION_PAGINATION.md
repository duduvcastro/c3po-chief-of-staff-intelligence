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
first page retains session/capture behavior; continuation pages revalidate
state/package/calendar and process source events plus actual session clocks. Each page records the actual observation time. A clock that has
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
`493e40efbc38e0afd55c7ee4f275694b88eb549cf5eebcdbbfac18a55d143118`
is Fable revision1a, superseding849d6879. It qualifies the original design:

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
  initial share=max(1,floor(target/F0)), the qualified bound is
  ceil(total_pending/share); a drained file can subsequently increase the share.
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
identity/size/mtime were checked before and after the decoding pass. The historical receipt lists all in-memory module hashes. Its raw-source
module was an uncommitted draft and it omitted execution timestamps/host
provenance; it is not evidence that a later complete head ran on the host.


## Final reader audit F408c dispositions

Fable audit SHA256 `70ba8bcef63910cf447572e904849dbfeb5b1a64cbc4de692a9cf5590e99c8c7`
(`#348`, comment5680020301) introduced the following counterexamples.

- **c1 corrected:** the live reader refreshes the actual clock after the joint
  file-size snapshot. A valid receipt still ahead of that clock defers the whole
  joint page without quarantine, event application or cursor advancement. This
  is deliberately more conservative than skipping just that file: a concurrent
  STOP cannot be omitted while a quote in the other file triggers an exit.
  An explicit historical test clock is never silently refreshed. The next poll
  replays retained bytes; repeated deferral is covered by c3 below.
- **c2 corrected:** a quarantined frame with a valid instrument symbol creates
  an instrument-scoped DATA_GAP and admission gate, before economic application
  of that page. Its reason is `RAW_QUARANTINE_<decoder code>`. Other frames keep
  being decoded and receipted. Unknown-symbol/status frames do not establish
  an instrument identity or prove coverage. Existing portfolio uncertainty
  rules still apply; scoped quarantine is not permission to invent a STOP.
- **c3 corrected:** incomplete/changed/ahead-of-clock raw input defers only raw
  application, not capture attempts, stale checks or SESSION_CLOSE. Durable
  `RAW_POLL_DEFERRED` receipts count consecutive failures; the third poll adds
  `RAW_POLL_PERSISTENT_FAILURE`. Recovery is receipted and clears the consecutive
  counter, not the historical data-quality issue. Cursor bytes remain unchanged
  on every deferred page.
- **c4 corrected:** compact UTC-daily LIVE journals; see the controller document.
- **c5 declared limitation:** equivalence is to polls at actual commit clocks
  t1<t2<… after the respective cuts, never polls backdated to W. If reading and
  committing crosses market close, a pre-close quote received by the collector
  after close cannot trigger a retrospective EOD_POSITIVE. SESSION_CLOSE still
  runs on that continuation. The boundary counterexample now asserts this
  behavior explicitly. Operational latency must be accepted in the head review.
- **c6 corrected:** a reception regression is counted and limits the affected
  file to its quota once detected. The per-page horizon is derived from that
  page, not the cursor's historic maximum. The historical maximum remains only
  for anomaly detection across restart. On anomalous streams a page is bounded
  by per-file quota or any already-consumed legitimate tied prefix; the normal
  global prefix-closure/tie guarantee does not extend to a regressing writer.
  Tests cover a201-record clock spike and a later300-record append.
- **c7 declared limitation:** retain all raw epoch parts and journal receipts.
  Reaching EOF does not seal a part: a writer can append to a previously drained
  file (covered by regression). Without a signed finality/retention protocol,
  deleting that file remains a continuity failure, not silently accepted
  rotation. Full multi-file cursors remain in SOURCE_CURSOR journal entries,
  so storage grows with retained-file count and page count. The4096-file gate
  remains; this change adds no purge or compact cursor protocol. Capacity and
  retention are operational acceptance conditions, not claimed resolved.
- **c8 partial:** every continuation revalidates state/calendar/package; corrupt
  changes roll back the page. JSON parsing has a distinct controller diagnostic.
  Concurrent cursor mutation still fails closed with a worker exception; EMFILE
  still maps to a source failure. Optional controller stop-journal receipt,
  generation-specific unsubscribe matching and expiry snapshot label remain
  open P3. Historical real-decode provenance is explicitly qualified above.

No head GO is claimed by this document. Declared c5/c7 limitations and remaining
P3 items are submitted for the independent exact-head review.
