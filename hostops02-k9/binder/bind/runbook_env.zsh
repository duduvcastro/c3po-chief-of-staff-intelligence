# Sourced at the start of every RUNBOOK block (shell state does not persist between calls). Defines names only.
# Usage, first line of every block:   L=<label>; if source <this file>; then ... fi
setopt noclobber
B="${${(%):-%N}:A:h}"
S="${B:h}"
W="${BIND_WORK_ROOT:?Defina BIND_WORK_ROOT para as cópias locais revisadas}"
PY=/usr/bin/python3
BIND="${B}/bind_once.py"
PICK="${B}/pick.py"
REPO=duduvcastro/c3po-chief-of-staff-intelligence
ISSUE=429
# The executed bound set the transport fields are copied from (read by the binder, never printed). Durable copy in W.
REFERENCE="${W}/hostfacts01-fable-20261002/bound/DISPATCH.BOUND.json"
W1_FAMILY="${S}/w1preflight/candidate"
HOSTOPS_FAMILY="${S}/hostops01/candidate"
# HOSTOPS02: the durable copy of the four operations and the core (the seals sent for review on 2026-10-02, RUNBOOK 1), and the
# sealed copy every bind and dispatch is made from (RUNBOOK 10.1)
HOSTOPS02_SOURCE="${W}/fable-hostops02-tier0-20261002-r2"
HOSTOPS02_COPY="${W}/hostops02-sealed"
is_hash() { [[ "$1" =~ '^[0-9a-f]{64}$' ]] }
is_label() { [[ "$1" =~ '^[a-z0-9][a-z0-9-]{0,39}$' ]] }
is_comment_url() { [[ "$1" =~ '^https://github\.com/duduvcastro/c3po-chief-of-staff-intelligence/issues/[0-9]{1,6}#issuecomment-[0-9]{6,20}$' ]] }
is_utc_stamp() { [[ "$1" =~ '^2026-10-(0[2-9]|10)T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z$' ]] }
if ! is_label "${L}"; then echo "PARADO: defina L=<label> antes do source (o mesmo label do arquivo de parametros); nada foi feito"; return 1; fi
# RUN_BASE is only set by the rehearsal of these blocks; a real run lives under bind/runs.
RUN="${RUN_BASE:-${B}/runs}/${L}"
# run.env is written once by block 1a of the runbook: FAMILY, OP, MODE, PARAMS, OUT (a rehearsal also sets REFERENCE and ARCHIVE);
# for HOSTOPS02 also GATES (the dispatch gates file) whenever the sheet lists dispatch gates (blocks 6 and 9 stop without it).
# RESUME_GATE is no longer read: block 9 runs check --step resume for every HOSTOPS02 set.
GATES=""; RESUME_GATE=""
if [[ -f "${RUN}/run.env" ]]; then source "${RUN}/run.env"; ATTEMPT="${OUT}/.dispatch-root/${L}-once"; fi
# The only answer that is a signature. A rehearsal has no owner and no answer: its marker is what the binder accepts there.
if [[ "${MODE}" == rehearsal ]]; then ANSWER_WORD=REHEARSAL_NO_OWNER_ANSWER; else ANSWER_WORD=Assino; fi
return 0
