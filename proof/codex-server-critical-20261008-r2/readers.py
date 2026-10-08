"""Native receipt and current-authority readers; no status-only promotion."""
from common import canonical,context,digest,fields,instant,linked_receipt,need,sha,strict


class GateReader:
    def __init__(self,guard,results,external,channel,registry,*,external_journals=None):
        self.guard,self.results,self.external,self.channel,self.registry=guard,results,external,channel,registry
        self.external_journals=external_journals or {}
        self.rows=None

    def bind_ledger(self,rows):self.rows=rows

    def __call__(self,request):
        need(self.rows is not None,'GATE_LEDGER_NOT_LOCKED');out={}
        need(set(request['required_gates'])==set(request['gate_selectors']),'GATE_ROLE_SET')
        for role,sel in request['gate_selectors'].items():
            # The registry fixes the storage/transport and allowed producer;
            # request selectors cannot invent a file path or another publisher.
            entry=self.registry[role]
            need(sel['producer_sha256']==entry['producer_sha256'] and sel['operation']==entry['operation']
                 and sel['context']==entry['context'],'GATE_NOT_ELECTED')
            if entry['origin']=='OWN_JOURNAL':
                candidates=[]
                for row in self.rows:
                    if row['kind']=='OUTCOME' and row.get('status')==('COMPLETE' if self.guard.mode=='REAL' else 'COMPLETE_FIXTURE'):
                        raw=self.results.read(row['attempt_key']+'.receipt.json',pin=row['receipt_sha256'],modes=(0o600,))
                        receipt=strict(raw)
                        if receipt['context']==sel['context'] and receipt['operation']==sel['operation']:
                            candidates.append(raw)
                need(len(candidates)==1,'GATE_JOURNAL_NOT_UNIQUE');raw=candidates[0]
            elif entry['origin']=='EXTERNAL_ORIGINAL':
                fields(entry['reference'],('id','author_id','author_type','body_sha256'),'GATE_EXTERNAL_REFERENCE')
                original=self.channel.original(entry['reference'],self.channel.collection())
                raw=original['raw']
                # External originals must already have exact reviewed bytes.
                need('sha256' in sel and sel['sha256']==entry['reference']['body_sha256'],'GATE_EXTERNAL_NOT_PINNED')
            elif entry['origin']=='EXTERNAL_WITNESSED_JOURNAL':
                upstream,store=self.external_journals[entry['journal_id']]
                # Upstream genesis/identities/source/authority are fixed in the
                # physical acceptance. Future result hashes are selected only
                # from COMPLETE witnessed outcomes, never invented at Assino.
                need(upstream.election['context']==sel['context'] and upstream.election['mode']==self.guard.mode
                     and upstream.root.identity!=self.registry['_own_root_identity'],'GATE_UPSTREAM_ELECTION')
                candidates=[]
                with upstream.locked() as (_,rows,_):
                    for row in rows:
                        if row['kind']=='OUTCOME' and row.get('status')==('COMPLETE' if self.guard.mode=='REAL' else 'COMPLETE_FIXTURE'):
                            candidate=store.read(row['attempt_key']+'.receipt.json',pin=row['receipt_sha256'],modes=(0o600,0o400))
                            value=strict(candidate)
                            if value['context']==sel['context'] and value['operation']==sel['operation']:
                                candidates.append(candidate)
                    need(len(candidates)==1,'GATE_UPSTREAM_NOT_UNIQUE');raw=candidates[0]
            else:need(False,'GATE_ORIGIN_UNAVAILABLE')
            receipt=linked_receipt(raw,sel['context'],operation=sel['operation'])
            need(receipt['producer_sha256']==sha(sel['producer_sha256']) and receipt['mode']==self.guard.mode,'GATE_SOURCE_OR_MODE')
            if 'sha256' in sel:need(digest(raw)==sha(sel['sha256']),'GATE_DIGEST')
            out[role]=raw
        self.guard.recheck();return out


class AuthorityView:
    """Read a fresh original of the independently elected host observer.

    The observer is an explicit installation dependency, not a boolean supplied
    by an operation request. Its exported original is retained in the protected
    store and bound to its source/runtime/review, with a ten-second lifetime.
    """
    def __init__(self,guard,directory,entry,*,clock,observer=None):
        self.guard,self.directory,self.entry,self.clock=guard,directory,entry,clock
        self.observer=observer

    def __call__(self):
        raw=(self.observer.observe() if self.observer is not None else self.directory.read(self.entry['name'],modes=(0o600,0o400)))
        record=strict(raw);now=instant(self.clock())
        fields(record,('schema','producer_sha256','observer_runtime_sha256','observer_review_sha256','view'),'AUTHORITY_OBSERVER_FIELDS')
        need(record['schema']=='SERVER_AUTHORITY_OBSERVER_ORIGINAL_V2'
             and record['producer_sha256']==sha(self.entry['producer_sha256'])
             and record['observer_runtime_sha256']==sha(self.guard.value['measurement_sha256'] if self.observer is not None else self.entry['runtime_sha256'])
             and record['observer_review_sha256']==sha(self.entry['review_sha256']),'AUTHORITY_OBSERVER_NOT_ELECTED')
        view=record['view'];need(view['context']==self.guard.context and 0<=(now-instant(view['observed_UTC'])).total_seconds()<=10
                                and now<instant(view['valid_until_UTC']),'AUTHORITY_OBSERVER_STALE')
        self.guard.recheck();return view
