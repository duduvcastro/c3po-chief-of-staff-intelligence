Calendar-specific synthetic test supplements
==========================================

These fixtures are offline synthetic documents. They carry no real owner's
authority, epoch approval, host approval, operational GO, or Linux PASS. The
published original documents, chains and test fixtures remain byte for byte
unchanged. The operational binder, acceptance list and verifier are unchanged.

The real capacity_day_documents.py tool (SHA256
888a48e6654aff90e2f305b410ea6c5614485e5ac778354ba721b790bfead183)
generated a separate supplement for exchange_calendars 4.2.8 and 4.13.2.
Only the unsigned synthetic epoch input's calendar_pin_receipt is assigned from
the real tool.calendar_receipt(tool.app()) API. Every downstream contract, pin,
GO, configuration, request, summary and listing is rebuilt by the real day CLI;
the real verify CLI then verifies each result. No output hash or signed field is
remapped. Chain, order, templates and sessions are copied with identical bytes.

The original generator is programs-final-candidate/k8_eve/tests/make_fixtures.py
(SHA256 36b8131a5258265e43ce6a5a46c3364db53b1ccc0f1de0af603bec8e9b1df9be).
Its historical helper test_r2d2_v2_capacity_day_documents.py, expected SHA256
70ef5cf4bb08b1895d4bf4af4be47ea67a021fe23d9fa874111cbf3241def92e,
is unavailable in the published tool bundle and certified dd4ec4bb archive.
It was not used. calendar-fixtures/generate.py reuses the already published
synthetic inputs through the real tool API and CLI. The generator runtime adds
only the runner's missing config.py dependency, SHA256
91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897;
all listed tool/application bytes are checked against the original verifier
manifest. The generation runtime and virtual environments are not shipped here.

| Exact calendar version | Real computed calendar pin | Supplement manifest SHA256 |
| --- | --- | --- |
| 4.2.8 | 31654118a9d5ed9b04f81a434b773514dc06b79bfd499a299ea6d3a7d802e72d | 01d7e54324eb6e08919c1991eff635f577bf0fa36c6b105daa38eec1f899ca20 |
| 4.13.2 | 46777dde9fb7a2289d67e95467351380d8c22c8994ca21adf8cb618a7a67db8c | e2d952c55ec817110d04cf80c99acf9cf649c94639855ea01efffe994357f31a |

Each version's PROVENANCE.json records interpreter and dependency versions,
original/new unsigned epoch SHA256, unchanged input hashes, 20 real successful
day/verify commands with separate stdout/stderr hashes, and the complete output
hash list. Each version's SHA256SUMS includes its provenance and command streams.
Warnings remain in stderr evidence. The version-specific k8-document-fixtures.json
retains the historical tool_test_sha256 as original metadata, explicitly records
historical_helper_used=false, and rebuilds its role bytes from real outputs.

The two existing actual-tool test names are preserved. Only their real positive
contexts select the exact installed calendar version; all other default/mock
contexts still use the original fixtures. Missing or unexpected calendar versions
fail instead of skipping. Two new real negative cases select the other calendar
and require K8_DOCUMENTS_NOT_VERIFIED. Independently captured real CLI results
confirm DOCUMENTS_SELF_CHECK_CONFIG with exit 3 for both opposite sets on each
interpreter. Local four-case QA passes with zero skips on Python 3.9.6/4.2.8 and
Python 3.12.14/4.13.2. This does not make Python 3.9 verify 4.13.2 production
documents; the original verifier correctly refuses those bytes. A new sealed
delivery and a separate Fable Linux rehearsal remain required.

To reproduce generation offline, provide a new output directory named for the
installed exact calendar version, the original test-inputs directory, and the
original verifier runtime plus the separately pinned config dependency:

    <python> -B calendar-fixtures/generate.py --source <original-test-inputs> --runtime <runtime> --output <new-parent>/<exact-version>

The root binder SHA256SUMS must list every delivered file, including every nested
SHA256SUMS, excluding only the root manifest itself. New test/helper hashes belong
in bind/SHA256SUMS. The binder source and operational ACCEPTED_SEALS remain at
their existing digests.

Publication transform: local path prefixes in provenance and command streams
are neutral symbolic tokens. Warnings, refusals and counts are preserved.
CALENDAR_REDACTION.json maps private original hashes to published hashes
and describes each transformation without publishing raw path literals.
Original private artifacts and their original seals remain unchanged.
Original QA is attributed to the private input bytes; separate public-pin
QA metadata records the four-case rerun after updating only helper pins.
