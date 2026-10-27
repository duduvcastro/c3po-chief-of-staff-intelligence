# Signed ensemble: computation and instrument binding

The owner signed `PREREG_VALUATION_ENSEMBLE_PIT_US_V1` revision 1 on 27 October 2026
at 09:59 BRT, receipt 6442500464. The document bytes are
`712b4c171c4d059a31156eba8f7a9624f1195083309471e89e0519271d2e5471`
at commit `8b02ba0fbf715a9abb421eea6f00238aad5ef38d`.

The grade computes the 16 model kernels directly from the reference grade's
as-filed SEC facts, close(D), Treasury curve at T and RAW analyst-target snapshot.
It does not use a V3 model target as an ensemble input. The served target is
retained solely for the paired comparison. Eight aggregations are published;
the primary removes exactly one smallest and one largest value, including the
house-mean consensus as one value, with at least three values before trimming.
Missing consensus leaves the fundamental-model values and records the reason.

## Two distinct paths

`compute_grid_section` is the calculation API in `valuation_ensemble_grid.py`.
It uses the assumptions already declared by the signed retrospective grade,
including the pinned current catalogue classification and retrospective price
publication. These are disclosed conventions, not independent authentication of
historical originals, issuer/class rights, share basis or sector history.
Its output keeps 16 values or refusal reasons for every catalogue name.
The original-byte transport/capture/provenance path remains separate and may
continue in parallel; its missing evidence does not block this calculation API.

`execute_grade_chunk` is the explicit bounded artifact-writing API. The caller
owns the read-only database handle, pinned-price factory, private receipt store
and actual operational guard. It refuses a missing/mismatched instrument pin or
an old-rev3 owner order. It checks the ensemble owner's order and deadline
before/after reads, before computation and before persistence. Resuming verifies
the immutable artifact, current instrument and actual reference siblings.
The sink stores each company as its own bounded private object and commits the
section header last. `load_grade_artifact` reconstructs and verifies the complete
section; missing/altered company objects refuse it. An interrupted attempt may
leave private orphan objects, but cannot mark a section complete. This avoids
placing a whole multi-company ledger into the legacy 16 MiB object limit. The
600 copied-record size probe is synthetic, not a claim of measured host capacity
or 600 actual model evaluations.

This API does not install, activate, dispatch, deploy, promote or alter a DB.

The supplied CLI and manual workflow inventory source bytes only:

```sh
cd c3po/backend
python -m app.valuation_ensemble_executor --inventory --repository-root /path/to/repository
```

An inventory is **not** an issued instrument pin, an operational driver or an
authorization to run. The final host/chunk driver must execute the existing
deployment lock, host running/blocking, timer/window, backfill-paused and
autopilot-off guards. That driver and the actual scientific workflow must be
reviewed and included in the single instrument pin before the first run. The
manual inventory workflow must not be represented as a tested host runner.

## Before the first grade or label

1. Review the complete computation/report/executor/operational-driver delta.
2. Merge through the established Fable review process; identify the exact main
   commit and every instrument file, including the statistical dependencies.
3. Publish the single `VALUATION-ENSEMBLE-INSTRUMENT-PIN-v1` receipt for this
   revision with its exact file inventory, constants, technical GO and owner's
   signature. No actual pin or signature is created by these APIs/tests.
4. Supply `InstrumentBinding` from that independently verified channel receipt.
   A digest/signature/comment ID copied from an untrusted JSON cannot authenticate
   itself. The expected pin digest is an external trust anchor.
5. Obtain the ensemble-specific owner order, including its session range,
   expiration and chunk cap. The old study's owner orders cannot authorize this
   new grade. Resume currently requires the same ensemble owner-order digest;
   a successor-order resume needs its own reviewed authorization path.
6. Publish the completed grade manifest digest. The report requires this expected
   digest independently of the supplied manifest's own digest.

The report verifies actual source siblings, target/screen/input correspondences,
all 16 model results and the eight recomputed aggregations before calling the
label reader. Its calendar and maturity are derived from the reference
publication metadata; neither label cutoff nor calendar can be changed by a free
argument after the manifest is published. Non-stock catalogue rows remain in the
input ledger but do not inflate stock coverage or cause label reads.

Precision uses the difference of median absolute log errors, with the geometric
12-month target path evaluated at 126 and 252 sessions. Ranking uses executable
returns on its separate clock. The signed IC, spread, paired difference,
coverage, attrition, complete-block and 12-month conditions all remain mandatory.
`design_table()` describes power of individual conditions, never full-PASS power.

Only a valid PASS permits the conditional promotion to one target across all
services. A technical code review, source inventory, successful CI or a computed
section is not that verdict. None of the tests accompanying this change read
real outcomes or change any served target.
