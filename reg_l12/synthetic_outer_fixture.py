"""SYNTHETIC fixture helper; no test methods from the closed 22 imported/run."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import os, time, tempfile, unittest
import finite_batch as c
import outer_limiter as o
import bounded_runner as inner
from synthetic_image_go_fixture import evidence as image_evidence

class Fixture:

    def __init__(self, root, bootstrap=False):
        self.root = Path(root)
        self.mark = time.monotonic()
        self.base = datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc) if bootstrap else o.now()
        self.context = (c.EPOCH, c.DAY, c.PREVIOUS, 'BOOTSTRAP' if bootstrap else 'P')
        authority = c.canonical({'fixture': 'SYNTHETIC_NOT_REAL_AUTHORITY'})
        runtime = c.canonical({'fixture': 'SYNTHETIC_NOT_RUNTIME'})
        operations = c.BOOTSTRAP if bootstrap else c.UPSTREAM
        lane = 'BOOTSTRAP_MONDAY' if bootstrap else 'UPSTREAM_P'
        deadline = self.base - timedelta(hours=1)
        prepared = self.base - timedelta(hours=6 if bootstrap else 3)
        if bootstrap:
            deadline = datetime(2026, 10, 12, 0, 45, tzinfo=timezone.utc)
        self.q = {'schema': 'L12_FINITE_BATCH_REQUEST_CANDIDATE_V1', 'lane': lane, 'epoch': c.EPOCH, 'session': c.DAY, 'previous_session': c.PREVIOUS, 'track': self.context[-1], 'prepared_at': c.iso(prepared), 'owner_deadline': c.iso(deadline), 'authority_sha256': c.sha(authority), 'runtime_sha256': c.sha(runtime), 'veto_authority_sha256': c.sha(b'SYNTHETIC_VETO_AUTH'), 'initial_receipts': {}, 'tasks': [{'operation': op, 'not_before': c.iso(self.base if bootstrap else self.base - timedelta(seconds=1)), 'not_after': c.iso(self.base + timedelta(seconds=60)), 'budget_seconds': 1.0, 'requires': list(c.MINIMUM_DEPENDENCIES[op])} for op in operations]}
        self.receipts = {'prove': self.receipt('prove', self.base - timedelta(hours=4))}
        self.gos = {}
        if bootstrap:
            self.receipts['epoch_pre'] = self.receipt('epoch_pre', prepared - timedelta(hours=1))
            self.q['initial_receipts'] = {'epoch_pre': c.sha(self.receipts['epoch_pre'].raw)}
            for t in self.q['tasks']:
                e = image_evidence(t['operation'], t)
                self.gos[t['operation']] = e
                t.update(image_go_sha256=c.sha(e.go_raw), image_proposal_sha256=c.sha(e.proposal_raw))
        request = c.canonical(self.q)
        owner = c.canonical({'schema': 'L12_OWNER_RECORD_CANDIDATE_V1', 'answer': 'Assino', 'channel': 'REGISTRO_PELA_FABLE', 'request_sha256': c.sha(request), 'question_sha256': c.sha(b'SYNTHETIC_QUESTION'), 'question_published_at': c.iso(prepared + timedelta(seconds=1)), 'signed_at': c.iso(prepared + timedelta(seconds=2))})
        docs = (('authority', authority), ('owner', owner), ('runtime', runtime))
        bound = c.canonical({'schema': 'L12_BOUND_CANDIDATE_V1', 'request_sha256': c.sha(request), 'documents_sha256': {k: c.sha(v) for (k, v) in docs}, 'bound_at': c.iso(prepared + timedelta(seconds=3))})
        self.bundle = c.Bundle(request, bound, docs)
        self.services = c.Services(authority=self.authority, identity=lambda *a: None, receipt_read=lambda role, ctx: self.receipts.get(role), receipt_verify=lambda *a: None, operation_gate=lambda *a: None, veto_read=self.veto, veto_verify=lambda *a: None, image_go_read=lambda q, t, n: self.gos[t['operation']], image_go_verify=lambda *a: None, execute=self.execute)

    def clock(self):
        return self.base + timedelta(seconds=time.monotonic() - self.mark)

    def receipt(self, role, at=None):
        at = at or self.clock()
        raw = c.canonical({'fixture': 'SYNTHETIC_NOT_OPERATIONAL_RECEIPT', 'role': role, 'at': c.iso(at)})
        return c.Receipt(raw, role, self.context, 'COMPLETE', at)

    def authority(self, b, q, t, n):
        key = c.sha(c.canonical(list(c.context(q) + (t['operation'],))))
        marker = c.strict(self.root.joinpath('consume-' + key).read_bytes())
        rows = [c.strict(line) for line in self.root.joinpath('attempts.ledger').read_bytes().splitlines()]
        c.need(marker['request_sha256'] == c.sha(b.request) and any((r['kind'] == 'CLAIM' and r['attempt_key'] == key for r in rows)), 'FIXTURE_CLAIM_NOT_PERSISTED')

    def veto(self, q, t, n):
        return c.VetoView(b'SYNTHETIC_CURRENT_VETO', q['veto_authority_sha256'], 'ALLOW', n, n + timedelta(seconds=5))

    def execute(self, call):
        with self.root.joinpath('effects.synthetic').open('ab') as s:
            s.write(b'1')
        return self.receipt(call.operation)
