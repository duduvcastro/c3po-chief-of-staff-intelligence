# Provider Timestamp Workstream V1

## Evidence anchor

The completed `MICROSTRUCTURE_TAPE_PROBE_V1` run `33069776868` is the factual
source for the regression vectors in
`c3po/backend/tests/fixtures/provider_ts_no_tape_support_v1.json`.

- Report self-hash: `aeff080a2c23b9dc523697f991bfe1afe2d0d0e575277fb55eace18ad5a65e67`.
- Report file SHA-256: `0f72e092cf2d4251f1dacf87b3c16233e568477a7d3e2a696813e11648129ba6`.
- Manifest file SHA-256: `e4b318a155863078486b03c322ef88ac49d97cd57074d5062fd652d85f722adf`.
- Raw Massive tape SHA-256: `b8bf7f8a1d81adee6bbfacec31e4a3847accc54245f77fe0f5d6f4918c033cfd`.
- Classification: 18 `no_tape_support` cases, representing 14 unique fills
  across 12 symbols.

The 18 study-level cases remain separate. A fill shared by the exit and entry
studies is not silently deduplicated because each study provenance is part of
the regression contract.

## Required instrumentation

Future quote-path instrumentation must preserve, for each decision input:

1. the provider event timestamp (`provider_ts`);
2. the instant C3PO received the event (`received_at`);
3. the instant the event entered the decision-ready cache (`processed_at`);
4. the instant the API served the value (`served_at`);
5. symbol, provider, transport, source event identifier when available, and a
   stable payload hash.

The fixture is the nominal acceptance set for proving that these timestamps
can distinguish provider-originated unsupported prices from transport,
processing, cache, and presentation delay.

## Governance

- This workstream does not change the current G1/G2/G3 gate, its 25 bps band,
  any consumer, valuation, TP, strategy, or official metric.
- `no_tape_support` means only that no valid Massive tape trade was found within
  10 bps in the frozen window. It is a diagnostic vector, not proof of provider
  fault by itself.
- Phase 2 continuous tape ingestion remains unauthorized. Reopening it requires
  a new spec and decision.
