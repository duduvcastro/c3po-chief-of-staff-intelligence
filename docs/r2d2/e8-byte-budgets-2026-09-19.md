# F-E8-1: measured byte budgets

The 550-entry DIAG rehearsal completed provider capture but failed while combining inputs: 958,924,104 bytes exceeded the 536,870,912-byte in-memory cap. The failed plan is closed; no replay or implicit provider-budget increase is authorized.

This change raises the host executor buffer and application staging total to 2 GiB. Both remain hard, fail-closed limits. It changes neither provider request budgets nor any existing approved plan. A new exact plan/GO and complete source repin are required before another run.

Evidence: FAILED SHA256 `6885f2785310eaa943aad4d567f83c0a6c6f11dd6656ee8d46d06d489d58118e`; capture manifest SHA256 `4b6c9eac521feff50f307f0c9a95fc5b48a10752dc70fb892f4d7651bcf3a290`. No names or payloads are included here.

| Bound | Measured bytes | Previous cap | Candidate cap | Candidate / measured |
| --- | ---: | ---: | ---: | ---: |
| Host `_prepare_acquired` / `_assess_manifest` combined blobs | 958,924,104, excluding final manifest overhead | 512 MiB | 2 GiB | 2.24x before manifest overhead |
| Application `risk_stage.MAX_TOTAL`, decoded inputs | 958,924,104 lower bound; execute/assessment did not run | 512 MiB | 2 GiB | 2.24x against measured blobs; final stage size unmeasured |
| `risk_stage.MAX_FILE`, executor `_Inputs.MAX_BYTES` | 11,034,615 largest direct snapshot | 16 MiB | 16 MiB | 1.52x |
| HTTP per-response limit (acquisition/transport/host plan) | 995,941 largest predecessor HTTP body; direct snapshot is a conservative upper bound for its nested HTTP body | 16 MiB | 16 MiB | >=1.52x on measured payloads |
| Insider HTTP total, approved plan and runner accepted maximum | 42,480,398 | 1 GiB | 1 GiB (unchanged) | 25.28x |
| Runner default HTTP total (explicit plan overrides it) | 42,480,398 | 256 MiB | 256 MiB (unchanged) | 6.32x |
| External predecessor HTTP budget | 404,963,292 | 512 MiB | **1 GiB required in next reviewed package** | 2.65x proposed |
| External predecessor evidence store | 406,667,136 complete source tree | 512 MiB plus separate 4 KiB failure receipt | **1 GiB plus failure reserve required in next reviewed package** | 2.64x proposed |
| External source binder input budget | 406,408,367 bound input tree | 512 MiB | **1 GiB required in next reviewed package** | 2.64x proposed |
| External successor copy of `risk_input_stage.MAX_TOTAL` | 958,924,104 lower bound | 512 MiB | **2 GiB required in next reviewed package** | 2.24x proposed |

The external sealed E8 and successor packages are not repository runtime files. They are immutable and are **not changed by merging this PR**. Their three 512 MiB source/binder limits have only 1.32–1.33x measured headroom, below the requested 1.5x. Their staging copy must also adopt the application 2 GiB bound. All four changes are mandatory before a new package may receive execution GO; the next package must be separately sealed, tested and audited. Existing package hashes and authorizations cannot be inherited.

The capture spool was 555,176,459 bytes (including repeated serialized evidence), while HTTP capture was only 42,480,398 bytes. HTTP caps do not bound JSON/base64 expansion or total resident memory. The executor's buffer cap is a logical sum of input blobs, not an RSS guarantee; staging can hold encoded and decoded representations simultaneously. Disk and memory checks remain part of the next rehearsal preflight.

Execution did not run, so final assessment/staging/output sizes and execute duration are unmeasured. The 1.5x criterion must be rechecked on those actual outputs in the next authorized rehearsal; this table does not certify end-to-end capacity or operation.

Validation covers acceptance above the former 512 MiB buffer boundary, exact 2 GiB acceptance, refusal of one additional byte without mutation, replacement accounting, and staging total-limit refusal before any acceptance marker. Boundary tests reuse immutable byte chunks to exercise production byte accounting without allocating multi-gigabyte CI fixtures.
