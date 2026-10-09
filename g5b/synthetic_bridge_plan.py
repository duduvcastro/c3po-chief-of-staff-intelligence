"""Explicit SYNTHETIC C6 plan fixture; no authority or operational receipt."""
from datetime import datetime,timedelta,timezone
import finite_batch as c
from synthetic_gate_fixture import OPEN,CAPTURE_OPEN,CAPTURE_CLOSE
class DownFixture:
 def __init__(self):
  self.authority=c.canonical({'fixture':'SYNTHETIC_NOT_AUTHORITY'});self.runtime=c.canonical({'fixture':'SYNTHETIC_NOT_RUNTIME'})
  self.at=datetime(2026,10,12,7,tzinfo=timezone.utc);prepared=datetime(2026,10,11,18,tzinfo=timezone.utc);ctx=(c.EPOCH,c.DAY,c.PREVIOUS,'P');self.receipts={}
  for role in ('commit_result','publish_launch'):
   raw=c.canonical({'fixture':'SYNTHETIC_NOT_OPERATIONAL_RECEIPT','role':role});self.receipts[role]=c.Receipt(raw,role,ctx,'COMPLETE',prepared-timedelta(hours=1))
  windows={'reader_bound':(OPEN-timedelta(minutes=30),OPEN-timedelta(minutes=2)),
   'reader_cycle':(OPEN-timedelta(seconds=90),OPEN+timedelta(minutes=2)),
   'policy_read':(OPEN+timedelta(minutes=10),OPEN+timedelta(minutes=11)),
   'capture_launch':(OPEN+timedelta(minutes=20),CAPTURE_CLOSE+timedelta(minutes=2)),
   'capture_result':(CAPTURE_CLOSE+timedelta(minutes=24),CAPTURE_CLOSE+timedelta(minutes=29))}
  self.q={'schema':'L12_FINITE_BATCH_REQUEST_CANDIDATE_V1','lane':'DOWNSTREAM_AFTER_E6','epoch':c.EPOCH,'session':c.DAY,'previous_session':c.PREVIOUS,'track':'P',
   'prepared_at':c.iso(prepared),'owner_deadline':c.iso(prepared+timedelta(hours=1)),'authority_sha256':c.sha(self.authority),'runtime_sha256':c.sha(self.runtime),
   'veto_authority_sha256':c.sha(b'SYNTHETIC_VETO_AUTH'),'initial_receipts':{r:c.sha(x.raw) for r,x in self.receipts.items()},'tasks':[]}
  for i,op in enumerate(c.DOWNSTREAM):
   start,end=windows.get(op,(self.at+timedelta(minutes=i*2),self.at+timedelta(minutes=i*2+1)))
   self.q['tasks'].append({'operation':op,'not_before':c.iso(start),'not_after':c.iso(end),'budget_seconds':1,'requires':list(c.MINIMUM_DEPENDENCIES[op])})
  request=c.canonical(self.q);owner=c.canonical({'schema':'L12_OWNER_RECORD_CANDIDATE_V1','answer':'Assino','channel':'REGISTRO_PELA_FABLE','request_sha256':c.sha(request),
   'question_sha256':c.sha(b'SYNTHETIC_QUESTION'),'question_published_at':c.iso(prepared+timedelta(seconds=1)),'signed_at':c.iso(prepared+timedelta(seconds=2))})
  docs=(('authority',self.authority),('owner',owner),('runtime',self.runtime));bound=c.canonical({'schema':'L12_BOUND_CANDIDATE_V1','request_sha256':c.sha(request),
   'documents_sha256':{n:c.sha(x) for n,x in docs},'bound_at':c.iso(prepared+timedelta(seconds=3))});self.bundle=c.Bundle(request,bound,docs)
 def task(self,op):return next(t for t in self.q['tasks'] if t['operation']==op)
