"""The official target price — one for everything (Valuation Engine V3.2 rev 7, §7-bis, Passo 0).

Two structures, both append-only (rev 7, TP-B):

* **prediction records** (`valuation_predictions`): what a producer said for ``(market, symbol)`` at
  ``prediction_instant``, keyed by the producing cycle (the ``analysis_snapshots`` row the producer published).
  Sources coexist (``official_blend_v1`` today; ``official_internal_v1`` after Passo 1; ``v3_2_shadow`` later);
  a re-run is a new cycle, hence a new record — nothing is rewritten. **The record is what is served**: the
  official TP and buy-in a consumer sees come from the record, never from a snapshot that could be edited.
* **the official selection** (`valuation_official_selection`): one row per *generation* — the set of complete,
  validated cycles, one per market, plus the targeted (on-demand) cycles admitted for symbols outside the universe,
  whose records ARE the official TP right now. Any change of a served number is a NEW generation (new id); switching
  the source (Passo 1/2) or rolling back is the insertion of a new generation; the previous one stays readable.

Passo 0 changes no number: the producer is the current official engine — the canonical universe rows the
screeners already publish (`valuation_universe.outputs.rows`, ``our_tp``), i.e. exactly what the site shows.
What changes is who may compute: **no operational consumer computes, adjusts, calibrates or blends a TP of its
own**; each resolves ONE generation per request/batch and reads every market and symbol through it, stamping
``generation_id`` / ``tp_source`` / ``official_cycle_id`` / session / instant / record hash. Studies and grading read
prediction records by source/version/instant (rev 7, TP-C; §10.8).

Rev 4 (Codex F393-3..7 residuals; pre-review D1–D3, B1–B2, A1, C1, E1, F1):
* a caller that RESOLVED a generation and found none passes ``None`` and is served nothing — only the sentinel
  ``UNRESOLVED`` (the default) makes a reader resolve the current generation itself; there is no raw fallback;
* the session of a prediction is the last COMPLETED session of the market's exchange calendar (a Sunday-night
  or an intraday prediction belongs to the previous session), never the civil date of any zone;
* a targeted cycle is admitted only if it passes the same validation as a universe cycle, and only for a symbol
  the universe cycle of the generation does not already serve;
* activation carries a market's current cycle over when that market has no new valid cycle (one market's bad
  night no longer strips the stamp from the other two); bootstrap still needs every market once;
* activation/admission take the wall clock; a generation chains on ``previous_generation_id`` (UNIQUE in the
  migration) so two concurrent writers cannot both extend the same predecessor; served objects are deep copies.

Rev 5 (Codex F393-4..7, F393-9 residuals on rev 4):
* an explicit selection validates every targeted cycle with the SAME validator as the automatic admission;
* a writer names the generation it based its decision on (``expected_previous``); if the chain moved meanwhile the
  write is refused and the writer recomputes on the new head — no other writer's generation is ever dropped; the
  root is unique too (a second bootstrap is refused);
* a calendar failure is an UNAVAILABILITY (``CalendarUnavailable``), never a civil date: the row is not recordable,
  the cycle is not selectable, the health says so;
* the consensus of a record carries its own publication instant, horizon, currency and hash (explicit nulls);
* the studies' official arm includes the targeted admissions of the generation (universe wins on collision);
* the PostgreSQL row reader rebuilds the canonical record shape, so the stored hash re-verifies after a round trip.

Rev 5 residuals (X1–X4):
* the loser of a chain conflict recomposes on a NEW clock — a recomposition is a new activation, ordered by when it
  actually happened; the D3 refusal of a stale clock protects the explicit path only (see Y1 for the automatic path);
* targeted symbols are normalized (``strip().upper()``) before an explicit selection validates and writes them;
* a consensus ``datetime``/``date`` is kept in ISO form and an empty string is an absent value;
* a universe cycle that has NO record (published while the calendar could not answer) is recorded by the next
  activation pass before validation — records before selection, and the market recovers without a bootstrap.

Rev 5 residuals (Y1–Y4; Y5–Y7 in the docs and the B3 screener):
* the automatic path has NO clock of its own: the activation instant is the wall clock read IMMEDIATELY before each
  INSERT attempt — after the records were written, after the head was re-read — so a generation is dated after any
  decision taken on its predecessor; nothing is clamped to the head's instant (a clamp BACKDATED a generation activated
  later and made ``generation_at`` hand a past decision a generation that was not in force then, Y1); the D3 refusal
  exists only on the explicit path, which carries the mesa's clock (a wall clock behind the head: see Z1);
* a recomposition is retried while the head keeps moving, up to ``RECOMPOSITION_ATTEMPTS``; the limit is a WARNING
  and the decision is left to the next activation pass (Y2);
* the activation pass admits, for every symbol, the most recent REGISTERED targeted cycle newer than the one the
  generation holds — an admission that lost its race (or met a calendar outage) is not lost for the day (Y3);
* targeted keys that collide after normalization never raise on the automatic path: the first occurrence is carried
  (WARNING) and a new admission wins its own key; the ambiguity is a ``ValueError`` only for an explicit order (Y4).

Rev 5 residuals (Z1–Z5):
* a generation is NEVER dated before the generation it chains on — now true on the automatic path too: when the wall
  clock read at the INSERT is not after the head's ``activated_at`` (a host whose clock runs behind another host's),
  the activation instant is ADVANCED to the head's instant + 1 microsecond, with a WARNING; it only advances, never
  recedes (the old clamp reused a pre-records clock and tied with the head). A generation written behind the head was
  never the head for the readers (``max(activated_at)``, memory and SQL alike), so every later writer conflicted on the
  stale head and gave up — the chain was locked (Z1). The explicit path keeps refusing a clock behind the head (D3);
* an explicit order (``select_generation``: a purge, a rollback, a switch) is authoritative over every targeted cycle
  PREDICTED at or before its instant: the recovery of registered-but-unadmitted targeted cycles (Y3) considers only
  cycles predicted AFTER the mesa's last explicit order, so a purge stays purged and a rollback stays on its cycle
  across automatic passes and bootstraps (Z2; the authority clock is the prediction instant — a re-run keeps the
  original's instant, so it never re-opens what the order decided, S1);
* a registered targeted cycle the validator refuses is logged at INFO by the recovery path and recorded in the
  receipt (``targeted_refused``); it is a WARNING only when the refused cycle id changes (Z3);
* the receipt of a targeted admission carries ``attempt``, as the activation pass does (Z4).

Rev 5 residuals (W1–W5):
* the same authority rule holds for UNIVERSE cycles (W1): a market whose candidate cycle was predicted at or before the
  mesa's last explicit order is not new — the automatic pass and the bootstrap carry the cycle in force and name the
  market in ``receipt.held_by_explicit_order``; only a cycle predicted AFTER the order is activated, so a rollback of a
  universe cycle is not undone by the next pass (nor by a re-run of the rolled-back cycle, S1);
* an explicit order carries the mesa's wall clock: a ``now`` in the future beyond ``EXPLICIT_CLOCK_TOLERANCE`` (60 s) is
  refused (``ValueError``), symmetric to the D3 refusal of a clock behind the head (W2);
* an order is recognized by a marker ONLY ``select_generation`` writes (``receipt.explicit = True``), never by
  ``activated_by``; the automatic functions have no ``activated_by`` parameter, and the automatic path strips the
  marker from any receipt it is handed (W3);
* a legacy row chained behind its predecessor (dated before it, pre-Z1) locked the chain: every writer chained on the
  head by ``max(activated_at)`` and conflicted on its UNIQUE successor. When a conflict finds the head unmoved, the writer
  walks to the chain tip (``Database.valuation_official_selection_successor``) and chains on it, dated after it; the
  health reports ``head_has_successor`` while the head is not the chain tip (W4);
* an admission passes the head's known refusals (``receipt.targeted_refused``) to the validator, so a re-run of the same
  refused cycle logs at INFO, not WARNING (W5).

Rev 6 (Codex B1–B3 residuals on rev 5):
* a record carries TWO clocks (B2, spec rev 7 §7-bis TP-B): ``prediction_instant`` — when the prediction was made, the
  ``published_at`` of the ORIGINAL live evaluation — and ``published_at`` — the factual availability of the snapshot that
  contains it (the producing cycle's ``published_at``; for a re-run cycle, the re-run date, never retro-dated). A live
  cycle has both equal; a re-run cycle declares ``inputs.rerun_of`` (the original cycle) and ``inputs.prediction_instant``
  (the original's instant) — without the instant, or with an instant after its own publication, it is not recordable.
  The session is the prediction's (from ``prediction_instant``). ``published_at`` is part of the hashed core
  (``VALUATION_PREDICTION_V2``), a NOT NULL column, round-trips through the PostgreSQL reader, is served as
  ``official_published_at`` and travels with the studies' calls (``ValuationCall.published_at``);
* the mesa's last explicit order governs the DIRECT admission too (B3): ``admit_targeted_cycle`` — hence the persistence
  hook replaying the SAME old cycle (``record_snapshot``, recorded = 0) — holds a targeted cycle predicted at or before
  the order, re-reading the order on EVERY attempt of its loop, so a purge stays purged and a rollback stays on its
  cycle across replays; only a cycle predicted after the order is admitted.

Rev 6 residuals (S1–S10; S6 in the frontend, S9 in the migration, S10 in the docs):
* the authority clock of an explicit order is the PREDICTION instant — ``cycle_clocks(snapshot)[0]``, the record's
  ``prediction_instant``: for a live cycle its publication, for a re-run the ORIGINAL's instant — on all three paths:
  the direct admission (``_predicted_at_or_before``), the recovery (Z2) and the universe path (W1). Comparing the
  publication let a RE-RUN of a purged or rolled-back cycle, published after the order, re-admit the SAME prediction
  the order had decided over (S1); a cycle whose clocks cannot be read is held;
* the direct admission applies the recency rule of the recovery: a targeted cycle whose prediction is not newer than the
  one the generation already holds for the symbol is not admitted (INFO) — a replay of an OLD cycle with no order after
  it no longer downgrades the served number and flip-flops the chain (S2);
* a record whose ``published_at`` precedes its ``prediction_instant`` is refused by ``prediction_from_row`` (``ValueError``)
  and by the memory double of ``insert_valuation_predictions`` — the PostgreSQL CHECK, mirrored (S3);
* the readers of prediction records order by ``(prediction_instant, published_at, insertion)`` — memory and SQL alike
  (``created_at`` in SQL) — so a re-run, tied with its original on ``prediction_instant``, is the latest record for every
  reader, as it is for the selection (S4);
* an unrecordable re-run (no original instant, or one after its own publication) is a WARNING once per cycle id per
  process (``_unrecordable_logged``), INFO after — not two WARNINGs per activation pass forever (S5);
* the studies' loader keeps a call whose ``published_at`` is malformed (``published_at = None``, WARNING) instead of
  dropping the call (S8).

Rev 7 (Codex F393-11 on rev 6 — the historical reference is never rewritten silently):
* the migration NO LONGER backfills a legacy table (the S9 block filled ``published_at = prediction_instant`` into
  rev-5 rows and the reader then served them as ``VALUATION_PREDICTION_V2`` under their V1 hash — an identity nobody
  could recompute): a table without the column that HOLDS rows makes migration 048 fail loudly (``RAISE EXCEPTION``
  naming the row count and the operator path); an empty one gets the column ``NOT NULL`` directly; a table with the
  column only gets the CHECK ensured (F393-11 a). A fresh installation is the supported path of this step;
* every reader honours the STORED schema (``stored_prediction``, F393-11 b): a row whose ``published_at`` is NULL/absent,
  or whose stored schema is V1 (``LEGACY_PREDICTION_SCHEMA``), is rebuilt as the canonical V1 core — WITHOUT
  ``published_at`` — and its ``row_sha256`` is recomputed and verified as V1; it is served as V1 with
  ``official_published_at = None`` (never derived), never relabelled V2. A row that claims V2 without its clock, or
  whose V1 hash does not verify, is an integrity failure: not served (WARNING once per record per process, INFO after),
  and its cycle is not selectable (``cycle_validation`` counts the row unrecorded). PostgreSQL reader and memory double
  apply the same rule; V2 rows are served exactly as before.

Rev 8 / P1 — Passo 1 (spec rev 7 §7.5 item 5, §7-bis item 4; I-TP4): the consensus leaves the official TP by a NEW
selection line, never by editing a number:
* a SECOND official source, ``SOURCE_INTERNAL`` (``official_internal_v1``): the SAME producer cycles, the record ``tp``
  being the row's ``internal_tp`` (``consensus_weight_percent = 0``), its ``buy_in`` the row's ``internal_buy_in`` — the
  producer's own entry rule applied to the internal TP, emitted on the same row (US: ``official_buy_in_v1`` with the
  mirrored entry hurdle; B3: ``_entry_from_tp(internal_tp, …)``; ETFs and the foreign bridge: the same buy-in) — and the
  consensus persisted beside it exactly as in the blend record (``consensus_block``, same ``payload_sha256``); bands
  come from ``internal_bear_tp``/``internal_bull_tp`` (no producer emits bands today: null, never rescaled);
* DUAL RECORDING: ``record_cycle_predictions`` writes, for every cycle, the blend rows as before AND the internal rows in
  ONE insert (same ``source_version`` — the cycle's methodology version; the ``v1`` lives in the source name); a row
  without a positive ``internal_buy_in`` (a cycle produced before Passo 1) has no internal record and the cycle is not
  selectable for the internal source (``unrecorded``) — it is carried, never patched;
* SOURCE-AWARE SELECTION: every per-cycle reader names the source (``Database.valuation_predictions_for_cycle`` /
  ``valuation_prediction_record`` REQUIRE it — a reader blind to the source served the internal row under a blend
  generation, proved on the double); the automatic pass composes generations for the CURRENTLY SELECTED source only
  (``_selected_source``: the head's ``source``, blend when there is no head), so a switch is never undone by the next
  pass and a new cycle without internal records is a carry-over for an internal generation;
* the SWITCH (blend → internal) is ``select_generation(source=SOURCE_INTERNAL, before_after_sha256=<report hash>)`` — an
  explicit order (W3), REFUSED (``ValueError``) while ``OFFICIAL_TP_REPLACEMENT_AUTHORIZED`` is ``False`` (a module
  constant: it flips only by a commit citing the mesa's receipt) and without the hash of the before/after receipt;
  the ROLLBACK is ``select_generation(source=SOURCE_OFFICIAL, cycles=<the previous generation's>)`` by the same path,
  never locked; ``receipt.source_switch`` names ``from``/``to``/``before_after_sha256``;
* CONSUMERS are untouched: they read the selection and their stamps say ``tp_source = official_internal_v1`` after the
  switch; ``_served`` overlays, besides ``our_tp``/``buy_in``, the record's ``consensus_weight_percent`` and the two
  arithmetic identities of the producer (``upside_percent``, ``price_vs_buy_in_percent`` — bit for bit the blend's values
  for a blend record); ``score``/``status``/``expected_total_return_percent`` remain the producer's blend view (a declared
  residue, see the P1 doc); the frozen V3 engine and the pinned ``one_pager.py`` are not edited;
* BEFORE/AFTER: ``before_after_report`` (CLI ``--before-after [--private-detail PATH]``) publishes, for the generation's
  own cycles, per market ``n``, median and p90 of ``tp_internal / tp_blend − 1`` and of ``buy_in_internal / buy_in_blend − 1``
  as an aggregate receipt with ``report_sha256``; the per-symbol detail goes ONLY to the private file, never printed —
  the mesa's order to switch cites ``report_sha256``. The CLI prints it ATTESTED (``attest_before_after``, Codex P2 on
  #451): ``producer_build_sha`` (the deployed revision read by the producing process) and ``receipt_sha256`` over both,
  so a publisher attributes the receipt to the build that computed it, never to one read later by another process.

Rev 8 / P1 residuals (Q1–Q6, internal adversarial verification):
* the hash a switch cites is CHECKED, not just shaped (Q1) and BINDS the proposed composition (C395-1): ``select_generation`` recomputes ``before_after_report`` over the order's exact ``cycles``/``targeted`` — a hash computed over another cycle or another targeted set is refused; on the
  head it read in the same attempt and refuses (``ValueError`` naming both hashes) any ``before_after_sha256`` that is not
  that generation's ``report_sha256`` — a receipt computed on another generation (the head moved since the mesa read it)
  is refused too; the report is deterministic (canonical JSON, sorted keys, no clock), so the mesa's receipt recomputes;
  a switch needs a generation in force (there is no "before" otherwise);
* the served ``buy_in_models`` are the RECORD's (Q2): ``_served`` overlays ``decomposition.buy_in_models`` when the record
  carries any — the internal record's are the producer's ``internal_buy_in_models`` — so a consumer no longer shows the
  blend's entry models under the internal buy-in; for a blend record they are the row's own values, bit for bit;
* an UNKNOWN source is refused at write time (Q3: ``_new_generation`` and ``Database.insert_valuation_official_selection``
  — ``ValueError``, nothing stored) and, should a head carry one anyway (a hand edit), it is NOT servable, loudly:
  ``_selected_source`` returns ``None`` with an ERROR, the readers serve nothing, the automatic pass and the direct
  admission activate nothing under it, the health is ``status = "error"`` naming ``unknown_source``, and the only way
  out is the explicit rollback to the blend (never locked; ``receipt.source_switch.from`` names the unknown source);
* ``selectable_cycles`` re-records a latest cycle with no record of the selected source ONLY when at least one of its rows
  is usable for that source (Q4): a pre-P1 cycle under an internal head is skipped without N no-op inserts per pass;
* the private before/after detail is written with ``O_CREAT | O_EXCL | O_NOFOLLOW`` and mode ``0o600`` (Q5): an existing
  path (a file or a symlink) is refused (``FileExistsError``), nothing is overwritten or followed, the owner alone reads it;
* a switch without an explicit ``source_version`` stamps the validated cycles' methodology versions (Q6: ``"+".join(sorted)``,
  exactly as the automatic pass), never ``"rollback"``; a rollback to the blend keeps ``"rollback"`` unless given.

Rev 9 / P1 — the declared residue closed, the receipt the owner reads, the order as a command (Passo 1 delivery, 2026-10-17):
* THE INTERNAL VIEW: the producers emit, on the same row, the TP-dependent tail of the row evaluated by their OWN rules on the
  internal TP and its buy-in (consensus weight 0) — ``internal_score``, ``internal_status``,
  ``internal_expected_total_return_percent`` (and, where the producer's status depends on a TP plausibility check, B3:
  ``internal_tp_validation_status``/``internal_tp_validation_reasons``); ``_served`` overlays them for an internal record
  (``INTERNAL_VIEW_KEYS``), so the screeners' candidates/matrices and R2D2 rank and filter by the status and score OF THE TP
  THEY SHOW. A row without the view (a cycle produced before this revision) is not usable for the internal source
  (``_usable``: invalid, carried, never patched) and an internal record whose row lacks it is NOT served (never the blend's
  status under the internal TP); the internal record's ``decomposition.status``/``tp_validation_status``/``convergence_weight``
  are the internal ones. Blend records are served exactly as before, bit for bit;
* THE RECEIPT V3 (``BEFORE_AFTER_SCHEMA``): besides the TP/buy-in ratios, per market the SERVED view of both arms — status
  counts and transitions, BUY (``BUY_STATUS``) before/after/entered/left, upside quantiles before/after and their change, the
  score change, TP change buckets — over the pairs served on both sides; ``before_after_markdown`` renders it in Portuguese
  (CLI ``--markdown PATH``, appended: ``$GITHUB_STEP_SUMMARY`` works). No symbol in either; the detail stays private;
* THE LOCK NAMES THE RECEIPT: a switch must cite EXACTLY ``OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256`` — the ``report_sha256`` the
  owner accepted, written in the same commit that flips ``OFFICIAL_TP_REPLACEMENT_AUTHORIZED`` — besides matching the receipt
  recomputed on the head over the order's proposal (Q1/C395-1). A lock commit without a hex-64 receipt switches nothing;
* THE ORDER AS A COMMAND: ``--switch-to-internal --before-after-sha256 H --reason …`` (and ``--rollback-to-blend --reason …``,
  never locked) take the same proposal options as ``--before-after`` and execute ``select_generation`` with the host's wall
  clock; they print the new generation without the targeted symbols.
* THE LOCK COMMIT (a separate commit, merged only after the owner accepts the before/after): ``OFFICIAL_TP_REPLACEMENT_AUTHORIZED
  = True`` and ``OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256`` naming the accepted ``report_sha256`` — committed with
  ``RECEIPT_PLACEHOLDER`` until the acceptance, so the commit switches nothing before the hash is written.

Rev 9 / P1, cross-review (2026-10-17):
* THE FREEZE (F1): the lock commit is merged and deployed AFTER the owner accepts the receipt, so the head must not move
  between the receipt and the order — yet the IR worker republishes the B3 universe on every disclosure, a One Pager
  admits a targeted cycle, the deploy restarts the workers. ``freeze_selection`` (CLI ``--freeze-selection --until …``) is
  an explicit order that re-selects the head's OWN composition (nothing served changes but the generation id) and carries
  ``receipt.freeze.until`` (at most ``FREEZE_MAX`` ahead): while the HEAD carries an unexpired freeze the automatic writers
  (the activation pass, the targeted admission, the bootstrap) activate nothing over it, the IR propagation leaves its
  queue untouched and the B3 producer builds no on-demand cycle — so the receipt computed on the frozen head still
  recomputes when the order lands, and nothing produced in the window is then held by the order (W1). The switch or the
  rollback ends it (an explicit order; its receipt names ``ended_freeze``); past ``until`` everything resumes by itself;
* ``--keep-internal-targeted`` (F2): the proposal keeps the head's targeted admissions that are valid for the internal
  source and drops the others — no longer a blanket purge of valid rev-9 targeted cycles (a purged same-day cycle is
  never rebuilt by the producer that day, so its One Pager failed until the next day);
* THE RATING (F3): the receipt counts, per arm, the One Pager rating of the served upside (``ONE_PAGER_RATING_CUTS``,
  mirrored from the pinned ``one_pager.py``) besides the candidate gate (``BUY_STATUS``), and the summary no longer calls
  the candidate gate "COMPRA" — the word the One Pager uses for its rating.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import math
import os
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .valuation_official_engine import OFFICIAL_SOURCES, SOURCE_BLEND, SOURCE_INTERNAL

logger = logging.getLogger(__name__)

SOURCE_OFFICIAL = SOURCE_BLEND  # "official_blend_v1": the Passo 0 source, the default of every explicit order (a rollback target)
SOURCE_V3_2_SHADOW = "v3_2_shadow"  # the point-in-time re-execution of the V3 engine (valuation_pit_rerun): RECORDABLE, never selectable
# The sources a prediction RECORD may carry (rev 7 TP-B: sources coexist in `valuation_predictions`). The official SELECTION keeps
# reading `OFFICIAL_SOURCES` only: `_selected_source`, `_new_generation` and the store's selection writer refuse `v3_2_shadow` as before.
RECORDABLE_SOURCES: tuple[str, ...] = (*OFFICIAL_SOURCES, SOURCE_V3_2_SHADOW)
OFFICIAL_TP_REPLACEMENT_AUTHORIZED = True  # the Passo 1 lock (spec §7-bis item 4), FLIPPED by this commit together with the receipt it names below — merged only after the owner accepts that before/after receipt
RECEIPT_PLACEHOLDER = "PENDING-OWNER-ACCEPTANCE"  # not hex-64: while the receipt below is this, a switch is refused even with the lock flipped
OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256: str | None = RECEIPT_PLACEHOLDER  # the report_sha256 the owner accepted (replace the placeholder before merging): a switch must cite exactly it
BEFORE_AFTER_SCHEMA = "VALUATION_P1_BEFORE_AFTER_V3"  # V3 (rev 9): the served view of both arms (status/BUY/upside/score); V2 (C395-1) bound the AFTER composition
BUY_STATUS = "full_match"  # what the receipt counts as a CANDIDATE: the screeners' candidate gate (the B3 list also dedups issuers and asks the power zone)
ONE_PAGER_RATING_CUTS: tuple[tuple[str, float], ...] = (  # the One Pager's rating of the upside (one_pager.py, pinned): the first cut the upside reaches
    ("COMPRA", 25.0), ("ACUMULAR", 10.0), ("NEUTRO", -10.0),
)
ONE_PAGER_RATING_FLOOR = "REDUZIR"  # below the last cut
FREEZE_MAX = timedelta(hours=16)  # the longest freeze the mesa may order (F1): from the morning receipt to the evening order
FREEZE_NIGHTLY_ZONE = ZoneInfo("America/Sao_Paulo")  # the valuation worker's nightly cycle is due at midnight here: a freeze never spans it (F1)
INTERNAL_VIEW_KEYS = {  # served key → the producer's internal-view field (rev 9): the TP-dependent tail of the row on the internal TP
    "score": "internal_score", "status": "internal_status", "expected_total_return_percent": "internal_expected_total_return_percent",
}
INTERNAL_VIEW_OPTIONAL_KEYS = {  # overlaid when the producer emits them (B3: its status depends on a TP plausibility check)
    "tp_validation_status": "internal_tp_validation_status", "tp_validation_reasons": "internal_tp_validation_reasons",
}
P90_METHOD = "linear interpolation at (n-1)*0.9"
TP_CHANGE_BUCKETS: tuple[tuple[str, float], ...] = (  # rev 9: |tp_internal / tp_blend − 1| below each bound (the last bucket: ge_25pct)
    ("lt_1pct", 0.01), ("1_to_5pct", 0.05), ("5_to_10pct", 0.10), ("10_to_25pct", 0.25),
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PREDICTION_SCHEMA = "VALUATION_PREDICTION_V2"  # V2 (rev 6, B2): `published_at` joined the hashed core
LEGACY_PREDICTION_SCHEMA = "VALUATION_PREDICTION_V1"  # rev 5: one clock — a stored V1 row is read, verified and served as V1, never relabelled (F393-11)
SELECTION_SCHEMA = "VALUATION_OFFICIAL_SELECTION_V1"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
UNIVERSE_ANALYSIS = "valuation_universe"
TARGETED_ANALYSIS = "security_valuation"
ACTIVATED_BY = "valuation_official.activate_generation"
SESSION_ZONES = {"B3": ZoneInfo("America/Sao_Paulo"), "NASDAQ": ZoneInfo("America/New_York"), "NYSE": ZoneInfo("America/New_York")}
CALENDARS = {"B3": "BVMF", "NASDAQ": "XNYS", "NYSE": "XNYS"}
UNRESOLVED: Any = object()  # "the caller did not resolve a generation": readers resolve the current one themselves
_calendars: dict[str, Any] = {}
CONSENSUS_HORIZON = "12m"  # a public analyst consensus is a 12-month target unless the producer says otherwise
RECOMPOSITION_ATTEMPTS = 5  # a writer recomposes on a moved head this many times before leaving it to the next pass (Y2)
EXPLICIT_CLOCK_TOLERANCE = timedelta(seconds=60)  # an explicit order carries the mesa's wall clock: further ahead of ours is a wrong clock (W2)
CHAIN_WALK_LIMIT = 64  # successors followed from an unmoved head to the chain tip before giving up (W4)
_refusals_logged: dict[str, str] = {}  # symbol → the refused targeted cycle this PROCESS already warned about (Z3; the receipt carries it across processes)
_unrecordable_logged: set[str] = set()  # re-run cycle ids this PROCESS already warned were not recordable (S5): the repeats are INFO
_integrity_logged: set[str] = set()  # stored record ids this PROCESS already warned could not be verified (F393-11): the repeats are INFO
_viewless_logged: set[str] = set()  # internal records this PROCESS already warned had no internal view on their row (rev 9): the repeats are INFO


class CalendarUnavailable(RuntimeError):
    """The exchange calendar could not answer for this market/instant: the session is UNKNOWN. Callers never fall
    back to a civil date (a Sunday would become a session, F393-6): the row is not recordable, the cycle not selectable."""


ITEM_STAMP_KEYS = {  # served-row key → API item field (F393-6: the full stamp travels with every served number)
    "tp_source": "tp_source", "generation_id": "official_generation_id", "official_cycle_id": "official_cycle_id",
    "tp_source_version": "tp_source_version", "official_session_date": "official_session_date",
    "prediction_instant": "prediction_instant", "official_row_sha256": "official_row_sha256",
    "official_published_at": "official_published_at",  # rev 6 (B2): the record's own publication clock, distinct from the prediction's
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number + 0.0  # -0.0 → 0.0: JSONB has no signed zero, and the hash must survive the round trip


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _calendar(market: str) -> Any:
    name = CALENDARS[market]
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def session_date_of(market: str, instant: datetime) -> str:
    """The market session a prediction belongs to: the last COMPLETED session of the market's exchange calendar at
    ``instant`` (close ≤ instant) — B3 on BVMF, NASDAQ/NYSE on XNYS. A prediction published on a Sunday night, on a
    holiday or during the session belongs to the previous session (F393-6); never the civil date of any zone.
    When the calendar cannot answer (missing, out of range, broken) the session is unknown: ``CalendarUnavailable``,
    logged — a civil-date fallback would mint a Sunday session and a wrong identity (rev 5, F393-6 c)."""
    at = _utc(instant)
    local_day = at.astimezone(SESSION_ZONES[market]).date().isoformat()
    try:
        calendar = _calendar(market)
        session = calendar.date_to_session(local_day, direction="previous")
        if _utc(calendar.session_close(session).to_pydatetime()) > at:
            session = calendar.previous_session(session)
        return session.date().isoformat()
    except Exception as error:
        logger.warning("session_date_of(%s, %s): calendar unavailable (%s: %s) — session unknown, nothing recorded or selected",
                       market, at.isoformat(), type(error).__name__, error)
        raise CalendarUnavailable(f"{market} calendar unavailable at {at.isoformat()}: {type(error).__name__}") from error


def market_of_entity(analysis_type: str, entity_key: str) -> str | None:
    """`valuation_universe` entities are ``<MARKET>_UNIVERSE``; targeted B3 valuations are keyed by the ticker."""
    if analysis_type == UNIVERSE_ANALYSIS:
        market = entity_key.removesuffix("_UNIVERSE")
        return market if market in MARKETS else None
    if analysis_type == TARGETED_ANALYSIS:
        return "B3"
    return None


def currency_of(market: str) -> str:
    return "BRL" if market == "B3" else "USD"


def _normalized_snapshot(snapshot: Mapping[str, Any], *, analysis_type: str, entity_key: str) -> dict[str, Any]:
    """Storage readers may return a snapshot without ``analysis_type``/``entity_key`` (the PostgreSQL path of
    ``latest_analysis_snapshot`` does): the caller always knows both, so they are re-attached here (F393-1)."""
    return {**snapshot, "analysis_type": analysis_type, "entity_key": entity_key}


def provenance_sha256(rows: list[Mapping[str, Any]]) -> str:
    """The manifest hash a producer records with its cycle (E1): the provenance of every row it published (symbol,
    source, fundamentals date, quote instant), canonical and sorted — what a re-execution must reproduce."""
    manifest = sorted(
        [str(row.get("symbol") or "").strip().upper(), str(row.get("source_name") or row.get("history_source") or ""),
         str(row.get("fundamentals_as_of") or ""), str(row.get("as_of") or "")]
        for row in rows if isinstance(row, Mapping) and row.get("symbol")
    )
    return canonical_sha256(manifest)


def _analyst_count(row: Mapping[str, Any]) -> int | None:
    number = _number(row.get("analyst_count"))
    return int(number) if number is not None else None


def _text_or_none(value: Any) -> str | None:
    """A producer's textual field as the record keeps it: ``None`` for an absent OR EMPTY value (``''`` is not an
    instant), a ``datetime``/``date`` as its ISO form (never ``str()``, whose ``T`` is a space), text stripped."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def consensus_block(row: Mapping[str, Any], *, market: str) -> dict[str, Any]:
    """The consensus of reference a record carries, with its OWN identity (rev 5, F393-6 b): what it says (``tp``,
    ``analyst_count``, ``gap_percent``), where it comes from (``source``), WHEN it was published (``published_at`` —
    the producer's ``consensus_published_at``, else its ``consensus_as_of``; ``as_of`` is kept as the producer wrote
    it), for which ``horizon`` (the producer's, else ``12m`` for any public consensus, null without one), in which
    ``currency`` (the producer's, else the market's — the producer converts the consensus into the market's currency;
    null without one), and ``payload_sha256`` — the canonical hash of all the other fields. Every key is always
    present; absent values are explicit ``null``. A ``datetime``/``date`` the producer hands over is kept in ISO form
    (never ``str()``), and an empty string is an absent value (X3)."""
    tp = _positive(row.get("public_consensus_tp"))
    published = _text_or_none(row.get("consensus_published_at")) or _text_or_none(row.get("consensus_as_of"))
    payload = {
        "tp": tp,
        "source": _text_or_none(row.get("consensus_origin_source")),
        "analyst_count": _analyst_count(row),
        "as_of": _text_or_none(row.get("consensus_as_of")),
        "published_at": published,
        "horizon": _text_or_none(row.get("consensus_horizon")) or (CONSENSUS_HORIZON if tp is not None else None),
        "currency": _text_or_none(row.get("consensus_currency")) or (currency_of(market) if tp is not None else None),
        "gap_percent": _number(row.get("consensus_gap_percent")),
    }
    return {**payload, "payload_sha256": canonical_sha256(payload)}


def internal_view(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """The producer's INTERNAL VIEW of a row (rev 9): the TP-dependent tail — Power Score, status, expected return (and,
    when emitted, the TP validation the status depends on) — that the producer evaluated by its own rules on the internal TP
    and its buy-in, keyed as served (``INTERNAL_VIEW_KEYS``/``INTERNAL_VIEW_OPTIONAL_KEYS``). ``None`` when a required field
    is absent or not a number/text — a row produced before rev 9 — which makes the row unusable for the internal source
    and its internal record unservable: an internal TP is never shown under the blend's status or score. Copies."""
    score = _number(row.get(INTERNAL_VIEW_KEYS["score"]))
    expected = _number(row.get(INTERNAL_VIEW_KEYS["expected_total_return_percent"]))
    status = _text_or_none(row.get(INTERNAL_VIEW_KEYS["status"]))
    if score is None or expected is None or status is None:
        return None
    view: dict[str, Any] = {"score": score, "status": status, "expected_total_return_percent": expected}
    for served_key, key in INTERNAL_VIEW_OPTIONAL_KEYS.items():
        if key in row:
            view[served_key] = copy.deepcopy(row[key])
    return view


def prediction_from_row(row: Mapping[str, Any], *, market: str, scope: str, cycle_id: str, source_version: str,
                        prediction_instant: datetime, source_manifest_sha256: str | None = None,
                        published_at: datetime | None = None, rerun_of: str | None = None,
                        source: str = SOURCE_OFFICIAL, extra_provenance: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The immutable record of one canonical row. ``None`` when the row carries no usable official TP
    (no symbol, TP or buy-in) — such rows are not predictions and never become official — or when the market's
    session is unknown (``CalendarUnavailable``: an identity cannot be minted from a civil date, rev 5). Every field
    the contract names is present — absent values are explicit ``null``, never dropped (F393-6).
    Two clocks (rev 6, B2): ``prediction_instant`` is WHEN THE PREDICTION WAS MADE (the original live evaluation's
    publication; the session is its); ``published_at`` is when the snapshot that contains this record became available
    (defaults to ``prediction_instant`` — a live cycle; a re-run passes its own date and names ``rerun_of``). Both are
    hashed. A ``published_at`` BEFORE ``prediction_instant`` is a ``ValueError`` (S3) — the PostgreSQL CHECK, applied
    before any record exists. ``Database._prediction_record`` rebuilds EXACTLY this shape from a PostgreSQL row: change
    both together.
    ``source`` (Passo 1): ``SOURCE_OFFICIAL`` reads the blend (``our_tp``/``buy_in``, the producer's weight and models);
    ``SOURCE_INTERNAL`` reads the SAME row's ``internal_tp``/``internal_buy_in`` (the buy-in the producer derived from the
    internal TP by its own rule; absent or non-positive → ``None``: not recordable in that source), writes
    ``consensus_weight_percent = 0`` (top level and ``decomposition.weights``), ``decomposition.buy_in_models`` from
    ``internal_buy_in_models`` (else the producer's), bands from ``internal_bear_tp``/``internal_bull_tp`` (null when the
    producer emits none — never rescaled) — and keeps EVERYTHING else identical: the consensus of reference with its own
    identity (``consensus_block``, same ``payload_sha256``), methods, calibration, provenance, both clocks. Rev 9: the internal
    record's ``decomposition.status`` is the producer's ``internal_status`` (null on a row without the internal view — never
    the blend's), its ``tp_validation_status`` the ``internal_tp_validation_status`` when emitted and its
    ``weights.convergence_weight`` the ``internal_convergence_weight`` when emitted (else the row's, TP-independent).
    ``extra_provenance`` (the point-in-time re-execution, ``valuation_pit_rerun``): JSON-ready keys MERGED into
    ``decomposition.provenance`` after the fixed ones (a fixed key is never overridden) — hashed with the record, stored in
    the JSONB column, rebuilt by the PostgreSQL reader as any other provenance field. ``None`` for every producer today."""
    if source not in RECORDABLE_SOURCES:
        raise ValueError(f"unknown recordable source {source!r}; expected one of {RECORDABLE_SOURCES}")
    internal = source == SOURCE_INTERNAL
    symbol = str(row.get("symbol") or "").strip().upper()
    if internal:
        tp, buy_in = _positive(row.get("internal_tp")), _positive(row.get("internal_buy_in"))
    else:
        tp, buy_in = _positive(row.get("our_tp")), _positive(row.get("buy_in"))
    if not symbol or tp is None or buy_in is None:
        return None
    instant = _utc(prediction_instant)
    available = _utc(published_at) if published_at is not None else instant
    if available < instant:
        raise ValueError(f"published_at {available.isoformat()} precedes prediction_instant {instant.isoformat()} for {market}/{symbol} of cycle {cycle_id}: "
                         "a prediction cannot be made after the snapshot that contains it became available (B2)")
    try:
        session_date = session_date_of(market, instant)
    except CalendarUnavailable as error:
        logger.warning("valuation_official: %s/%s of cycle %s not recordable — %s", market, symbol, cycle_id, error)
        return None
    methods = row.get("methods")
    buy_in_models = row.get("buy_in_models")
    if internal and isinstance(row.get("internal_buy_in_models"), Mapping):
        buy_in_models = row.get("internal_buy_in_models")
    bear_key, bull_key = ("internal_bear_tp", "internal_bull_tp") if internal else ("bear_tp", "bull_tp")
    bear_tp, bull_tp = _positive(row.get(bear_key)), _positive(row.get(bull_key))
    consensus_weight_percent = 0.0 if internal else _number(row.get("consensus_weight_percent"))
    status, validation_status, convergence_weight = row.get("status"), row.get("tp_validation_status"), row.get("convergence_weight")
    if internal:  # rev 9: the internal record names the producer's internal view, never the blend's status
        status = row.get("internal_status")
        validation_status = row["internal_tp_validation_status"] if "internal_tp_validation_status" in row else validation_status
        convergence_weight = row["internal_convergence_weight"] if "internal_convergence_weight" in row else convergence_weight
    core = {
        "schema": PREDICTION_SCHEMA,
        "source": source,
        "source_version": str(source_version),
        "market": market,
        "symbol": symbol,
        "scope": scope,
        "session_date": session_date,
        "cycle_id": str(cycle_id),
        "prediction_instant": instant.isoformat(),
        "published_at": available.isoformat(),
        "tp": tp,
        "buy_in": buy_in,
        "internal_tp": _positive(row.get("internal_tp")),
        "bear_tp": bear_tp,
        "bull_tp": bull_tp,
        "consensus_tp": _positive(row.get("public_consensus_tp")),
        "consensus_source": _text_or_none(row.get("consensus_origin_source")),
        "analyst_count": _analyst_count(row),
        "consensus_weight_percent": consensus_weight_percent,
        "price": _positive(row.get("price")),
        "currency": currency_of(market),
        "decomposition": {
            "methods": {str(k): _number(v) for k, v in methods.items()} if isinstance(methods, Mapping) else {},
            "buy_in_models": {str(k): _number(v) for k, v in buy_in_models.items()} if isinstance(buy_in_models, Mapping) else {},
            "weights": {
                "calibration_factor": _number(row.get("calibration_factor")),
                "convergence_weight": _number(convergence_weight),
                "consensus_weight_percent": consensus_weight_percent,
            },
            "bands": {"bear_tp": bear_tp, "bull_tp": bull_tp},
            "consensus": consensus_block(row, market=market),
            "valuation_profile": row.get("valuation_profile"),
            "risk_score": _number(row.get("risk_score")),
            "valuation_confidence": _number(row.get("valuation_confidence")),
            "method_dispersion_percent": _number(row.get("method_dispersion_percent")),
            "signal_quality": row.get("signal_quality"),
            "status": status,
            "tp_validation_status": validation_status,
            "provenance": {
                "source_name": row.get("source_name") or row.get("history_source") or None,
                "fundamentals_as_of": row.get("fundamentals_as_of") or None,
                "as_of": _text_or_none(row.get("as_of")),  # ISO for a datetime, null for '' (X3, as the consensus block)
                "source_manifest_sha256": source_manifest_sha256,
                "rerun_of": str(rerun_of) if rerun_of else None,  # the original cycle a re-run reproduces (B2); null for a live cycle
            },
        },
    }
    if extra_provenance:
        fixed = core["decomposition"]["provenance"]
        core["decomposition"]["provenance"] = {**{str(k): v for k, v in extra_provenance.items() if str(k) not in fixed}, **fixed}
    return {**core, "id": str(uuid4()), "row_sha256": canonical_sha256(core)}


def _integrity_failure(record: Mapping[str, Any], reason: str) -> None:
    key = str(record.get("id") or f"{record.get('market')}/{record.get('symbol')}/{record.get('cycle_id')}")
    level = logging.INFO if key in _integrity_logged else logging.WARNING
    _integrity_logged.add(key)
    logger.log(level, "valuation_official: stored record %s (%s/%s of cycle %s) is not served — %s; its identity is not verifiable and the cycle "
               "is not selectable (F393-11)", record.get("id"), record.get("market"), record.get("symbol"), record.get("cycle_id"), reason)


def _stored_as_legacy(record: Mapping[str, Any]) -> bool:
    """Whether a stored row was written by the rev-5 emitter (``VALUATION_PREDICTION_V1``): its stored schema says so
    (the memory double keeps the record's ``schema``), its ``published_at`` is NULL/absent (the column joined after it),
    or its provenance has no ``rerun_of`` key — the fingerprint of the rev-6 emitter, which always writes it (``null``
    for a live cycle): a PostgreSQL row has no schema column, and this is what tells a V1 row whose ``published_at`` was
    filled in place (the auditor's counterproof) from a V2 row."""
    if record.get("schema") == LEGACY_PREDICTION_SCHEMA or record.get("published_at") is None:
        return True
    if record.get("schema") == PREDICTION_SCHEMA:
        # An explicit V2 schema with its clock present is V2 (the memory double keeps it); the provenance
        # fingerprint below only decides for a PostgreSQL row, which carries no schema column.
        return False
    decomposition = record.get("decomposition")
    provenance = decomposition.get("provenance") if isinstance(decomposition, Mapping) else None
    return not (isinstance(provenance, Mapping) and "rerun_of" in provenance)


def stored_prediction(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """The record a reader SERVES for a stored row, under the schema the row was STORED with — never relabelled (F393-11 b).
    A V2 row (its ``published_at`` present, the rev-6 provenance, a V2 or absent schema — a PostgreSQL row has no schema
    column) is served as it is. A legacy rev-5 row (``_stored_as_legacy``) is rebuilt as the canonical V1 core — WITHOUT
    ``published_at``, the decomposition as stored — and its ``row_sha256`` is RECOMPUTED as V1 and verified; it is served
    with ``schema`` V1 and no ``published_at`` (``official_published_at`` is ``None``, never derived from the prediction's
    instant). A V1 row that carries a ``published_at`` (filled in place, which the migration and the append-only trigger
    both refuse) is served as V1 under its verified V1 hash, the filled clock IGNORED, with a WARNING: nothing is ever
    served under an identity that does not recompute. A row that claims V2 (or any other schema) without its clock, or
    whose V1 hash does not verify, is an integrity failure: ``None`` — not served, the cycle not selectable
    (``cycle_validation`` counts the row unrecorded) — with a WARNING the first time this process meets the record and
    INFO after (``_integrity_logged``, as S5). Every reader — the PostgreSQL reader ``Database._prediction_record`` and
    the memory double — passes through here; a V2 row is what it was before this rule."""
    claimed = record.get("schema")
    if claimed not in (None, PREDICTION_SCHEMA, LEGACY_PREDICTION_SCHEMA):
        _integrity_failure(record, f"it claims an unknown schema {claimed!r}")
        return None
    if claimed == PREDICTION_SCHEMA and record.get("published_at") is None:
        _integrity_failure(record, f"it claims schema {PREDICTION_SCHEMA} but carries no published_at")
        return None
    if not _stored_as_legacy(record):
        return {"schema": PREDICTION_SCHEMA, **{key: value for key, value in record.items() if key != "schema"}}
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256", "schema", "published_at")}
    rebuilt = {"schema": LEGACY_PREDICTION_SCHEMA, **core}
    stored_hash = str(record.get("row_sha256") or "")
    recomputed = canonical_sha256(rebuilt)
    if recomputed != stored_hash:
        _integrity_failure(record, f"its stored row_sha256 {stored_hash[:12]}… does not verify as {LEGACY_PREDICTION_SCHEMA} (recomputed {recomputed[:12]}…)")
        return None
    if record.get("published_at") is not None:
        key = f"filled:{record.get('id')}"
        level = logging.INFO if key in _integrity_logged else logging.WARNING
        _integrity_logged.add(key)
        logger.log(level, "valuation_official: legacy %s record %s (%s/%s of cycle %s) carries a published_at (%s) it was not hashed with — a row "
                   "filled in place; the clock is ignored and the record is served as V1 under its verified hash (F393-11)", LEGACY_PREDICTION_SCHEMA,
                   record.get("id"), record.get("market"), record.get("symbol"), record.get("cycle_id"), record.get("published_at"))
    return {**rebuilt, "id": str(record.get("id")), "row_sha256": stored_hash}


def cycle_rows(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    outputs = snapshot.get("outputs")
    if not isinstance(outputs, Mapping):
        return []
    if snapshot.get("analysis_type") == UNIVERSE_ANALYSIS:
        rows = outputs.get("rows")
        return [dict(item) for item in rows if isinstance(item, Mapping)] if isinstance(rows, list) else []
    row = outputs.get("row")
    return [dict(row)] if isinstance(row, Mapping) else []


def cycle_clocks(snapshot: Mapping[str, Any]) -> tuple[datetime, datetime, str | None] | None:
    """The two clocks of a producer cycle (rev 6, B2): ``(prediction_instant, published_at, rerun_of)``. A LIVE cycle
    predicts at its own publication: both clocks are its ``published_at``. A RE-RUN cycle names the original cycle
    (``inputs.rerun_of``) and the original's instant (``inputs.prediction_instant``, spec rev 7 line 223): its
    ``prediction_instant`` is that original instant and its ``published_at`` is the re-run's own publication — never
    retro-dated. ``None`` (not recordable) when a re-run does not name the original's instant, or names one AFTER its
    own publication (a prediction cannot be made after the snapshot that contains it became available) — a WARNING the
    first time this process meets the cycle, INFO after (``_unrecordable_logged``): every activation pass re-reads the
    latest snapshot of the market, and an unrecordable one is met twice per pass, forever (S5)."""
    if not snapshot.get("published_at"):
        return None
    available = _utc(snapshot["published_at"])
    inputs = snapshot.get("inputs") if isinstance(snapshot.get("inputs"), Mapping) else {}
    rerun_of = _text_or_none(inputs.get("rerun_of")) if isinstance(inputs, Mapping) else None
    if rerun_of is None:
        return available, available, None
    declared = inputs.get("prediction_instant") if isinstance(inputs, Mapping) else None
    try:
        instant = _utc(declared) if _text_or_none(declared) is not None else None
    except (TypeError, ValueError):
        instant = None
    if instant is not None and instant <= available:
        return instant, available, rerun_of
    cycle_id = str(snapshot.get("id"))
    level = logging.INFO if cycle_id in _unrecordable_logged else logging.WARNING
    _unrecordable_logged.add(cycle_id)
    if instant is None:
        logger.log(level, "valuation_official: cycle %s is a re-run of %s but names no original prediction_instant — not recordable (B2)", cycle_id, rerun_of)
    else:
        logger.log(level, "valuation_official: cycle %s is a re-run of %s dated %s, AFTER its own publication %s — not recordable (B2)",
                   cycle_id, rerun_of, instant.isoformat(), available.isoformat())
    return None


def _usable(row: Mapping[str, Any], source: str = SOURCE_OFFICIAL) -> bool:
    """A row with everything a prediction of ``source`` needs: symbol, price, blend TP, buy-in, internal TP — and, for
    ``SOURCE_INTERNAL``, the buy-in the producer derived from the internal TP (``internal_buy_in``, Passo 1) and the
    producer's internal view (``internal_view``: score/status/expected return on the internal TP, rev 9) — a row without
    it would serve the internal TP under the blend's status."""
    base = bool(str(row.get("symbol") or "").strip() and _positive(row.get("price")) and _positive(row.get("our_tp"))
                and _positive(row.get("buy_in")) and _positive(row.get("internal_tp")))
    return base and (source != SOURCE_INTERNAL or (_positive(row.get("internal_buy_in")) is not None and internal_view(row) is not None))


def cycle_validation(snapshot: Mapping[str, Any], *, recorded: Mapping[str, Mapping[str, Any]] | None = None,
                     source: str = SOURCE_OFFICIAL) -> dict[str, Any]:
    """Whether a cycle is COMPLETE, VALID and RECORDED enough to be selectable FOR ``source``: it finished (it was
    published), it has rows, every row is a usable prediction (symbol, price, TP, buy-in, internal TP; for the internal
    source the internal buy-in too, Passo 1), its market session is KNOWN (the exchange calendar answered for
    ``published_at`` — an unavailable calendar makes the cycle unselectable, never a civil-date session, rev 5) and —
    when ``recorded`` (the records of THAT source) is given — every usable row already has its immutable prediction
    record (selection never precedes the records, F393-5). Coverage against the producer's universe size is recorded,
    never presumed. The same rule admits targeted cycles (automatic and explicit paths alike, F393-4). A cycle produced
    before Passo 1 (no ``internal_buy_in``) or before rev 9 (no internal view) is invalid for the internal source and valid
    for the blend: it is carried."""
    rows = cycle_rows(snapshot)
    outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), Mapping) else {}
    universe_size = _number(outputs.get("universe_size")) if isinstance(outputs, Mapping) else None
    invalid = [str(row.get("symbol") or "?") for row in rows if not _usable(row, source)]
    unrecorded: list[str] = []
    if recorded is not None:
        unrecorded = [str(row["symbol"]).strip().upper() for row in rows if _usable(row, source) and str(row["symbol"]).strip().upper() not in recorded]
    market = market_of_entity(str(snapshot.get("analysis_type") or ""), str(snapshot.get("entity_key") or ""))
    session_date: str | None = None
    calendar_unavailable = False
    clocks = cycle_clocks(snapshot)  # the session is the PREDICTION's (a re-run keeps the original's session, B2)
    if market is not None and clocks is not None:
        try:
            session_date = session_date_of(market, clocks[0])
        except CalendarUnavailable:
            calendar_unavailable = True
    return {
        "cycle_id": str(snapshot.get("id")),
        "source": source,
        "rows": len(rows),
        "universe_size": universe_size,
        "coverage": (len(rows) / universe_size) if universe_size else None,
        "invalid_rows": invalid[:20],
        "invalid_count": len(invalid),
        "unrecorded_count": len(unrecorded),
        "session_date": session_date,
        "calendar_unavailable": calendar_unavailable,
        "valid": bool(rows) and not invalid and not unrecorded and (market is None or session_date is not None),
        "published_at": _utc(snapshot["published_at"]).isoformat() if snapshot.get("published_at") else None,
        "prediction_instant": clocks[0].isoformat() if clocks else None,  # the authority clock of an explicit order (S1): a re-run's is the original's
    }


def _source_version(snapshot: Mapping[str, Any]) -> str:
    inputs = snapshot.get("inputs")
    if isinstance(inputs, Mapping) and inputs.get("methodology_version") is not None:
        return str(inputs["methodology_version"])
    return str(snapshot.get("methodology_version_id") or "unknown")


def _manifest_sha(snapshot: Mapping[str, Any]) -> str | None:
    inputs = snapshot.get("inputs")
    if isinstance(inputs, Mapping):
        value = inputs.get("source_manifest_sha256")
        return str(value) if value else None
    return None


def record_cycle_predictions(database: Any, snapshot: Mapping[str, Any]) -> int:
    """The records of one producer cycle, written (append-only, idempotent: the unique key ignores a re-insert) —
    NOTHING else: no activation, no admission. Returns how many records were new, over BOTH official sources (Passo 1,
    dual recording): the blend rows as before AND the internal rows (``SOURCE_INTERNAL``), in ONE insert, the same
    ``source_version`` (the cycle's methodology version; the unique key differs by ``source``). A row without a usable
    internal buy-in yields no internal record — a cycle produced before Passo 1 records 0 internal rows and is not
    selectable for the internal source. An unavailable calendar makes NO row recordable (one warning per cycle, not one
    per row); the cycle can be recorded later, when the calendar answers again (``selectable_cycles`` does so before
    validating, X4)."""
    analysis_type = str(snapshot.get("analysis_type") or "")
    market = market_of_entity(analysis_type, str(snapshot.get("entity_key") or ""))
    if market is None:
        return 0
    scope = "universe" if analysis_type == UNIVERSE_ANALYSIS else "targeted"
    clocks = cycle_clocks(snapshot)  # (prediction_instant, published_at, rerun_of): a re-run keeps the original's instant (B2)
    if clocks is None:
        return 0
    instant, available, rerun_of = clocks
    try:
        session_date_of(market, instant)
    except CalendarUnavailable as error:
        logger.warning("valuation_official: cycle %s (%s) not recorded — %s", snapshot.get("id"), market, error)
        return 0
    rows = cycle_rows(snapshot)
    records = [record for record in (prediction_from_row(row, market=market, scope=scope, cycle_id=str(snapshot["id"]),
                                                          source_version=_source_version(snapshot), prediction_instant=instant,
                                                          source_manifest_sha256=_manifest_sha(snapshot), published_at=available, rerun_of=rerun_of,
                                                          source=source)
                                     for source in OFFICIAL_SOURCES for row in rows) if record is not None]
    return int(database.insert_valuation_predictions(records)) if records else 0


def _selected_source(generation: Mapping[str, Any] | None) -> str | None:
    """The source the official selection is on (Passo 1): the head's ``source``; the blend when there is no head yet
    (the bootstrap) — the automatic pass composes generations for this source only, and every reader of a generation's
    records names it. A generation whose ``source`` is not one of ``OFFICIAL_SOURCES`` (never written by this module —
    a hand edit of the row) is NOT servable (Q3): ``None``, with an ERROR on every read — the readers serve nothing,
    the writers activate nothing under it, the health says so; the explicit rollback to the blend is the way out."""
    if not generation:
        return SOURCE_OFFICIAL
    source = generation.get("source")
    if source in OFFICIAL_SOURCES:
        return str(source)
    logger.error("valuation_official: generation %s selects an UNKNOWN source %r (expected one of %s) — nothing is served and nothing is "
                 "activated under it until the mesa selects a known source by explicit order (rollback to the blend, never locked; Q3)",
                 generation.get("generation_id"), source, OFFICIAL_SOURCES)
    return None


def selection_freeze(generation: Mapping[str, Any] | None, *, now: datetime) -> dict[str, Any] | None:
    """The freeze the HEAD carries and that still holds at ``now`` (F1) — ``{"generation_id", "until", "reason"}`` — or
    ``None``. Only an explicit order written by ``freeze_selection`` carries one, and only the head's counts: while a head
    is frozen no automatic writer chains on it, so the next generation is an order of the mesa (the switch, the rollback, a
    new freeze) or — once ``until`` has passed — the first automatic pass, and either way the freeze is gone. Always
    bounded: ``until`` never reads later than the order's own ``activated_at`` + ``FREEZE_MAX``, and an unreadable ``until``
    (never written by this module) reads as that bound."""
    receipt = (generation or {}).get("receipt") or {}
    freeze = receipt.get("freeze")
    if not generation or not isinstance(freeze, Mapping) or receipt.get("explicit") is not True:
        return None
    bound = _utc(generation["activated_at"]) + FREEZE_MAX
    try:
        until = min(_utc(freeze.get("until")), bound)
    except (TypeError, ValueError):
        until = bound
    if _utc(now) >= until:
        return None
    return {"generation_id": str(generation["generation_id"]), "until": until.isoformat(), "reason": receipt.get("reason")}


def selection_frozen(database: Any, *, now: datetime | None = None) -> dict[str, Any] | None:
    """``selection_freeze`` of the generation in force at ``now`` (the wall clock by default): what a producer asks before
    publishing a cycle the frozen head could not take (the IR propagation, the on-demand B3 valuation, F1)."""
    return selection_freeze(database.latest_valuation_official_selection(), now=now or datetime.now(timezone.utc))


def freeze_selection(database: Any, *, now: datetime, until: datetime, reason: str, activated_by: str) -> dict[str, Any]:
    """The mesa's FREEZE (F1): an explicit order that re-selects the head's OWN composition — cycles, targeted admissions
    (normalized as the automatic carry-over does), source, ``source_version`` and session dates, nothing validated anew and
    nothing served changed but the generation id and its stamp — with ``receipt.freeze = {"until": …}``. Until then the
    automatic writers (``activate_generation_if_changed``, ``admit_targeted_cycle``, the bootstrap) activate nothing over it,
    the IR propagation leaves its queue untouched and the B3 producer builds no on-demand cycle (``selection_frozen``): the
    before/after receipt computed on the frozen head still recomputes when the order lands — after the lock commit's review,
    merge and deploy — and nothing is produced in the window for the order to hold (W1). The switch or the rollback (both
    explicit) ends it, naming it in ``receipt.ended_freeze``; past ``until`` everything resumes by itself (the first
    universe publication or ``--bootstrap`` composes the pending cycles; they were predicted after the freeze, so W1 lets
    them in). Like every order it is authoritative over the cycles predicted at or before it (W1/Z2) — the head's own, in
    practice. ``now`` is the mesa's wall clock (W2: not ahead of ours by more than ``EXPLICIT_CLOCK_TOLERANCE``); ``until``
    must be after it, at most ``FREEZE_MAX`` ahead and not past the next midnight in ``FREEZE_NIGHTLY_ZONE`` (the nightly
    cycle is never frozen out). ``ValueError`` without a generation in force, under a head whose source is unknown (Q3:
    roll back first), on a naive or out-of-bounds ``until``, or when the chain moves meanwhile (the mesa re-reads)."""
    instant = _utc(now)
    wall = datetime.now(timezone.utc)
    if instant > wall + EXPLICIT_CLOCK_TOLERANCE:
        raise ValueError(f"activation clock {instant.isoformat()} is in the future by more than {int(EXPLICIT_CLOCK_TOLERANCE.total_seconds())} s "
                         f"(wall clock {wall.isoformat()}) — the order carries the mesa's wall clock")
    if not isinstance(until, datetime) or until.tzinfo is None:
        raise ValueError(f"the freeze's until must be an aware instant (an offset or a zone), got {until!r}")
    end = _utc(until)
    local = instant.astimezone(FREEZE_NIGHTLY_ZONE)
    midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=FREEZE_NIGHTLY_ZONE).astimezone(timezone.utc)
    if end <= instant:
        raise ValueError(f"the freeze's until {end.isoformat()} is not after the order's clock {instant.isoformat()}")
    if end > instant + FREEZE_MAX or end > midnight:
        raise ValueError(f"the freeze's until {end.isoformat()} is too far: at most {FREEZE_MAX} after the order and never past the nightly cycle "
                         f"({midnight.isoformat()}, midnight in {FREEZE_NIGHTLY_ZONE})")
    current = database.latest_valuation_official_selection()
    if current is None:
        raise ValueError("no official generation in force: nothing to freeze (bootstrap the blend first)")
    source = _selected_source(current)
    if source is None:
        raise ValueError(f"the generation in force ({current.get('generation_id')}) selects an unknown source {current.get('source')!r}: "
                         "it is not frozen — roll back to the blend by explicit order first (Q3)")
    receipt = {"reason": reason, "explicit": True, "freeze": {"until": end.isoformat(), "of_generation": str(current["generation_id"])}}
    generation = _new_generation(
        database, expected_previous=str(current["generation_id"]), cycles=current["cycles"],
        targeted=_normalized_targeted(current.get("targeted") or {}, strict=False), source=source, source_version=str(current["source_version"]),
        session_dates=dict(current.get("session_dates") or {}), now=instant, activated_by=activated_by, receipt=receipt, strict=True,
    )
    assert generation is not None  # strict mode raises instead of returning None
    logger.info("valuation_official: the mesa froze the selection on generation %s until %s (%s) — the automatic writers activate nothing until "
                "then, or until the mesa's next order", generation["generation_id"], end.isoformat(), reason)
    return generation


def record_snapshot(database: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Called by the persistence layer right after a producer publishes a cycle: turns the cycle's rows into
    prediction records FIRST (both official sources, Passo 1), then (universe cycles) activates a new generation when
    the set of selectable cycles changed, or (targeted cycles) admits the symbol into a new generation. Idempotent per
    cycle. No clock is taken here: the activation instant is the wall clock the activation reads immediately before its
    INSERT — after the records are written — never the cycle's ``published_at`` and never an instant from before the
    records (a clock taken here and reused by the activation dated a generation before generations activated meanwhile,
    Y1). ``recorded`` counts the new records of both sources."""
    analysis_type = str(snapshot.get("analysis_type") or "")
    market = market_of_entity(analysis_type, str(snapshot.get("entity_key") or ""))
    if market is None:
        return {"recorded": 0, "generation": None}
    recorded = record_cycle_predictions(database, snapshot)
    if analysis_type == UNIVERSE_ANALYSIS:
        generation = activate_generation_if_changed(database)
    else:
        symbol = str(snapshot.get("entity_key") or "").strip().upper()
        # an unrecordable cycle is never admitted; the admission itself validates against the SELECTED source's records
        has_record = bool(recorded) or any(symbol in database.valuation_predictions_for_cycle(str(snapshot["id"]), source=source) for source in OFFICIAL_SOURCES)
        generation = admit_targeted_cycle(database, symbol=symbol, cycle_id=str(snapshot["id"])) if has_record else None
    return {"recorded": recorded, "generation": generation}


def selectable_cycles(database: Any, *, source: str = SOURCE_OFFICIAL) -> dict[str, dict[str, Any]]:
    """The latest COMPLETE, VALID and RECORDED universe cycle per market FOR ``source`` (the candidates for the next
    generation of that source — the automatic pass passes the selected one, Passo 1).
    A latest cycle with NO record of that source is recorded here first (idempotent, records before selection): it was
    published while the calendar could not answer (nothing was recordable then, X4) or before Passo 0 — the moment
    the calendar answers, the next activation pass recovers it with its real session instead of leaving the market on
    a stale generation. The re-record is attempted ONLY when at least one row of the cycle is usable for ``source``
    (Q4): a cycle produced before Passo 1 (no internal buy-in) has no row the internal source could record, so under an
    internal head it is skipped — ``invalid`` for that source, carried, never patched — instead of N no-op inserts on
    every automatic pass. A cycle with SOME records missing is left alone: another process may still be writing them
    (D1) and it is simply not selectable yet."""
    cycles: dict[str, dict[str, Any]] = {}
    for market in MARKETS:
        raw = database.latest_analysis_snapshot(UNIVERSE_ANALYSIS, f"{market}_UNIVERSE")
        if not raw:
            continue
        snapshot = _normalized_snapshot(raw, analysis_type=UNIVERSE_ANALYSIS, entity_key=f"{market}_UNIVERSE")
        recorded = database.valuation_predictions_for_cycle(str(snapshot["id"]), source=source)
        recordable = any(_usable(row, source) for row in cycle_rows(snapshot))  # Q4: nothing to record for this source → no insert attempted
        if not recorded and recordable and record_cycle_predictions(database, snapshot) > 0:
            logger.info("valuation_official: %s cycle %s recorded at selection time (published while unrecordable)", market, snapshot["id"])
            recorded = database.valuation_predictions_for_cycle(str(snapshot["id"]), source=source)
        validation = cycle_validation(snapshot, recorded=recorded, source=source)
        validation["source_version"] = _source_version(snapshot)
        cycles[market] = validation
    return cycles


def _normalized_targeted(targeted: Mapping[str, str], *, strict: bool = True) -> dict[str, str]:
    """Targeted admissions keyed by the CLEAN symbol (``strip().upper()``, as ``official_row`` looks them up): a key
    written as ``wege3`` would never be served (X2). Two keys that collide after normalization with different cycles
    are an ambiguous order: ``ValueError`` when ``strict`` (an explicit selection); on the automatic path (carry-over of
    a generation already in force) the FIRST occurrence is kept and the collision is logged — the nightly writer never
    dies on a map it did not write (Y4)."""
    clean: dict[str, str] = {}
    for symbol, cycle_id in targeted.items():
        key = str(symbol).strip().upper()
        if key in clean and clean[key] != str(cycle_id):
            message = f"targeted symbols collide after normalization: {symbol!r} → {key} names {clean[key]} and {cycle_id}"
            if strict:
                raise ValueError(message)
            logger.warning("valuation_official: %s — the first occurrence (%s) is carried", message, clean[key])
            continue
        clean[key] = str(cycle_id)
    return clean


def _new_generation(database: Any, *, expected_previous: str | None, cycles: Mapping[str, str], targeted: Mapping[str, str], source: str,
                    source_version: str, session_dates: Mapping[str, str], activated_by: str, receipt: Mapping[str, Any],
                    now: datetime | None = None, strict: bool = False) -> dict[str, Any] | None:
    """One INSERT chained on ``expected_previous`` — the generation the CALLER based its decision on (``None`` for the
    bootstrap). If the chain moved meanwhile (the head read here is not that generation: another writer published
    first, F393-9) or the storage refuses the chain (the UNIQUE predecessor / the unique root, B2), the write is
    refused: ``ValueError`` on the explicit path (``strict``), ``None`` on the automatic one — the caller re-reads the
    NEW head and recomposes its decision on it, so the other writer's generation is carried, never dropped.
    The activation clock (Y1, Z1): the explicit path carries the mesa's clock (``now``), and a clock earlier than the
    current activation is a stale order, refused (D3, ``ValueError``, ``strict``). The automatic path passes NO clock:
    the wall clock is read HERE, immediately before the INSERT — after the records were written and after the head was
    re-read above — so the generation is dated after any decision taken on that predecessor; it is never clamped to the
    head's instant (a clamp backdated it under a decision that read the predecessor, and ``generation_at`` handed that
    decision a generation not in force then). A generation is NEVER dated before the generation it chains on: on the
    non-strict path a clock that is not after the head's ``activated_at`` (this host's wall clock behind the host that
    wrote the head) is ADVANCED to the head's instant + 1 microsecond, with a WARNING — it only advances, never recedes
    (a generation written behind the head was not the head for any reader, and every later writer conflicted on the
    stale head: the chain was locked, Z1). Nothing is ever half-written.
    The marker of an explicit order (``receipt.explicit``) is written by ``select_generation`` alone: the non-strict
    path strips it from any receipt it is handed, so no automatic generation is ever read as an order (W3).
    A conflict that finds the head UNMOVED is a legacy row chained behind its predecessor (W4, see ``_repaired``).
    ``source`` must be one of ``OFFICIAL_SOURCES`` (Q3): a generation selecting an unknown source is never written —
    ``ValueError`` on both paths, before anything is read (the storage layer refuses it too)."""
    from .database import SelectionConflict  # the storage layer raises it on the UNIQUE previous_generation_id / root
    if source not in OFFICIAL_SOURCES:
        raise ValueError(f"unknown official source {source!r}; expected one of {OFFICIAL_SOURCES} — a generation selecting it is never written (Q3)")
    current = database.latest_valuation_official_selection()
    head = current.get("generation_id") if current else None
    if head != expected_previous:
        message = f"the current generation is {head}, not the expected predecessor {expected_previous} — decision must be recomposed"
        if strict:
            raise ValueError(f"selection conflict: {message}")
        logger.warning("valuation_official: %s", message)
        return None
    activated_at = _utc(now) if now is not None else datetime.now(timezone.utc)  # the automatic path: the clock of THIS attempt, at the INSERT
    if current:
        head_at = _utc(current["activated_at"])
        if strict and activated_at < head_at:
            raise ValueError(f"activation clock {activated_at.isoformat()} is earlier than the current generation ({current['activated_at']})")
        if not strict and activated_at <= head_at:
            advanced = head_at + timedelta(microseconds=1)
            logger.warning("valuation_official: activation clock %s is not after the current generation (%s) — advanced to %s: a generation is "
                           "never dated before the generation it chains on (wall clock behind the head, Z1)",
                           activated_at.isoformat(), current["activated_at"], advanced.isoformat())
            activated_at = advanced
    stamped_receipt = dict(receipt)
    if not strict:
        stamped_receipt.pop("explicit", None)  # W3: only select_generation writes the marker of an order
    generation = {
        "schema": SELECTION_SCHEMA,
        "generation_id": str(uuid4()),
        "source": source,
        "source_version": source_version,
        "cycles": {market: str(cycles[market]) for market in MARKETS},
        "targeted": dict(sorted(_normalized_targeted(targeted, strict=strict).items())),
        "session_dates": dict(session_dates),
        "validated_complete": True,
        "activated_at": activated_at.isoformat(),
        "activated_by": activated_by,
        "previous_generation_id": head,
        "receipt": stamped_receipt,
    }
    try:
        database.insert_valuation_official_selection(generation)
    except SelectionConflict as error:
        generation = _repaired(database, generation, expected_previous=head, error=error, strict=strict)
        if generation is None:
            return None
    database.drop_official_cycle_cache()
    return generation


def _chain_tip(database: Any, generation_id: str | None) -> dict[str, Any] | None:
    """The last generation reachable from ``generation_id`` through ``previous_generation_id`` successors — ``None``
    when it has no successor (it IS the tip) or the walk exceeds ``CHAIN_WALK_LIMIT`` (W4)."""
    tip: dict[str, Any] | None = None
    cursor = generation_id
    for _ in range(CHAIN_WALK_LIMIT):
        successor = database.valuation_official_selection_successor(str(cursor)) if cursor is not None else None
        if successor is None:
            return tip
        tip = successor
        cursor = str(successor["generation_id"])
    logger.warning("valuation_official: the chain from %s has more than %s successors — not followed", generation_id, CHAIN_WALK_LIMIT)
    return None


def _repaired(database: Any, generation: dict[str, Any], *, expected_previous: str | None, error: Exception, strict: bool) -> dict[str, Any] | None:
    """The write refused by the storage (UNIQUE successor / unique root), re-examined (W4). If the head MOVED, it is a
    legitimate race: ``ValueError`` on the explicit path, ``None`` on the automatic one (the caller recomposes). If the
    head is UNMOVED, its successor is a row dated BEHIND it — written before Z1 by a host whose clock ran behind — that
    no reader ever saw as the head; every writer chained on the head and conflicted on it: the chain was locked. The
    generation is chained on the chain TIP instead, dated after it — and, on the automatic path, after the head too
    (advanced by 1 µs past the later of the two when needed; the explicit clock is never advanced past the head, D3
    already holds it at or after the head) — with the repair in its receipt (``repaired_chain``) and a WARNING. A second
    refusal is given up (explicit: ``ValueError``)."""
    reread = database.latest_valuation_official_selection()
    moved = (reread.get("generation_id") if reread else None) != expected_previous
    tip = None if moved else _chain_tip(database, expected_previous)
    if moved or tip is None or reread is None:
        if strict:
            raise ValueError(f"selection conflict: {error}") from error
        logger.warning("valuation_official: chain conflict on %s — generation not activated (%s)", expected_previous,
                       "the head moved" if moved else "no successor is visible")
        return None
    activated_at = _utc(generation["activated_at"])
    floor = _utc(tip["activated_at"]) if strict else max(_utc(tip["activated_at"]), _utc(reread["activated_at"]))
    if activated_at <= floor:
        activated_at = floor + timedelta(microseconds=1)
    repaired = {**generation, "activated_at": activated_at.isoformat(), "previous_generation_id": str(tip["generation_id"]),
                "receipt": {**generation["receipt"], "repaired_chain": {"head": expected_previous, "chained_on": str(tip["generation_id"])}}}
    logger.warning("valuation_official: the head %s already has a successor dated behind it (chain tip %s, activated %s — a row written behind its "
                   "predecessor): chained on the tip instead, at %s (W4)", expected_previous, tip["generation_id"], tip["activated_at"], repaired["activated_at"])
    from .database import SelectionConflict
    try:
        database.insert_valuation_official_selection(repaired)
    except SelectionConflict as second:
        if strict:
            raise ValueError(f"selection conflict: {second}") from second
        logger.warning("valuation_official: chain conflict on the chain tip %s too — generation not activated", tip["generation_id"])
        return None
    return repaired


def _admissible_targeted(database: Any, *, symbol: str, cycle_id: str, known_refusal: str | None = None,
                         source: str = SOURCE_OFFICIAL) -> dict[str, Any] | None:
    """The validation of a targeted cycle for ``symbol`` when it may be admitted — the SAME validator as a universe
    cycle (F393-4), for the SELECTED source (Passo 1), and the symbol's own record of that source present — else
    ``None``, logged: a WARNING the first time this cycle is refused (the admission, or a recovery pass meeting a refused
    cycle id it did not know), INFO when the refusal is already known — by this process (``_refusals_logged``) or by the
    head's receipt (``known_refusal``, Z3)."""
    snapshot = database.official_cycle_snapshot(str(cycle_id))
    if not snapshot or snapshot.get("analysis_type") != TARGETED_ANALYSIS:
        return None
    recorded = database.valuation_predictions_for_cycle(str(cycle_id), source=source)
    validation = cycle_validation(snapshot, recorded=recorded, source=source)
    if not validation["valid"] or symbol not in recorded:
        level = logging.INFO if str(cycle_id) in (known_refusal, _refusals_logged.get(symbol)) else logging.WARNING
        logger.log(level, "valuation_official: targeted cycle %s for %s refused: %s", cycle_id, symbol,
                   {k: validation[k] for k in ("invalid_count", "unrecorded_count", "rows", "calendar_unavailable")})
        _refusals_logged[symbol] = str(cycle_id)
        return None
    return validation


def _predicted_at_or_before(database: Any, cycle_id: str, order: Mapping[str, Any]) -> bool:
    """Whether the cycle was PREDICTED at or before the mesa's explicit ``order`` (its ``activated_at``) — the order then
    decided over it (B3; the same clock as W1 for universe cycles and Z2 for the recovery). The clock is the prediction
    instant, ``cycle_clocks(snapshot)[0]``: a live cycle's publication, a re-run's ORIGINAL instant — a re-run published
    after the order reproduces a prediction the order already decided over, so it is held (S1). A cycle that cannot be
    read, or whose clocks cannot (an unrecordable re-run), is held too: nothing unknown is admitted over an order."""
    snapshot = database.official_cycle_snapshot(str(cycle_id))
    clocks = cycle_clocks(snapshot) if snapshot else None
    if clocks is None:
        return True
    return clocks[0] <= _utc(order["activated_at"])


def _recovered_targeted(database: Any, carried: Mapping[str, str], universe_cycle: str | None, *,
                        head: Mapping[str, Any] | None, order: Mapping[str, Any] | None,
                        source: str = SOURCE_OFFICIAL) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """The targeted admissions of the next generation (Y3): the carried ones, then — for every symbol with a REGISTERED
    targeted cycle newer than the one carried (or none carried) — that cycle, if it passes the validator and the
    universe cycle does not serve the symbol (A1). A targeted cycle that was recorded but never admitted (its admission
    lost every recomposition, or its calendar was out when it was validated) is thus admitted by the next activation
    pass instead of waiting for a re-run.
    The mesa's last EXPLICIT order (``order``: the latest generation carrying the marker ``receipt.explicit``, which
    ``select_generation`` alone writes — a purge, a rollback, a switch; read once by the caller, W3) is authoritative
    over every targeted cycle PREDICTED at or before its ``activated_at``: those are never recovered — the order
    decided over them (a purge stays purged, a rollback to an older cycle stays on it) — whether the order is the head
    or an automatic generation has chained on it since; only cycles predicted AFTER the order are candidates (Z2).
    A candidate the validator refuses is recorded in the receipt (``targeted_refused``) and logged at INFO when the
    head's receipt (or this process) already names that cycle for the symbol, at WARNING when the refused cycle id
    changes (Z3). The authority clock is the record's ``prediction_instant`` (a re-run keeps the ORIGINAL's instant, so
    a re-run published after the order never re-opens what it decided, S1), as on the admission and the universe path (W1).
    Every record read here is of the SELECTED ``source`` (Passo 1). Returns ``(targeted, recovered, refused)``."""
    targeted = dict(carried)
    recovered: dict[str, str] = {}
    refused: dict[str, str] = {}
    served = set(database.valuation_predictions_for_cycle(str(universe_cycle), source=source)) if universe_cycle else set()
    authority = _utc(order["activated_at"]) if order else None
    known_refusals = ((head or {}).get("receipt") or {}).get("targeted_refused") or {}
    for symbol, record in sorted(database.latest_targeted_predictions("B3", source=source).items()):
        clean = str(symbol).strip().upper()
        candidate = str(record["cycle_id"])
        if clean in served or targeted.get(clean) == candidate:
            continue
        if authority is not None and _utc(record["prediction_instant"]) <= authority:
            continue  # predicted at or before the mesa's last explicit order: that order decided over it (Z2; a re-run keeps the original's instant, S1)
        admitted = database.valuation_prediction_record(str(targeted[clean]), clean, source=source) if clean in targeted else None
        if admitted is not None and _utc(record["prediction_instant"]) <= _utc(admitted["prediction_instant"]):
            continue  # the generation already holds a cycle at least as recent
        if _admissible_targeted(database, symbol=clean, cycle_id=candidate, known_refusal=known_refusals.get(clean), source=source) is None:
            refused[clean] = candidate
            continue
        targeted[clean] = candidate
        recovered[clean] = candidate
    return targeted, recovered, refused


def activate_generation_if_changed(database: Any) -> dict[str, Any] | None:
    """Insert a new generation when the set of official cycles — or of targeted admissions — changed. A market with a
    new COMPLETE, VALID, RECORDED cycle contributes it; a market without one keeps the cycle of the current generation
    (carried over, recorded in the receipt, B1) — so one market's bad night never strips the other two of their
    official stamp. Bootstrap (no generation yet) still requires every market to have a valid cycle: an incomplete
    generation is never selectable. One INSERT — readers see the previous generation or the new one, never a mixture.
    The mesa's last EXPLICIT order (the latest generation with ``receipt.explicit``, read ONCE per attempt, W3) stands
    over every cycle PREDICTED at or before its ``activated_at`` — universe cycles too (W1): a market whose candidate
    was predicted at or before the order, while a generation is in force, is NOT new — the cycle in force is carried
    and the market is named in ``receipt.held_by_explicit_order`` — so a rollback of a universe cycle survives the next
    automatic pass and the bootstrap; only a cycle predicted AFTER the order is activated. The clock is the candidate's
    prediction instant (``validation.prediction_instant``): a re-run of the rolled-back cycle keeps the original's
    instant and is held too (S1).
    Targeted admissions of the current generation are carried over (collisions after normalization: first occurrence,
    Y4) and a registered targeted cycle newer than the carried one is admitted here (Y3, ``receipt.targeted_recovered``)
    — only if it was predicted AFTER the same order (Z2); a registered cycle the validator refuses is named in
    ``receipt.targeted_refused`` (Z3). Always written as ``ACTIVATED_BY``: the automatic path has no ``activated_by`` of
    its own, so nothing it writes can be read as an order (W3).
    The generation read here is the expected predecessor: if another writer moved the chain meanwhile the write is
    refused and the decision is recomposed on the new head (F393-9), up to ``RECOMPOSITION_ATTEMPTS`` times (Y2) —
    each attempt is a new activation, dated by the wall clock read at its own INSERT (Y1), never before the head it
    chains on (Z1); past the limit the pass gives up with a WARNING and the next pass (the next cycle of any market, or
    the bootstrap) composes the decision again.
    Passo 1: the pass composes for the CURRENTLY SELECTED source only (``_selected_source`` of the head read on this
    attempt; the blend when there is no head): candidates, targeted recovery and the new generation all carry that
    source — a switch ordered by the mesa is never undone by the next pass, and a market whose new cycle has no records
    of the selected source (a cycle produced before Passo 1, for an internal generation) is carried over. A head whose
    source is unknown activates NOTHING (Q3, ERROR logged by ``_selected_source``): the pass never composes a blend
    generation over it — the mesa rolls back by explicit order.
    A head FROZEN by the mesa (``selection_freeze``, F1) activates nothing either (INFO): the cycles stay recorded and the
    first pass after the freeze — or the mesa's order — decides over them; the freeze is read on every attempt."""
    for attempt in range(RECOMPOSITION_ATTEMPTS):
        current = database.latest_valuation_official_selection()
        selected = _selected_source(current)
        if selected is None:
            return None  # Q3: an unknown head source is not a source to compose for; the ERROR is logged, the health says so
        freeze = selection_freeze(current, now=datetime.now(timezone.utc))
        if freeze is not None:
            logger.info("valuation_official: the selection is frozen by the mesa's order %s until %s — nothing activated by this pass; the cycles "
                        "stay recorded (F1)", freeze["generation_id"], freeze["until"])
            return None
        candidates = selectable_cycles(database, source=selected)
        order = database.latest_explicit_valuation_official_selection() if current else None  # the mesa's last order, once (W1/W3)
        authority = _utc(order["activated_at"]) if order else None
        cycles: dict[str, str] = {}
        versions: dict[str, str] = {}
        carried: list[str] = []
        held: list[str] = []
        session_dates: dict[str, str] = {}
        for market in MARKETS:
            item = candidates.get(market)
            in_force = str((current.get("cycles") or {}).get(market) or "") if current else ""
            if item and item["valid"] and in_force and str(item["cycle_id"]) != in_force and authority is not None \
                    and item.get("prediction_instant") and _utc(item["prediction_instant"]) <= authority:
                held.append(market)  # W1: predicted at or before the mesa's order — the order decided over it; not new (a re-run keeps the original's instant, S1)
                item = None
            if item and item["valid"]:
                cycles[market] = str(item["cycle_id"])
                versions[market] = str(item["source_version"])
                session_dates[market] = str(item["session_date"])  # validated: the calendar answered for this cycle
            elif in_force:
                cycles[market] = in_force
                carried_snapshot = database.official_cycle_snapshot(cycles[market])
                versions[market] = _source_version(carried_snapshot) if carried_snapshot else "unknown"
                session_dates[market] = str(((current or {}).get("session_dates") or {}).get(market) or "")
                carried.append(market)
            else:
                logger.warning("valuation_official: %s has no valid recorded cycle and no generation to carry — nothing activated", market)
                return None
        carried_targeted = _normalized_targeted((current or {}).get("targeted") or {}, strict=False)
        targeted, recovered, refused = _recovered_targeted(database, carried_targeted, cycles.get("B3"), head=current, order=order, source=selected)
        if current and current.get("cycles") == cycles and current.get("targeted") == targeted:
            return None  # nothing changed for the selected source: only the cycles and the targeted admissions decide (Passo 1)
        generation = _new_generation(
            database, expected_previous=current.get("generation_id") if current else None, cycles=cycles, targeted=targeted, source=selected,
            source_version="+".join(sorted(set(versions.values()))), session_dates=session_dates, activated_by=ACTIVATED_BY,
            receipt={"validation": {market: {k: v for k, v in candidates[market].items() if k != "invalid_rows"} for market in MARKETS if market in candidates},
                     "changed_markets": [market for market in MARKETS if not current or (current.get("cycles") or {}).get(market) != cycles[market]],
                     "carried_markets": carried, "held_by_explicit_order": held, "explicit_order": str(order["generation_id"]) if order else None,
                     "versions": versions, "source": selected, "targeted_recovered": recovered, "targeted_refused": refused, "attempt": attempt + 1},
        )
        if generation is not None:
            return generation
    logger.warning("valuation_official: the head moved on every one of %s recomposition attempts — nothing activated by this pass; the next pass recomposes",
                   RECOMPOSITION_ATTEMPTS)
    return None


def admit_targeted_cycle(database: Any, *, symbol: str, cycle_id: str) -> dict[str, Any] | None:
    """A targeted (on-demand) valuation published by the official producer for a symbol outside the universe becomes
    official only THROUGH the selection: a new generation with ``targeted[symbol] = cycle_id`` (new id — a new served
    number is a new generation, F393-4). The cycle must pass the SAME validation as a universe cycle (a row with
    ``price = 0`` or no ``internal_tp`` is never admitted); a symbol the universe cycle already serves is not admitted
    (the universe answers first, so the admission would never be read, A1). Without a current generation there is
    nothing to admit into (and nothing is validated: the bootstrap's recovery pass validates it, Y3). The generation
    read is the expected predecessor; a moved chain is recomposed up to ``RECOMPOSITION_ATTEMPTS`` times (F393-9, Y2),
    each attempt dated by the wall clock at its own INSERT (Y1, never before the head, Z1) and numbered in the receipt
    (``attempt``, Z4); the current admissions are carried normalized (first occurrence on a collision) and this
    admission wins its own key (Y4), and the head's known refusals (``receipt.targeted_refused``) are carried too, minus
    this symbol, so a later pass does not warn again for a refusal the chain already names (Z3). The validator receives
    the head's known refusal for this symbol: a re-run of the same refused cycle is INFO, not WARNING (W5). Always
    written as ``ACTIVATED_BY`` (W3). An admission that gives up is recovered by the next activation pass (Y3).
    The mesa's last EXPLICIT order governs this direct path too (B3, rev 6): a cycle PREDICTED at or before the order's
    ``activated_at`` is held — the order decided over it (a purge stays purged, a rollback stays on its cycle) — so the
    persistence hook replaying the same old cycle (``record_snapshot``, recorded = 0) creates no generation and restores
    nothing; the order is re-read on EVERY attempt (an order landing between two attempts is honoured by the next one);
    only a cycle predicted after the order is admitted — a re-run keeps the original's instant, so a re-run of a purged
    cycle is held too (S1). Nothing is validated or logged for a held cycle beyond INFO.
    The recency rule of the recovery (Y3) holds here too (S2): when the generation already holds a targeted cycle for the
    symbol, a candidate whose prediction is not NEWER than the held record's is not admitted (INFO) — the replay of an
    old cycle (``record_snapshot`` on a snapshot recorded long ago, with no order after it) no longer downgrades the
    served number and flip-flops the chain with the next pass. The held cycle is read from the head's map NORMALIZED
    (the same map the carry-over writes, U1): a legacy key not written clean (``wege3``, which Y4 tolerates) is still
    the held cycle for this rule and for the early return — it no longer lets the replay through as if nothing were held.
    Nothing is admitted over a head FROZEN by the mesa (``selection_freeze``, F1; INFO): the cycle stays recorded and the
    first activation pass after the freeze recovers it (it was predicted after the freeze order, Z2)."""
    clean = symbol.strip().upper()
    validation: dict[str, Any] | None = None
    for attempt in range(RECOMPOSITION_ATTEMPTS):
        current = database.latest_valuation_official_selection()
        if not current:
            return None
        selected = _selected_source(current)  # every record read below is of the head's source (Passo 1)
        if selected is None:
            return None  # Q3: nothing is admitted under a head whose source is unknown (ERROR logged); the mesa rolls back
        freeze = selection_freeze(current, now=datetime.now(timezone.utc))
        if freeze is not None:
            logger.info("valuation_official: targeted cycle %s for %s not admitted — the selection is frozen by the mesa's order %s until %s (F1)",
                        cycle_id, clean, freeze["generation_id"], freeze["until"])
            return None
        carried = _normalized_targeted(current.get("targeted") or {}, strict=False)  # the head's admissions as they are served (Y4, U1)
        held_cycle = carried.get(clean)
        if held_cycle == str(cycle_id):
            return None
        order = database.latest_explicit_valuation_official_selection()  # re-read on every attempt (B3)
        if order is not None and _predicted_at_or_before(database, str(cycle_id), order):
            logger.info("valuation_official: targeted cycle %s for %s was predicted at or before the mesa's last explicit order %s (%s) — held, not "
                        "admitted: the order decided over it (B3)", cycle_id, clean, order["generation_id"], order["activated_at"])
            return None
        held_record = database.valuation_prediction_record(str(held_cycle), clean, source=selected) if held_cycle else None
        candidate = database.valuation_prediction_record(str(cycle_id), clean, source=selected)
        if held_record is not None and candidate is not None and _utc(candidate["prediction_instant"]) <= _utc(held_record["prediction_instant"]):
            logger.info("valuation_official: targeted cycle %s for %s (predicted %s) is not newer than the cycle the generation holds, %s (%s) — not "
                        "admitted (S2)", cycle_id, clean, candidate["prediction_instant"], held_cycle, held_record["prediction_instant"])
            return None
        if validation is None or validation.get("source") != selected:  # validated once per source, against the head's known refusals (W5)
            known = ((current.get("receipt") or {}).get("targeted_refused") or {}).get(clean)
            validation = _admissible_targeted(database, symbol=clean, cycle_id=str(cycle_id), known_refusal=str(known) if known else None, source=selected)
            if validation is None:
                return None
        universe_cycle = (current.get("cycles") or {}).get("B3")
        if universe_cycle and clean in database.valuation_predictions_for_cycle(str(universe_cycle), source=selected):
            return None
        generation = _new_generation(
            database, expected_previous=str(current["generation_id"]), cycles=current["cycles"],
            targeted={**carried, clean: str(cycle_id)}, source=selected,
            source_version=str(current["source_version"]), session_dates=dict(current.get("session_dates") or {}), activated_by=ACTIVATED_BY,
            receipt={"targeted_admission": {"symbol": clean, "cycle_id": str(cycle_id), "validation": {k: v for k, v in validation.items() if k != "invalid_rows"}},
                     "changed_markets": [], "attempt": attempt + 1,
                     "targeted_refused": {k: v for k, v in (((current.get("receipt") or {}).get("targeted_refused") or {}).items()) if k != clean}},
        )
        if generation is not None:
            return generation
    logger.warning("valuation_official: the head moved on every one of %s recomposition attempts — %s/%s not admitted by this call; the next activation pass recovers it",
                   RECOMPOSITION_ATTEMPTS, clean, cycle_id)
    return None


def select_generation(database: Any, *, cycles: Mapping[str, str], now: datetime, activated_by: str, reason: str,
                      targeted: Mapping[str, str] | None = None, source: str = SOURCE_OFFICIAL, source_version: str | None = None,
                      before_after_sha256: str | None = None) -> dict[str, Any]:
    """Explicit selection (rollback or a mesa-ordered switch): a new generation pointing at complete, recorded cycles
    that already exist — each market cycle must be a universe cycle OF THAT MARKET, each targeted cycle a targeted
    cycle OF THAT SYMBOL, and BOTH must pass ``cycle_validation`` (the validator of the automatic path: a targeted row
    with ``price = 0`` or no ``internal_tp`` is refused here too, F393-4 rev 5). Every market must be named (F1). The
    targeted symbols are normalized (``strip().upper()``) before validation and writing, as ``official_row`` looks them
    up (X2). The generation in force when the order is executed is the expected predecessor: if the chain moves during
    validation the order fails (``ValueError``) and the mesa re-reads. The order is authoritative over every cycle
    PREDICTED at or before ``now`` — targeted (Z2, B3) and universe (W1) alike; the clock is the prediction instant, so a
    re-run (which keeps the original's instant) never re-opens what the order decided (S1): the automatic recovery (Y3)
    and the direct admission never re-admit them — a purge (``targeted={}``) stays purged, a rollback to an older cycle
    stays on it, a universe rollback is not undone by the next pass; a cycle predicted after the order is
    activated/recovered/admitted normally.
    ``now`` is the mesa's WALL CLOCK at the order: a clock behind the head is refused (D3) and so is a clock further
    ahead of this host's than ``EXPLICIT_CLOCK_TOLERANCE`` (60 s; W2) — an order dated in the future would stand over
    cycles not yet published. The order is marked ``receipt.explicit = True`` — the ONLY marker the automatic path
    reads as an order (W3). Never used by the nightly path.
    ``source`` (Passo 1): the source the new generation SELECTS, one of ``OFFICIAL_SOURCES``; every named cycle is
    validated against the records OF THAT SOURCE (a cycle produced before Passo 1 has no internal records and is
    refused for ``SOURCE_INTERNAL``). A switch to any source other than ``SOURCE_OFFICIAL`` is REFUSED while the lock
    ``OFFICIAL_TP_REPLACEMENT_AUTHORIZED`` is ``False`` (it flips only by a commit citing the mesa's receipt) and requires
    ``before_after_sha256`` — the ``report_sha256`` of the before/after receipt (``before_after_report``) the order cites,
    which is CHECKED (Q1) and BINDS the proposal (C395-1): after the cycle/targeted validations (an invalid cycle is named
    as such first) the receipt is recomputed here on the head read in this same attempt, over EXACTLY this order's
    ``cycles``/``targeted`` (normalized) and the ``source_version`` it stamps (deterministic — no clock, canonical JSON),
    and a hash that is not that ``report_sha256`` is refused, naming both — so a well-formed but foreign hash, the receipt
    of a generation the chain has moved past, or a receipt approved over ANOTHER composition (a different cycle in a market,
    a targeted admission added or dropped, another version) never lands; a switch needs a generation in force (there is no
    "before" to compare otherwise — refused before anything else is read). Rev 9: the cited hash must ALSO be exactly
    ``OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256`` — the receipt the owner accepted, named by the commit that flips the lock —
    checked last, after the recomputation (so a hash of another generation or composition is named as such first): a lock
    commit whose receipt is absent or not hex-64 (the placeholder) switches nothing, and a receipt computed after the
    accepted one (the head moved: a new night, a targeted admission) needs a new acceptance and a new lock commit.
    ``source_version`` (Q6): the mesa's declaration when given; when omitted, a switch stamps the methodology versions of
    the validated universe cycles (``"+".join(sorted(set))``, exactly as the automatic pass stamps its generations) and a
    rollback to the blend stamps ``"rollback"`` (the Passo 0 behaviour) — a switch is never stamped ``"rollback"``.
    The ROLLBACK to the blend is this same call with ``source=SOURCE_OFFICIAL`` and the previous generation's cycles:
    never locked, no hash required — and the way out of a head whose source is unknown (Q3). When the source changes,
    ``receipt.source_switch`` names ``from`` (the head's source as stored)/``to``/hash. An order over a head the mesa FROZE
    (``freeze_selection``, F1) lands as on any head — the freeze holds the automatic writers, never the mesa — and ends the
    freeze: ``receipt.ended_freeze`` names it."""
    if source not in OFFICIAL_SOURCES:
        raise ValueError(f"unknown official source {source!r}; expected one of {OFFICIAL_SOURCES}")
    if source != SOURCE_OFFICIAL:
        if not OFFICIAL_TP_REPLACEMENT_AUTHORIZED:
            raise ValueError(f"official_tp_replacement_authorized is false: a switch of the official source to {source!r} is refused until the "
                             "mesa's receipt flips the lock (V3.2 rev 7 §7-bis, Passo 1); the rollback to the blend is never locked")
        if not before_after_sha256 or not _SHA256.match(str(before_after_sha256)):
            raise ValueError(f"a switch to {source!r} must cite the before/after receipt: before_after_sha256 (hex-64, the report_sha256 of "
                             "before_after_report) is missing or malformed")
    instant = _utc(now)
    wall = datetime.now(timezone.utc)
    if instant > wall + EXPLICIT_CLOCK_TOLERANCE:
        raise ValueError(f"activation clock {instant.isoformat()} is in the future by more than {int(EXPLICIT_CLOCK_TOLERANCE.total_seconds())} s "
                         f"(wall clock {wall.isoformat()}) — the order carries the mesa's wall clock")
    missing = [market for market in MARKETS if market not in cycles]
    if missing:
        raise ValueError(f"cycles must name every market; missing: {', '.join(missing)}")
    admissions = _normalized_targeted(targeted or {})
    current = database.latest_valuation_official_selection()
    if source != SOURCE_OFFICIAL and current is None:  # Q1: no "before" to compare — refused before anything else is read
        raise ValueError(f"a switch to {source!r} requires a generation in force: the before/after receipt compares the cycles it serves, "
                         "and there is none — bootstrap the blend first")
    session_dates: dict[str, str] = {}
    versions: set[str] = set()
    for market in MARKETS:
        snapshot = database.analysis_snapshot_by_id(str(cycles[market]))
        if not snapshot or snapshot.get("analysis_type") != UNIVERSE_ANALYSIS or market_of_entity(UNIVERSE_ANALYSIS, str(snapshot.get("entity_key") or "")) != market:
            raise ValueError(f"cycle for {market} is not a universe cycle of {market}: {cycles.get(market)}")
        validation = cycle_validation(snapshot, recorded=database.valuation_predictions_for_cycle(str(cycles[market]), source=source), source=source)
        if not validation["valid"]:
            raise ValueError(f"cycle for {market} is not complete/valid/recorded for source {source}: {cycles[market]}")
        session_dates[market] = str(validation["session_date"])
        versions.add(_source_version(snapshot))
    if source_version is None:  # Q6: a switch is stamped with the validated cycles' methodology versions, as the automatic pass; a rollback keeps "rollback"
        source_version = "rollback" if source == SOURCE_OFFICIAL else "+".join(sorted(versions))
    for symbol, cycle_id in admissions.items():
        snapshot = database.analysis_snapshot_by_id(cycle_id)
        if not snapshot or snapshot.get("analysis_type") != TARGETED_ANALYSIS or str(snapshot.get("entity_key") or "").strip().upper() != symbol:
            raise ValueError(f"targeted cycle for {symbol} is not a targeted cycle of {symbol}: {cycle_id}")
        recorded = database.valuation_predictions_for_cycle(cycle_id, source=source)
        validation = cycle_validation(snapshot, recorded=recorded, source=source)
        if not validation["valid"] or symbol not in recorded:
            raise ValueError(f"targeted cycle for {symbol} is not complete/valid/recorded for source {source}: {cycle_id} "
                             f"({ {k: validation[k] for k in ('invalid_count', 'unrecorded_count', 'rows', 'calendar_unavailable')} })")
    if source != SOURCE_OFFICIAL:  # Q1 (after the validations, so an invalid cycle is named as such first): the cited receipt must be THE receipt of the generation in force, recomputed here over THIS proposal (C395-1)
        expected = before_after_report(database, generation=current, cycles=cycles, targeted=admissions, source_version=source_version)["report_sha256"]  # C395-1: bound to THIS composition
        if str(before_after_sha256) != expected:
            raise ValueError(f"a switch to {source!r} must cite the before/after receipt of the generation in force ({current['generation_id']}) "
                             f"computed over EXACTLY the cycles and targeted admissions this order proposes (and the source_version it stamps): before_after_sha256 "
                             f"{str(before_after_sha256)[:12]}… does not match its report_sha256 {expected[:12]}… — the receipt was computed on "
                             "another generation (the chain moved since the mesa read it), over another composition (a different cycle in a "
                             "market, a targeted admission added or dropped, another declared source_version), or is not this receipt; re-run "
                             "before_after_report on the head with the order's cycles/targeted/source_version and cite it (C395-1)")
        accepted = OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256  # rev 9: the receipt the owner accepted, named by the lock commit
        if not isinstance(accepted, str) or not _SHA256.match(accepted):
            raise ValueError(f"a switch to {source!r} is refused: the lock commit names no accepted before/after receipt "
                             f"(OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256 = {accepted!r}) — the commit that flips the lock writes the report_sha256 "
                             "the owner accepted")
        if str(before_after_sha256) != accepted:
            raise ValueError(f"a switch to {source!r} must cite the before/after receipt the owner accepted ({accepted[:12]}…, named by the lock "
                             f"commit): {str(before_after_sha256)[:12]}… is the receipt of the generation in force over this proposal but not the "
                             "accepted one — the head moved or the proposal changed since the acceptance; a new receipt needs a new acceptance "
                             "and a new lock commit")
    receipt: dict[str, Any] = {"reason": reason, "explicit": True}  # the marker of an order — written here and by freeze_selection, nowhere else (W3)
    frozen = selection_freeze(current, now=instant)
    if frozen is not None:  # F1: this order ends the mesa's freeze (the automatic writers chain on it again) — named for the audit
        receipt["ended_freeze"] = {"generation_id": frozen["generation_id"], "until": frozen["until"]}
    if current is not None and current.get("source") != source:  # a switch or a rollback of the SOURCE: named in the receipt (Passo 1) — as STORED, so
        receipt["source_switch"] = {"from": current.get("source"), "to": source, "before_after_sha256": before_after_sha256}  # an unknown source is named (Q3)
    generation = _new_generation(
        database, expected_previous=current.get("generation_id") if current else None, cycles=cycles, targeted=admissions,
        source=source, source_version=source_version, session_dates=session_dates, now=instant, activated_by=activated_by,
        receipt=receipt, strict=True,
    )
    assert generation is not None  # strict mode raises instead of returning None
    return generation


def current_generation(database: Any) -> dict[str, Any] | None:
    return database.latest_valuation_official_selection()


def generation_at(database: Any, instant: datetime) -> dict[str, Any] | None:
    """The generation that was in force at ``instant`` (the latest activated at or before it) — what a study or a
    replay of a past decision must read, never the current one (F393-7)."""
    return database.valuation_official_selection_at(_utc(instant))


def _resolve(database: Any, generation: Any) -> Mapping[str, Any] | None:
    """``UNRESOLVED`` → the current generation; ``None`` → the caller resolved and found none: serve NOTHING (F393-3)."""
    if generation is UNRESOLVED:
        return current_generation(database)
    return generation


def _markets_for(market: str | None) -> tuple[str, ...]:
    if market is None:
        return MARKETS
    clean = market.strip().upper()
    if clean == "US":
        return ("NASDAQ", "NYSE")
    return (clean,) if clean in MARKETS else ()


def _served(row: Mapping[str, Any], record: Mapping[str, Any], *, generation: Mapping[str, Any], cycle_id: str, scope: str,
            market: str) -> dict[str, Any] | None:
    """What a consumer receives: a DEEP COPY of the cycle row for display fields, with the SERVED numbers taken from
    the immutable record (``our_tp``, ``buy_in``) and the full stamp (F393-3, F393-5, F393-6). Mutating the result
    never reaches a cache or a record.
    Passo 1: the record's ``consensus_weight_percent`` (0 for an internal record) and the producer's two arithmetic
    identities over the served numbers — ``upside_percent = (tp / price − 1) × 100`` and ``price_vs_buy_in_percent =
    (price / buy_in − 1) × 100``, the very expressions the US and B3 producers evaluate — are overlaid too, so a consumer
    that displays or ranks by them sees the served TP; for a blend record they are bit for bit the row's own values.
    The entry models behind the served buy-in — ``buy_in_models`` — are the RECORD's ``decomposition.buy_in_models`` when
    it carries any (Q2): the internal record's are the producer's ``internal_buy_in_models`` (else the producer's, as
    ``prediction_from_row`` stored them), so the models shown beside the internal buy-in are its own; for a blend record
    they are the row's own values, bit for bit (a record without models leaves the row's untouched).
    Rev 9 (the residue of Passo 1, closed): for an INTERNAL record the TP-dependent display fields — ``score``, ``status``,
    ``expected_total_return_percent`` and, when the producer emits them, ``tp_validation_status``/``tp_validation_reasons``
    — are the producer's INTERNAL VIEW of the row (``internal_view``), never the blend's; an internal record whose row has
    no internal view is NOT served (``None``, WARNING once per record per process, INFO after) — the validator never selects
    such a cycle for the internal source, so this is the guard of a hand-made generation. A blend record is served as before."""
    view: dict[str, Any] | None = None
    if record.get("source") == SOURCE_INTERNAL:
        view = internal_view(row)
        if view is None:
            key = f"{cycle_id}/{record.get('symbol')}"
            level = logging.INFO if key in _viewless_logged else logging.WARNING
            _viewless_logged.add(key)
            logger.log(level, "valuation_official: internal record %s/%s of cycle %s has no internal view on its row (score/status/expected return on the "
                       "internal TP) — not served: the internal TP is never shown under the blend's status (rev 9)", market, record.get("symbol"), cycle_id)
            return None
    stamped = copy.deepcopy(dict(row))
    tp, buy_in, price = float(record["tp"]), float(record["buy_in"]), _positive(record.get("price"))
    if price is not None:
        stamped["upside_percent"] = (tp / price - 1) * 100
        stamped["price_vs_buy_in_percent"] = (price / buy_in - 1) * 100
    if record.get("consensus_weight_percent") is not None:
        stamped["consensus_weight_percent"] = float(record["consensus_weight_percent"])
    decomposition = record.get("decomposition")
    models = decomposition.get("buy_in_models") if isinstance(decomposition, Mapping) else None
    if isinstance(models, Mapping) and models:
        stamped["buy_in_models"] = copy.deepcopy(dict(models))  # Q2: the models of the served buy-in, never the blend's under an internal record
    if view is not None:
        stamped.update(view)  # rev 9: the status/score/expected return of the served (internal) TP, never the blend's
    stamped.update({
        "our_tp": tp,
        "buy_in": buy_in,
        "tp_source": record["source"],
        "tp_source_version": record["source_version"],
        "generation_id": generation["generation_id"],
        "official_cycle_id": cycle_id,
        "official_scope": scope,
        "official_market": market,
        "official_session_date": record["session_date"],
        "prediction_instant": record["prediction_instant"],
        "official_published_at": record.get("published_at"),  # the record's own publication clock (B2); a re-run's is its re-run date
        "official_row_sha256": record["row_sha256"],
    })
    return stamped


def item_stamp(row: Mapping[str, Any] | None) -> dict[str, Any]:
    """The per-item stamp for API models (F393-6): every key explicit, ``None`` when the row is not official."""
    source = row or {}
    return {field: source.get(key) for key, field in ITEM_STAMP_KEYS.items()}


def official_rows(database: Any, market: str, *, generation: Any = UNRESOLVED) -> dict[str, dict[str, Any]]:
    """Every official row of one market for ONE generation (default: the current one — resolve it once per request or
    batch and pass it, so that every market and symbol of that request comes from the same generation; pass ``None``
    when you resolved and found none: nothing is served). Enumeration comes from the RECORDS of the generation's
    cycle (the identity), the display fields from the cycle row of the same symbol; a record whose row vanished from a
    mutated snapshot is not served and is logged. Empty when there is no generation: an operational consumer then
    has NO TP — it never falls back to computing or to a raw snapshot."""
    resolved = _resolve(database, generation)
    if not resolved:
        return {}
    source = _selected_source(resolved)  # the records of the generation's own source (Passo 1)
    if source is None:
        return {}  # Q3: an unknown source serves nothing (ERROR logged) — never a guess
    result: dict[str, dict[str, Any]] = {}
    for selected in _markets_for(market):
        cycle_id = (resolved.get("cycles") or {}).get(selected)
        if not cycle_id:
            continue
        snapshot = database.official_cycle_snapshot(str(cycle_id))
        if not snapshot:
            continue
        records = database.valuation_predictions_for_cycle(str(cycle_id), source=source)
        rows_by_symbol = {str(row.get("symbol") or "").strip().upper(): row for row in cycle_rows(snapshot)}
        for symbol, record in records.items():
            row = rows_by_symbol.get(symbol)
            if row is None:
                logger.warning("valuation_official: record %s/%s of cycle %s has no display row — not served", selected, symbol, cycle_id)
                continue
            served = _served(row, record, generation=resolved, cycle_id=str(cycle_id), scope="universe", market=selected)
            if served is not None:  # rev 9: an internal record without its row's internal view is not served (logged by _served)
                result.setdefault(symbol, served)
    return result


def official_row(database: Any, market: str, symbol: str, *, generation: Any = UNRESOLVED) -> dict[str, Any] | None:
    """The official row for one symbol, resolved through ONE generation: from the market's universe cycle, else from
    the targeted cycles the generation admitted for that symbol. Nothing outside the generation is ever served
    (F393-4). ``None`` means "no official TP" — consumers say so instead of computing; an internal record whose row has no
    internal view is ``None`` too (rev 9, ``_served``)."""
    clean = symbol.strip().upper().removesuffix(".SA").removesuffix(".US")
    resolved = _resolve(database, generation)
    if not resolved:
        return None
    source = _selected_source(resolved)  # the record of the generation's own source (Passo 1)
    if source is None:
        return None  # Q3: an unknown source serves nothing (ERROR logged) — never a guess
    for selected in _markets_for(market):
        cycle_id = (resolved.get("cycles") or {}).get(selected)
        record = database.valuation_prediction_record(str(cycle_id), clean, source=source) if cycle_id else None  # one record, one copy
        if record is None:
            continue
        snapshot = database.official_cycle_snapshot(str(cycle_id))
        if not snapshot:
            continue
        for row in cycle_rows(snapshot):
            if str(row.get("symbol") or "").strip().upper() == clean:
                return _served(row, record, generation=resolved, cycle_id=str(cycle_id), scope="universe", market=selected)
    targeted_cycle = (resolved.get("targeted") or {}).get(clean)
    if targeted_cycle and "B3" in _markets_for(market):
        snapshot = database.official_cycle_snapshot(str(targeted_cycle))
        record = database.valuation_prediction_record(str(targeted_cycle), clean, source=source)
        if snapshot and record is not None:
            for row in cycle_rows(snapshot):
                if str(row.get("symbol") or "").strip().upper() == clean:
                    return _served(row, record, generation=resolved, cycle_id=str(targeted_cycle), scope="targeted", market="B3")
    return None


def official_stamp(database: Any, market: str, *, generation: Any = UNRESOLVED) -> dict[str, Any]:
    """The stamp every served response carries (I-TP3): producer, version, generation, this market's cycle inside it
    and its session. Explicit ``None`` values when there is no generation in force."""
    resolved = _resolve(database, generation)
    return {
        "tp_source": resolved.get("source") if resolved else None,
        "tp_source_version": resolved.get("source_version") if resolved else None,
        "official_generation_id": resolved.get("generation_id") if resolved else None,
        "official_cycle_id": (resolved.get("cycles") or {}).get(market) if resolved else None,
        "official_session_date": (resolved.get("session_dates") or {}).get(market) if resolved else None,
    }


def prediction_records(database: Any, market: str, symbol: str, *, source: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """History for studies and grading (rev 7, TP-C; §10.8): the immutable records of one symbol, newest first —
    by ``(prediction_instant, published_at)``, so a re-run follows its original (S4) — by source when given; never
    re-read through the current selection."""
    clean = symbol.strip().upper()
    rows: list[dict[str, Any]] = []
    for selected in _markets_for(market):
        rows.extend(database.list_valuation_predictions(selected, clean, source=source, limit=limit))
    rows.sort(key=lambda record: (_utc(record["prediction_instant"]), _utc(record.get("published_at") or record["prediction_instant"])), reverse=True)
    return rows[:limit]


def _generation_records(database: Any, generation: Mapping[str, Any], market: str, *, source: str) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Everything a generation serves for ``market`` in ONE source, keyed by symbol: the universe cycle's records plus
    the records of the targeted cycles it admitted for that market (universe wins on a collision, as ``official_row``
    serves) — and the targeted cycles included. Copies. Read by the studies' arm and by the before/after report."""
    cycle_id = (generation.get("cycles") or {}).get(market)
    results: dict[str, dict[str, Any]] = database.valuation_predictions_for_cycle(str(cycle_id), source=source) if cycle_id else {}
    targeted_cycles: dict[str, str] = {}
    for symbol, targeted_cycle in sorted((generation.get("targeted") or {}).items()):
        clean = str(symbol).strip().upper()
        if clean in results or market_of_entity(TARGETED_ANALYSIS, clean) != market:
            continue
        record = database.valuation_prediction_record(str(targeted_cycle), clean, source=source)
        if record is not None:
            results[clean] = record
            targeted_cycles[clean] = str(targeted_cycle)
    return results, targeted_cycles


def official_prediction_snapshot(database: Any, market: str, *, generation: Any = UNRESOLVED) -> dict[str, Any] | None:
    """The official records of one market for one generation, in the shape the studies adapter reads (``outputs.results``
    keyed by symbol), with ``published_at`` = the generation's activation — the provenance a study needs. A study
    replaying a decision passes the generation in force at that decision (``generation_at``), never the current one.
    ``results`` holds EVERYTHING the generation served for the market: the universe cycle's records plus the records
    of the targeted cycles it admitted for that market (F393-7 rev 5) — one map, keyed by symbol; each entry carries
    its own ``scope`` (``universe``/``targeted``) and ``cycle_id`` (the record's), and ``outputs.targeted_cycles``
    names the targeted cycles included. On a collision the universe record wins (it is what ``official_row`` serves)."""
    resolved = _resolve(database, generation)
    if not resolved:
        return None
    cycle_id = (resolved.get("cycles") or {}).get(market)
    if not cycle_id:
        return None
    # the records of the generation's own source (Passo 1): after a switch, the internal ones; an unknown source: nothing (Q3)
    source = _selected_source(resolved)
    if source is None:
        return None
    results, targeted_cycles = _generation_records(database, resolved, market, source=source)
    return {
        "id": str(cycle_id),
        "analysis_type": "valuation_official_prediction",
        "entity_key": f"{market}_OFFICIAL",
        "published_at": _utc(resolved["activated_at"]),
        "outputs": {"generation_id": resolved["generation_id"], "source": resolved["source"], "source_version": resolved["source_version"],
                    "session_date": (resolved.get("session_dates") or {}).get(market), "cycle_id": str(cycle_id),
                    "targeted_cycles": targeted_cycles, "results": results},
    }


def selection_health(database: Any, *, now: datetime) -> dict[str, Any]:
    """The state of the official selection for the health card and the receipts (B1): whether a generation is in
    force, how many sessions old each market's official cycle is, and which markets were carried over. A market whose
    calendar cannot answer is reported as such (``calendar_unavailable``) and counted stale: its freshness is unknown
    and its next cycle cannot be selected until the calendar is back (rev 5). ``head_has_successor`` names the successor
    of the head when the head (``max(activated_at)``) is not the chain tip — a row chained behind its predecessor; the
    next activation chains on the tip (W4). A head whose source is unknown (Q3) is ``status = "error"``: ``source`` is
    ``None``, ``unknown_source`` names what the row carries, and the detail says nothing is served until the mesa rolls
    back by explicit order. ``freeze`` is the mesa's freeze holding the head at ``now`` (``selection_freeze``, F1) or
    ``None``; a frozen head keeps its status (the freshness is reported as it is) and the detail says until when."""
    current = current_generation(database)
    if not current:
        return {"status": "none", "generation_id": None, "source": None, "unknown_source": None, "markets": {}, "head_has_successor": None,
                "freeze": None, "detail": "no official generation in force — screeners serve nothing"}
    source = _selected_source(current)
    successor = database.valuation_official_selection_successor(str(current["generation_id"]))
    today = _utc(now)
    markets: dict[str, dict[str, Any]] = {}
    stale: list[str] = []
    unavailable: list[str] = []
    for market in MARKETS:
        session = (current.get("session_dates") or {}).get(market)
        expected: str | None
        try:
            expected = session_date_of(market, today)
        except CalendarUnavailable:
            expected = None
            unavailable.append(market)
        age: int | None = 0
        if expected is None:
            age = None
        elif session and session < expected:
            try:
                age = int(_calendar(market).sessions_distance(session, expected)) - 1
            except Exception:
                age = 1
        markets[market] = {"cycle_id": (current.get("cycles") or {}).get(market), "session_date": session, "expected_session": expected, "sessions_behind": age,
                           "calendar_unavailable": expected is None, "carried": market in ((current.get("receipt") or {}).get("carried_markets") or [])}
        if age is None or age >= 2:
            stale.append(market)
    detail = f"stale official cycles: {', '.join(stale)}" if stale else "every market within one session"
    if unavailable:
        detail += f"; calendar unavailable: {', '.join(unavailable)}"
    if successor:
        detail += f"; the head has a successor dated behind it ({successor['generation_id']}) — the next activation chains on the chain tip"
    freeze = selection_freeze(current, now=today)
    if freeze is not None:
        detail += f"; frozen by the mesa's order until {freeze['until']} — no automatic activation until then or the mesa's next order (F1)"
    status = "stale" if stale else "ok"
    if source is None:  # Q3: loud on the card too — nothing is served under this head
        status = "error"
        detail = (f"the generation in force selects an UNKNOWN source {current.get('source')!r} — nothing is served and nothing is activated "
                  f"until the mesa selects a known source by explicit order (rollback to the blend); {detail}")
    return {"status": status, "generation_id": current["generation_id"], "source": source,
            "unknown_source": None if source is not None else current.get("source"),
            "activated_at": current["activated_at"], "markets": markets, "stale_markets": stale, "calendar_unavailable": unavailable,
            "head_has_successor": str(successor["generation_id"]) if successor else None, "freeze": freeze, "detail": detail}


def bootstrap_official_selection(database: Any) -> dict[str, Any]:
    """At process start (valuation worker) or by CLI: turn the latest universe cycle of every market into prediction
    records (idempotent — records are unique per cycle) and activate the first generation if all three are valid, so
    that a deploy of Passo 0 does not leave the screeners empty until every market publishes a new cycle. Records of
    EVERY market first, ONE activation after (records before selection; the receipt counts what this call recorded).
    The activation is dated by the wall clock at its INSERT, as every automatic activation (Y1), never before the head
    it chains on (Z1); the mesa's last explicit order stands over the targeted cycles predicted before it (Z2) and over
    the universe cycles predicted before it (W1; the prediction instant, S1): a bootstrap never undoes a rollback."""
    recorded: dict[str, int] = {}
    for market in MARKETS:
        raw = database.latest_analysis_snapshot(UNIVERSE_ANALYSIS, f"{market}_UNIVERSE")
        if raw:
            recorded[market] = record_cycle_predictions(database, _normalized_snapshot(raw, analysis_type=UNIVERSE_ANALYSIS, entity_key=f"{market}_UNIVERSE"))
    activated = activate_generation_if_changed(database)
    generation = activated or current_generation(database)
    logger.info("valuation_official bootstrap: recorded %s; generation %s", recorded, generation["generation_id"] if generation else None)
    return {"recorded": recorded, "generation": generation}


def _percentile(values: list[float], fraction: float) -> float | None:
    """``P90_METHOD``: linear interpolation at position ``(n − 1) × fraction`` over the sorted sample; ``None`` when empty.
    Local on purpose — the screener's helper lives in a module that imports this one (no cycle), and the method is
    declared in the receipt so the mesa can recompute it."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _ratio_stats(values: list[float]) -> dict[str, float | None]:
    magnitudes = [abs(value) for value in values]
    return {"median": statistics.median(values) if values else None, "p10": _percentile(values, 0.1), "p90": _percentile(values, 0.9),
            "abs_median": statistics.median(magnitudes) if magnitudes else None, "abs_p90": _percentile(magnitudes, 0.9)}


def _quantiles(values: list[float]) -> dict[str, float | None]:
    """The spread of a served quantity (rev 9: the upside of each arm), ``P90_METHOD`` at 10/25/75/90 %, the median exact."""
    return {"p10": _percentile(values, 0.1), "p25": _percentile(values, 0.25), "median": statistics.median(values) if values else None,
            "p75": _percentile(values, 0.75), "p90": _percentile(values, 0.9)}


def _change_buckets(ratios: list[float]) -> dict[str, Any]:
    """How many TPs move, and by how much (rev 9): ``down``/``flat``/``up`` by the sign of ``tp_internal / tp_blend − 1`` and
    the magnitude in ``TP_CHANGE_BUCKETS`` (upper bound exclusive; the last bucket ``ge_25pct``). Counts only."""
    magnitude: dict[str, int] = {name: 0 for name, _ in TP_CHANGE_BUCKETS}
    magnitude["ge_25pct"] = 0
    for ratio in ratios:
        name = next((bucket for bucket, bound in TP_CHANGE_BUCKETS if abs(ratio) < bound), "ge_25pct")
        magnitude[name] += 1
    return {"down": sum(ratio < 0 for ratio in ratios), "flat": sum(ratio == 0 for ratio in ratios), "up": sum(ratio > 0 for ratio in ratios),
            "abs": magnitude}


def _report_view(database: Any, generation: Mapping[str, Any], market: str, record: Mapping[str, Any],
                 rows: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any] | None:
    """The row a consumer would be served for ``record`` (``_served``, the same overlay), read from the record's own cycle —
    ``None`` when the cycle row is gone or, for an internal record, has no internal view (counted by the report, not logged:
    a receipt over a pre-rev-9 cycle would otherwise warn once per symbol). ``rows`` memoizes the cycles read."""
    cycle_id = str(record["cycle_id"])
    if cycle_id not in rows:
        snapshot = database.official_cycle_snapshot(cycle_id)
        rows[cycle_id] = {str(row.get("symbol") or "").strip().upper(): row for row in cycle_rows(snapshot)} if snapshot else {}
    row = rows[cycle_id].get(str(record["symbol"]))
    if row is None or (record.get("source") == SOURCE_INTERNAL and internal_view(row) is None):
        return None
    return _served(row, record, generation=generation, cycle_id=cycle_id, scope=str(record.get("scope") or "universe"), market=market)


def one_pager_rating(upside_percent: Any) -> str | None:
    """The One Pager's rating of an upside (F3): the first of ``ONE_PAGER_RATING_CUTS`` it reaches, else
    ``ONE_PAGER_RATING_FLOOR`` — the rule of the pinned ``one_pager.py``, mirrored (a test reads its line). ``None`` without
    an upside. The receipt applies it to the SERVED upside (the TP over the cycle's price); the One Pager applies it to the
    price it quotes when generated."""
    upside = _number(upside_percent)
    if upside is None:
        return None
    return next((rating for rating, cut in ONE_PAGER_RATING_CUTS if upside >= cut), ONE_PAGER_RATING_FLOOR)


def _status_block(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """Status counts of each arm and the transitions (``before->after``, only the changed ones) over the served pairs."""
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    transitions: dict[str, int] = {}
    for old, new in pairs:
        before[old] = before.get(old, 0) + 1
        after[new] = after.get(new, 0) + 1
        if old != new:
            transitions[f"{old}->{new}"] = transitions.get(f"{old}->{new}", 0) + 1
    return {"before": dict(sorted(before.items())), "after": dict(sorted(after.items())), "changed": sum(transitions.values()),
            "transitions": dict(sorted(transitions.items()))}


def before_after_report(database: Any, *, generation: Any = UNRESOLVED, private_detail_path: str | Path | None = None,
                        cycles: Mapping[str, str] | None = None, targeted: Mapping[str, str] | None = None,
                        source_version: str | None = None) -> dict[str, Any]:
    """The before/after receipt of Passo 1 (spec §7-bis item 4): BEFORE = ONE generation (the head unless ``generation``
    is given) as it serves the blend; AFTER = the composition the order PROPOSES — ``cycles`` (every market) and
    ``targeted`` (symbol → cycle, normalized; with ``cycles`` given and ``targeted`` omitted the proposal admits NO
    targeted cycle — exactly as the order ``select_generation(cycles=…)`` without ``targeted`` purges them), both under
    ``SOURCE_INTERNAL`` — or, when no proposal is given, the same generation's own cycles and admissions (same cycles,
    both sources). The aggregate BINDS the after composition (C395-1): ``after_cycles`` (per market),
    ``after_targeted_sha256`` (the canonical hash of the normalized targeted mapping — the aggregate names no symbol;
    ``after_targeted_count`` is the count) and ``after_source_version`` (``source_version`` when the mesa declares it,
    else the union of the after cycles' methodology versions, ``"+".join(sorted(set))`` — the very string
    ``select_generation`` stamps when the order omits it, Q6), so the hash the mesa cites is the hash of THIS proposal:
    ``select_generation`` recomputes it with the exact ``cycles``/``targeted``/``source_version`` of the order and a
    receipt computed over another composition (another cycle in a market, a targeted admission added or dropped,
    another declared version) is refused.
    Per market ``n`` (symbols recorded in BOTH sources), ``missing_internal`` (recorded in the blend only: rows produced
    before Passo 1), ``only_internal`` (recorded in the after arm only), and the median / p10 / p90 (signed and in
    magnitude, ``P90_METHOD``) of ``tp_internal / tp_blend − 1`` and of ``buy_in_internal / buy_in_blend − 1`` over the n
    pairs, with ``tp_change_buckets`` (``_change_buckets``). Rev 9 (V3): the SERVED view of both arms — what ``_served`` hands
    a consumer: the blend row, and the internal record under the producer's internal view — over the ``served_pairs`` (the
    pairs served on BOTH sides; ``before_unservable``/``after_unservable`` count the rest: a cycle row gone, or an after row
    without the internal view — a cycle produced before rev 9, which the validator also refuses): ``status`` (counts per
    arm, ``changed``, ``transitions``), ``rating`` (the same block for the One Pager rating of each arm's served upside,
    ``one_pager_rating``; the cuts are in ``rating_cuts``, F3), ``buy`` (the candidate gate ``BUY_STATUS``
    before/after/entered/left), ``upside_percent`` (quantiles of
    each arm and of the change in percentage points), ``score_change`` (points) and ``tp_validation`` (validated counts,
    null for a market whose rows carry no TP validation). The AGGREGATE (returned, printable) names no symbol;
    ``report_sha256`` is the canonical hash of the aggregate without itself — the hash the mesa's order to switch cites
    (``select_generation(before_after_sha256=…)``) and the owner accepts (``OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256``). The
    per-symbol DETAIL exists only in ``private_detail_path`` when given (written as the canonical JSON whose sha256 is the
    aggregate's ``private_detail_sha256``), never printed. ``ValueError`` without a generation in force, or under a
    generation whose source is unknown (Q3). Deterministic: no clock — the hash recomputes wherever the same generation is
    read, which is what lets ``select_generation`` check the hash a switch cites (Q1).
    The private file is created EXCLUSIVELY (Q5): ``O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW``, mode ``0o600`` (then
    ``fchmod`` so the umask cannot widen it) — an existing path, a file or a symlink (dangling or not), is refused with
    ``FileExistsError`` and nothing is overwritten or followed; the report is returned only after the bytes are written."""
    resolved = _resolve(database, generation)
    if not resolved:
        raise ValueError("no official generation in force: nothing to compare")
    generation_source = _selected_source(resolved)
    if generation_source is None:
        raise ValueError(f"the generation in force ({resolved.get('generation_id')}) selects an unknown source {resolved.get('source')!r}: "
                         "nothing is served under it and nothing to compare — roll back to the blend by explicit order first (Q3)")
    if cycles is not None:  # the proposal (C395-1): every market named; the after arm reads THESE cycles, not the head's
        missing = [market for market in MARKETS if market not in cycles]
        if missing:
            raise ValueError(f"the proposal's cycles must name every market; missing: {', '.join(missing)}")
        after_cycles = {market: str(cycles[market]) for market in MARKETS}
        after_targeted = _normalized_targeted(targeted or {}, strict=True)  # a proposal without targeted admits none — as the order does
    else:
        after_cycles = {market: str(cycle_id) for market, cycle_id in dict(resolved.get("cycles") or {}).items()}
        after_targeted = _normalized_targeted(targeted if targeted is not None else (resolved.get("targeted") or {}), strict=targeted is not None)
    if source_version is None:  # the version the switch would stamp (Q6): the union of the after cycles' methodology versions
        versions: set[str] = set()
        for cycle_id in after_cycles.values():
            snapshot = database.analysis_snapshot_by_id(cycle_id)
            versions.add(_source_version(snapshot) if snapshot else "unknown")
        after_source_version = "+".join(sorted(versions))
    else:
        after_source_version = str(source_version)
    after_generation: dict[str, Any] = {**resolved, "cycles": after_cycles, "targeted": after_targeted}
    markets: dict[str, dict[str, Any]] = {}
    detail_markets: dict[str, dict[str, Any]] = {}
    rows: dict[str, dict[str, dict[str, Any]]] = {}  # cycle id → its rows by symbol, read once for both arms
    for market in MARKETS:
        blend, _ = _generation_records(database, resolved, market, source=SOURCE_OFFICIAL)
        internal, _ = _generation_records(database, after_generation, market, source=SOURCE_INTERNAL)
        pairs: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        served: list[dict[str, Any]] = []
        unservable = {"before": 0, "after": 0}
        validation_present = False
        for symbol in sorted(blend):
            before, after = blend[symbol], internal.get(symbol)
            if after is None:
                missing.append(symbol)
                continue
            pair: dict[str, Any] = {
                "tp_blend": float(before["tp"]), "tp_internal": float(after["tp"]), "tp_ratio": float(after["tp"]) / float(before["tp"]) - 1,
                "buy_in_blend": float(before["buy_in"]), "buy_in_internal": float(after["buy_in"]), "buy_in_ratio": float(after["buy_in"]) / float(before["buy_in"]) - 1,
            }
            shown_before = _report_view(database, resolved, market, before, rows)
            shown_after = _report_view(database, after_generation, market, after, rows)
            unservable["before"] += shown_before is None
            unservable["after"] += shown_after is None
            if shown_before is not None and shown_after is not None:
                view = {
                    "status_blend": str(shown_before.get("status") or "unknown"), "status_internal": str(shown_after.get("status") or "unknown"),
                    "upside_blend": _number(shown_before.get("upside_percent")), "upside_internal": _number(shown_after.get("upside_percent")),
                    "score_blend": _number(shown_before.get("score")), "score_internal": _number(shown_after.get("score")),
                    "validated_blend": shown_before.get("tp_validation_status") == "validated",
                    "validated_internal": shown_after.get("tp_validation_status") == "validated",
                }
                view["rating_blend"] = one_pager_rating(view["upside_blend"]) or "unknown"  # F3: what the owner reads on a One Pager
                view["rating_internal"] = one_pager_rating(view["upside_internal"]) or "unknown"
                validation_present = validation_present or "tp_validation_status" in shown_before or "tp_validation_status" in shown_after
                pair.update(view)
                served.append(view)
            pairs[symbol] = pair
        upsides = [(view["upside_blend"], view["upside_internal"]) for view in served if view["upside_blend"] is not None and view["upside_internal"] is not None]
        scores = [view["score_internal"] - view["score_blend"] for view in served if view["score_blend"] is not None and view["score_internal"] is not None]
        tp_ratios = [pair["tp_ratio"] for pair in pairs.values()]
        markets[market] = {
            "n": len(pairs), "missing_internal": len(missing), "only_internal": len(set(internal) - set(blend)),
            "served_pairs": len(served), "before_unservable": unservable["before"], "after_unservable": unservable["after"],
            "tp": _ratio_stats(tp_ratios), "tp_change_buckets": _change_buckets(tp_ratios),
            "buy_in": _ratio_stats([pair["buy_in_ratio"] for pair in pairs.values()]),
            "status": _status_block([(view["status_blend"], view["status_internal"]) for view in served]),
            "rating": _status_block([(view["rating_blend"], view["rating_internal"]) for view in served]),  # F3: the One Pager rating of the served upside
            "buy": {"status": BUY_STATUS, "before": sum(view["status_blend"] == BUY_STATUS for view in served),
                    "after": sum(view["status_internal"] == BUY_STATUS for view in served),
                    "entered": sum(view["status_blend"] != BUY_STATUS and view["status_internal"] == BUY_STATUS for view in served),
                    "left": sum(view["status_blend"] == BUY_STATUS and view["status_internal"] != BUY_STATUS for view in served)},
            "upside_percent": {"before": _quantiles([old for old, _ in upsides]), "after": _quantiles([new for _, new in upsides]),
                               "change_pp": _ratio_stats([new - old for old, new in upsides])},
            "score_change": _ratio_stats(scores),
            "tp_validation": ({"before_validated": sum(view["validated_blend"] for view in served),
                               "after_validated": sum(view["validated_internal"] for view in served)} if validation_present else None),
        }
        detail_markets[market] = {"pairs": pairs, "missing_internal": missing, "only_internal": sorted(set(internal) - set(blend))}
    detail = {"schema": f"{BEFORE_AFTER_SCHEMA}_DETAIL", "generation_id": resolved["generation_id"], "markets": detail_markets}
    aggregate = {
        "schema": BEFORE_AFTER_SCHEMA,
        "generation_id": resolved["generation_id"],
        "generation_source": generation_source,
        "source_from": SOURCE_OFFICIAL,
        "source_to": SOURCE_INTERNAL,
        "cycles": dict(resolved.get("cycles") or {}),
        "targeted_cycles": len(resolved.get("targeted") or {}),  # a count: the aggregate names no symbol
        "after_cycles": after_cycles,  # C395-1: the AFTER composition the hash binds — the order's cycles, per market
        "after_targeted_count": len(after_targeted),
        "after_targeted_sha256": canonical_sha256(dict(sorted(after_targeted.items()))),  # the targeted mapping, hashed: no symbol in the aggregate
        "after_source_version": after_source_version,  # the version the switch stamps (declared, or the after cycles' union): bound too
        "session_dates": dict(resolved.get("session_dates") or {}),
        "source_version": resolved.get("source_version"),
        "buy_status": BUY_STATUS,
        "rating_cuts": {**{rating: cut for rating, cut in ONE_PAGER_RATING_CUTS}, ONE_PAGER_RATING_FLOOR: None},  # F3: the cuts the ratings were read with
        "markets": markets,
        "p90_method": P90_METHOD,
        "private_detail_sha256": canonical_sha256(detail),
    }
    report = {**aggregate, "report_sha256": canonical_sha256(aggregate)}
    if private_detail_path is not None:
        _write_private_detail(Path(private_detail_path), detail)
    return report


BEFORE_AFTER_ATTESTATION_KEYS = ("producer_build_sha", "receipt_sha256")


def attest_before_after(report: Mapping[str, Any], *, producer_build_sha: str | None) -> dict[str, Any]:
    """The receipt as the CLI prints it (Codex P2 on #451): the aggregate plus the identity of the build that PRODUCED it —
    ``producer_build_sha``, the deployed revision (``C3PO_BUILD_SHA``) read by the very process that computed the aggregate —
    and ``receipt_sha256``, the canonical hash of the aggregate WITH that identity (every key but itself), so the identity
    cannot be swapped without the receipt hash failing. A publisher attributes the receipt to ``producer_build_sha`` and
    never to a revision read by another process: a deploy between the receipt and its rendering would otherwise publish
    a receipt computed under build A as build B's. ``report_sha256`` is unchanged and excludes the identity ON PURPOSE: it
    names the CONTENT the owner accepts, the lock commit writes and the order recomputes — under the lock commit's own
    build, another build by design (an identity inside it would refuse every switch). The identity is recorded as read
    (``None`` or ``"development"`` outside a deploy); the publisher refuses a receipt whose identity is not a commit.
    ``ValueError`` on a report that already carries an attestation key (never attested twice)."""
    present = [key for key in BEFORE_AFTER_ATTESTATION_KEYS if key in report]
    if present:
        raise ValueError(f"the before/after report is already attested ({', '.join(present)}): attest the library report once")
    attested = {**report, "producer_build_sha": producer_build_sha}
    return {**attested, "receipt_sha256": canonical_sha256(attested)}


def _pt_number(value: Any, *, digits: int = 1, suffix: str = "", signed: bool = False, scale: float = 1.0) -> str:
    """A number as the owner reads it (decimal comma; ``scale`` 100 turns a ratio into percent); ``n/d`` for an absent one."""
    number = _number(value)
    if number is None:
        return "n/d"
    number *= scale
    text = f"{number:+.{digits}f}" if signed else f"{number:.{digits}f}"
    return text.replace(".", ",") + suffix


def _pt_counts(block: Mapping[str, Any] | None, *, quoted: bool = True) -> str:
    return ", ".join(f"`{name}` {count}" if quoted else f"{name} {count}" for name, count in (block or {}).items()) or "—"


def _pt_cuts(cuts: Any) -> str:
    """The rating cuts as the owner reads them: ``COMPRA ≥ 25 %, …, REDUZIR abaixo`` (the floor has no cut)."""
    items = [(str(name), _number(cut)) for name, cut in (cuts.items() if isinstance(cuts, Mapping) else [])]
    items.sort(key=lambda item: (item[1] is None, -(item[1] or 0.0)))  # highest cut first, the floor last — whatever order the JSON kept
    return ", ".join(f"{name} ≥ {_pt_number(cut, digits=0, suffix=' %')}" if cut is not None else f"{name} abaixo" for name, cut in items) or "n/d"


def before_after_markdown(report: Mapping[str, Any]) -> str:
    """The receipt as the owner reads it — Portuguese markdown rendered ONLY from the aggregate (rev 9): no symbol can reach
    it, so it is safe in a public CI log (``$GITHUB_STEP_SUMMARY``). It quotes ``report_sha256``: the hash the owner accepts
    is the one the lock commit names and the order cites."""
    markets = {market: item for market, item in (report.get("markets") or {}).items() if isinstance(item, Mapping)}
    lines = [
        "## Valuation P1 — antes/depois do TP oficial sem consenso",
        "",
        f"- Recibo `report_sha256`: `{report.get('report_sha256')}` (esquema `{report.get('schema')}`)",
        *([f"- Produzido pela revisão implantada `{report.get('producer_build_sha')}` (`receipt_sha256` `{report.get('receipt_sha256')}`: "
           "o recibo com a identidade do produtor)"] if "producer_build_sha" in report else []),
        f"- Antes: geração `{report.get('generation_id')}` servindo `{report.get('source_from')}` (fonte em vigor: `{report.get('generation_source')}`)",
        f"- Depois: `{report.get('source_to')}`, versão `{report.get('after_source_version')}`, "
        f"{report.get('after_targeted_count')} direcionado(s) (hash `{str(report.get('after_targeted_sha256') or '')[:12]}…`)",
        f"- **Candidato** = status `{report.get('buy_status')}` (o portão da lista de Candidatos; a lista B3 ainda deduplica emissores e exige a "
        "zona de poder) — **não** é o rating do One Pager",
        f"- **Rating do One Pager** = faixa do upside do TP servido ({_pt_cuts(report.get('rating_cuts'))}), sobre o preço do ciclo — o One Pager "
        "aplica os mesmos cortes à cotação do momento em que é gerado",
        "",
        "| Mercado | Pares | Só no blend | Servidos nos dois | Sem visão interna | Candidatos antes → depois | Entram | Saem "
        "| Mudam de status | COMPRA (One Pager) antes → depois | Mudam de rating | ΔTP mediana | ΔTP p10 / p90 | Upside mediano antes → depois |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for market in MARKETS:
        if market not in markets:
            continue
        item = markets[market]
        tp, buy, upside = item.get("tp") or {}, item.get("buy") or {}, item.get("upside_percent") or {}
        rating = item.get("rating") or {}
        top = ONE_PAGER_RATING_CUTS[0][0]
        ratio = {key: _pt_number(tp.get(key), digits=2, suffix=" %", signed=True, scale=100) for key in ("median", "p10", "p90")}
        lines.append(
            f"| {market} | {item.get('n')} | {item.get('missing_internal')} | {item.get('served_pairs')} | {item.get('after_unservable')} "
            f"| {buy.get('before')} → {buy.get('after')} | {buy.get('entered')} | {buy.get('left')} | {(item.get('status') or {}).get('changed')} "
            f"| {(rating.get('before') or {}).get(top, 0)} → {(rating.get('after') or {}).get(top, 0)} | {rating.get('changed', 0)} "
            f"| {ratio['median']} | {ratio['p10']} / {ratio['p90']} "
            f"| {_pt_number((upside.get('before') or {}).get('median'), suffix=' %')} → {_pt_number((upside.get('after') or {}).get('median'), suffix=' %')} |"
        )
    lines += ["", "### Status por mercado (pares servidos nos dois lados)", ""]
    for market in MARKETS:
        if market not in markets:
            continue
        item = markets[market]
        status = item.get("status") or {}
        transitions = ", ".join(f"`{name.replace('->', ' → ')}` {count}" for name, count in (status.get("transitions") or {}).items()) or "nenhuma"
        buckets = item.get("tp_change_buckets") or {}
        magnitude = buckets.get("abs") or {}
        lines.append(f"- **{market}** — antes: {_pt_counts(status.get('before'))}; depois: {_pt_counts(status.get('after'))}; transições: {transitions}.")
        rating = item.get("rating") or {}
        moves = ", ".join(f"{name.replace('->', ' → ')} {count}" for name, count in (rating.get("transitions") or {}).items()) or "nenhuma"
        lines.append(f"  Rating do One Pager — antes: {_pt_counts(rating.get('before'), quoted=False)}; depois: {_pt_counts(rating.get('after'), quoted=False)}; "
                     f"mudanças: {moves}.")
        lines.append(f"  ΔTP: {buckets.get('down', 0)} caem, {buckets.get('flat', 0)} iguais, {buckets.get('up', 0)} sobem; |Δ| < 1 %: {magnitude.get('lt_1pct', 0)}, "
                     f"1–5 %: {magnitude.get('1_to_5pct', 0)}, 5–10 %: {magnitude.get('5_to_10pct', 0)}, 10–25 %: {magnitude.get('10_to_25pct', 0)}, "
                     f"≥ 25 %: {magnitude.get('ge_25pct', 0)}. Δ score mediano: {_pt_number((item.get('score_change') or {}).get('median'), signed=True)} ponto(s).")
        upside = item.get("upside_percent") or {}
        before, after = upside.get("before") or {}, upside.get("after") or {}
        lines.append(f"  Upside p10–p90: antes {_pt_number(before.get('p10'))} a {_pt_number(before.get('p90'), suffix=' %')}; depois {_pt_number(after.get('p10'))} a "
                     f"{_pt_number(after.get('p90'), suffix=' %')}; Δ mediano {_pt_number((upside.get('change_pp') or {}).get('median'), signed=True)} p.p.")
        if isinstance(item.get("tp_validation"), Mapping):
            lines.append(f"  TP validado: {item['tp_validation'].get('before_validated')} → {item['tp_validation'].get('after_validated')}.")
    lines += ["", "Nenhum símbolo é impresso: o detalhe por símbolo fica só no arquivo privado "
              f"(`private_detail_sha256` `{str(report.get('private_detail_sha256') or '')[:12]}…`)."]
    unservable = sum(int(item.get("after_unservable") or 0) for item in markets.values())
    if unservable:
        lines.append(f"**Atenção:** {unservable} par(es) sem a visão interna do produtor (ciclo anterior à rev 9) — a troca seria recusada pelo "
                     "validador; é preciso uma noite completa dos três produtores com esta revisão.")
    return "\n".join(lines) + "\n"


def _write_private_detail(path: Path, detail: Mapping[str, Any]) -> None:
    """The per-symbol detail as the canonical JSON bytes ``private_detail_sha256`` hashes, into a file created EXCLUSIVELY
    (Q5): ``O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW`` with mode ``0o600`` — an existing path (a file, or a symlink whether
    dangling or not: ``O_EXCL`` refuses the name, ``O_NOFOLLOW`` never follows it) is a ``FileExistsError`` and nothing is
    overwritten; ``fchmod(0o600)`` after the open, so a permissive umask cannot widen what the owner alone may read."""
    encoded = json.dumps(detail, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags, 0o600)
    except FileExistsError as error:
        raise FileExistsError(f"private detail path {path} already exists (a file or a symlink): the receipt's detail is never overwritten nor "
                              "written through a link — name a new file (Q5)") from error
    with os.fdopen(descriptor, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(encoded)


def _order_summary(generation: Mapping[str, Any]) -> dict[str, Any]:
    """What the order commands print (rev 9): the new generation WITHOUT the targeted symbols (a count and the hash of the
    normalized mapping, as the receipt) — the cycles, the source, the version and the receipt's ``source_switch``, and the
    freeze it carries or ends (F1)."""
    targeted = dict(sorted((generation.get("targeted") or {}).items()))
    receipt = generation.get("receipt") or {}
    return {"generation_id": generation.get("generation_id"), "previous_generation_id": generation.get("previous_generation_id"),
            "source": generation.get("source"), "source_version": generation.get("source_version"), "activated_at": generation.get("activated_at"),
            "cycles": dict(generation.get("cycles") or {}), "targeted_count": len(targeted), "targeted_sha256": canonical_sha256(targeted),
            "source_switch": receipt.get("source_switch"), "explicit": receipt.get("explicit"),
            "freeze": receipt.get("freeze"), "ended_freeze": receipt.get("ended_freeze")}


def targeted_valid_for(database: Any, generation: Mapping[str, Any], *, source: str = SOURCE_INTERNAL) -> dict[str, str]:
    """The ``generation``'s targeted admissions (normalized as the carry-over reads them, Y4) that ``select_generation``
    would accept for ``source``: a targeted cycle OF THAT SYMBOL that passes ``cycle_validation`` for ``source`` with the
    symbol's own record of it (F2). ``--keep-internal-targeted`` proposes exactly these — the valid rev-9 admissions are
    kept, only the ones the order would refuse are dropped — instead of purging every targeted cycle (a purged same-day
    cycle is not rebuilt by the producer that day: its One Pager failed until the next day). Deterministic for a given
    head (no clock beyond the cycles' own sessions), so the receipt and the order compute the same map."""
    kept: dict[str, str] = {}
    for symbol, cycle_id in _normalized_targeted(generation.get("targeted") or {}, strict=False).items():
        snapshot = database.analysis_snapshot_by_id(cycle_id)
        if not snapshot or snapshot.get("analysis_type") != TARGETED_ANALYSIS or str(snapshot.get("entity_key") or "").strip().upper() != symbol:
            continue
        recorded = database.valuation_predictions_for_cycle(cycle_id, source=source)
        if cycle_validation(snapshot, recorded=recorded, source=source)["valid"] and symbol in recorded:
            kept[symbol] = cycle_id
    return dict(sorted(kept.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Official TP selection (V3.2 rev 7 §7-bis): bootstrap records/generation, show the health, "
                                                 "publish the Passo 1 before/after receipt (aggregate only; the per-symbol detail goes to --private-detail), "
                                                 "or execute the mesa's order — the switch to the internal source (locked), the rollback to the blend, or the "
                                                 "freeze of the head between the receipt and the order.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bootstrap", action="store_true")
    group.add_argument("--health", action="store_true")
    group.add_argument("--before-after", action="store_true", help="the before/after receipt of the current generation (Passo 1); prints the aggregate only, "
                                                                     "attested with the producing build (producer_build_sha, receipt_sha256)")
    group.add_argument("--switch-to-internal", action="store_true",
                       help="the mesa's order: select_generation(source=official_internal_v1) over the proposal, citing --before-after-sha256 "
                            "(refused while the lock is false or the hash is not the accepted receipt)")
    group.add_argument("--rollback-to-blend", action="store_true",
                       help="the mesa's order: select_generation(source=official_blend_v1) over the proposal (never locked, no hash)")
    group.add_argument("--freeze-selection", action="store_true",
                       help="the mesa's freeze (F1): re-select the head's own composition with --until, so no automatic writer moves the head "
                            "between the receipt and the order")
    parser.add_argument("--until", metavar="ISO_INSTANT", default=None,
                        help="with --freeze-selection: when the freeze ends by itself, with its offset (e.g. 2026-10-20T21:00:00-03:00)")
    parser.add_argument("--private-detail", metavar="PATH", default=None, help="with --before-after: write the per-symbol detail to PATH (never printed)")
    parser.add_argument("--markdown", metavar="PATH", default=None,
                        help="with --before-after: APPEND the Portuguese summary of the aggregate to PATH (no symbols; $GITHUB_STEP_SUMMARY works)")
    parser.add_argument("--cycles", metavar="MARKET=CYCLE_ID", action="append", default=None,
                        help="with --before-after or an order: the proposal's universe cycle for MARKET (repeatable; markets not named keep the head's "
                             "cycle) — the receipt then binds THIS proposal (C395-1) and, unless --targeted names them, admits no targeted cycle")
    parser.add_argument("--targeted", metavar="SYMBOL=CYCLE_ID", action="append", default=None,
                        help="with --before-after or an order: a targeted admission of the proposal (repeatable)")
    parser.add_argument("--purge-targeted", action="store_true",
                        help="with --before-after or an order: the proposal admits no targeted cycle (the head's cycles, targeted={})")
    parser.add_argument("--keep-internal-targeted", action="store_true",
                        help="with --before-after or an order: the proposal keeps the head's targeted admissions valid for the internal source and "
                             "drops the others (F2; the head's cycles unless --cycles)")
    parser.add_argument("--source-version", metavar="VERSION", default=None,
                        help="with --before-after or an order: the source_version the order declares (else the cycles' union; a rollback: 'rollback')")
    parser.add_argument("--before-after-sha256", metavar="HASH", default=None, help="with --switch-to-internal: the accepted receipt's report_sha256")
    parser.add_argument("--reason", metavar="TEXT", default=None,
                        help="with an order or --freeze-selection: the reason written in the generation's receipt (required)")
    args = parser.parse_args(argv)
    order = args.switch_to_internal or args.rollback_to_blend
    if (args.cycles or args.targeted or args.purge_targeted or args.keep_internal_targeted or args.source_version) and not (args.before_after or order):
        parser.error("--cycles/--targeted/--purge-targeted/--keep-internal-targeted/--source-version require --before-after, --switch-to-internal "
                     "or --rollback-to-blend")
    if (args.private_detail or args.markdown) and not args.before_after:
        parser.error("--private-detail/--markdown require --before-after")
    if sum(map(bool, (args.targeted, args.purge_targeted, args.keep_internal_targeted))) > 1:
        parser.error("--targeted, --purge-targeted and --keep-internal-targeted are exclusive")
    if args.before_after_sha256 and not args.switch_to_internal:
        parser.error("--before-after-sha256 requires --switch-to-internal")
    if args.switch_to_internal and not args.before_after_sha256:
        parser.error("--switch-to-internal requires --before-after-sha256 (the report_sha256 of the receipt the owner accepted)")
    if (order or args.freeze_selection) and not (args.reason or "").strip():
        parser.error("an order (--switch-to-internal/--rollback-to-blend/--freeze-selection) requires --reason")
    if args.reason and not (order or args.freeze_selection):
        parser.error("--reason requires --switch-to-internal, --rollback-to-blend or --freeze-selection")
    if bool(args.until) != bool(args.freeze_selection):
        parser.error("--freeze-selection requires --until, and --until requires --freeze-selection")
    freeze_until: datetime | None = None
    if args.freeze_selection:
        try:
            freeze_until = datetime.fromisoformat(str(args.until))
        except ValueError:
            parser.error(f"--until expects an ISO 8601 instant, got {args.until!r}")
        if freeze_until is None or freeze_until.tzinfo is None:
            parser.error(f"--until needs its offset (e.g. 2026-10-20T21:00:00-03:00), got {args.until!r}")

    def _pairs(items: list[str] | None, flag: str, *, keys: tuple[str, ...] | None = None) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for item in items or []:
            key, sep, value = item.partition("=")
            if not sep or not key.strip() or not value.strip():
                parser.error(f"{flag} expects KEY=CYCLE_ID, got {item!r}")
            if keys is not None and key.strip() not in keys:  # an unknown market is refused, never ignored (Codex P3-2 on #395)
                parser.error(f"{flag} names an unknown market {key.strip()!r}; expected one of {', '.join(keys)}")
            if key.strip().upper() in {k.upper() for k in pairs}:  # case-insensitive: symbols normalize upper-case downstream
                parser.error(f"{flag} names {key.strip()!r} twice")
            pairs[key.strip()] = value.strip()
        return pairs

    from .config import get_settings
    from .database import Database
    database = Database(get_settings())

    def _proposal() -> tuple[dict[str, str] | None, dict[str, str] | None]:
        """The proposal exactly as the receipt reads it: with --cycles/--targeted/--purge-targeted/--keep-internal-targeted, the
        head's cycles overlaid by --cycles and targeted = --targeted, the head's admissions valid for the internal source
        (``targeted_valid_for``, F2) or none; without them, ``(None, None)`` — the head's own composition."""
        if not (args.cycles or args.targeted or args.purge_targeted or args.keep_internal_targeted):
            return None, None
        head = database.latest_valuation_official_selection() or {}
        cycles = {**{market: str(cycle) for market, cycle in dict(head.get("cycles") or {}).items()}, **_pairs(args.cycles, "--cycles", keys=tuple(MARKETS))}
        if args.keep_internal_targeted:
            return cycles, targeted_valid_for(database, head)
        return cycles, _pairs(args.targeted, "--targeted")

    if args.bootstrap:
        result = bootstrap_official_selection(database)
    elif args.before_after:
        cycles, targeted = _proposal()
        result = attest_before_after(  # the producer's identity, read by THIS process (Codex P2 on #451)
            before_after_report(database, private_detail_path=args.private_detail, cycles=cycles, targeted=targeted, source_version=args.source_version),
            producer_build_sha=os.environ.get("C3PO_BUILD_SHA"))
        if args.markdown:
            with open(args.markdown, "a", encoding="utf-8") as handle:  # appended: a CI step summary is an existing file
                handle.write(before_after_markdown(result))
    elif order:
        cycles, targeted = _proposal()
        if cycles is None:  # no proposal: the head's own composition — the cycles and admissions the receipt without options read
            head = database.latest_valuation_official_selection()
            if head is None:
                parser.error("no official generation in force: an order needs a head (bootstrap the blend first)")
            cycles = {market: str(cycle) for market, cycle in dict(head.get("cycles") or {}).items()}
            targeted = _normalized_targeted(head.get("targeted") or {}, strict=False)
        generation = select_generation(
            database, cycles=cycles, targeted=targeted, now=datetime.now(timezone.utc), activated_by="mesa", reason=str(args.reason).strip(),
            source=SOURCE_INTERNAL if args.switch_to_internal else SOURCE_OFFICIAL, source_version=args.source_version,
            before_after_sha256=args.before_after_sha256 if args.switch_to_internal else None,
        )
        result = _order_summary(generation)
    elif args.freeze_selection:
        assert freeze_until is not None  # parsed above (parser.error exits otherwise)
        result = _order_summary(freeze_selection(database, now=datetime.now(timezone.utc), until=freeze_until, reason=str(args.reason).strip(),
                                                 activated_by="mesa"))
    else:
        result = selection_health(database, now=datetime.now(timezone.utc))
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
