"""Offline composite event port. Worker activation is not wired here."""
from datetime import timedelta
from hashlib import sha256
import re
from zoneinfo import ZoneInfo
from .r2d2_v2_sources import SourceUnavailable, _require, _time, canonical


class CompositeEventSource:
    minute_bar_enabled = True
    MAX_PROOFS = 16384

    def __init__(self, quote_trade, massive):
        self.quote_trade=quote_trade
        self.massive=massive

    def snapshot(self,*args,**kwargs):
        return self.quote_trade.snapshot(*args,**kwargs)

    def causal_list(self,*args,**kwargs):
        return self.quote_trade.causal_list(*args,**kwargs)

    def prepare_events(self,now,cursor,*,snapshot=None,read_clock=None):
        try:
            _require(type(cursor) is dict,'COMPOSITE_CURSOR')
            if not cursor:
                cursors={'quote_trade':{},'massive':{}}
            elif set(cursor)=={'version','quote_trade','massive','barrier'} and cursor['version']==2:
                cursors=cursor
            else:
                raise SourceUnavailable('COMPOSITE_CURSOR_MIGRATION_REQUIRED')
            barrier = cursors.get('barrier', {'resolved': {}, 'sequence': 0})
            _require(type(barrier) is dict and set(barrier)=={'resolved','sequence'}
                and type(barrier['resolved']) is dict and len(barrier['resolved'])<=self.MAX_PROOFS
                and type(barrier['sequence']) is int and barrier['sequence']>=0,'COMPOSITE_BARRIER_CURSOR')
            _require(len(canonical(cursor)) <= 2_000_000, 'COMPOSITE_CURSOR_LIMIT')
            for key, value in barrier['resolved'].items():
                _require(type(key) is str and len(key)<=200 and type(value) is dict
                    and set(value)=={'end_at','event_id','envelope_sha256'},'COMPOSITE_BARRIER_PROOF')
                parts=key.split('|')
                _require(len(parts)==3 and re.fullmatch(r'US:[A-Z0-9._-]+',parts[0]) is not None
                    and _time(parts[2]).astimezone(ZoneInfo('America/New_York')).date().isoformat()==parts[1]
                    and _time(value['end_at'])-_time(parts[2])==timedelta(minutes=1)
                    and type(value['event_id']) is str and 0<len(value['event_id'])<=256
                    and type(value['envelope_sha256']) is str
                    and re.fullmatch(r'[0-9a-f]{64}',value['envelope_sha256']) is not None,'COMPOSITE_BARRIER_PROOF')
            _require(snapshot is None or type(snapshot) is dict and set(snapshot)=={'quote_trade','massive'},'COMPOSITE_SNAPSHOT')
            sources={'quote_trade':self.quote_trade,'massive':self.massive}
            pages={name:source.prepare_events(now,cursors[name],snapshot=snapshot[name] if snapshot else None,
                    read_clock=read_clock) for name,source in sources.items()}
            diagnostics=[d for p in pages.values() for d in p['diagnostics']]
            if diagnostics:
                return dict(events=[],diagnostics=diagnostics,cursor=cursor)
            frozen={name:p['snapshot'] for name,p in pages.items()}
            # Read the BAR feed independently: a later BAR receipt may be the
            # very evidence needed to unblock an earlier raw page.
            massive_page=pages['massive']
            if massive_page.get('has_more'):
                cutoff=massive_page.get('page',{}).get('cutoff_received_at')
                _require(cutoff is not None,'COMPOSITE_HORIZON_MISSING')
                pages['quote_trade']=self.quote_trade.prepare_events(now,cursors['quote_trade'],
                    snapshot=frozen['quote_trade'],read_clock=read_clock,receipt_cutoff=_time(cutoff))
                if pages['quote_trade']['diagnostics']:
                    return dict(events=[],diagnostics=pages['quote_trade']['diagnostics'],cursor=cursor)
            # Raw receipts stay at their child cursor until a BAR or explicit
            # gap resolves the preceding minute. No private tick is buffered
            # outside its immutable source, and retention sees the held cursor.
            oldest=min([_time(e['available_at']) for e in pages['quote_trade']['events']] or [now])
            resolved={key:value for key,value in barrier['resolved'].items()
                if oldest-_time(value['end_at']) <= timedelta(minutes=2)}
            for event in pages['massive']['events']:
                if event['type']=='BAR' and event.get('coverage_complete') is True:
                    resolved[self._key(event,event['at'])]=self._proof(event,event['end_at'])
                elif event['type']=='DATA_GAP':
                    start=_time(event['at']).replace(second=0,microsecond=0)
                    resolved[self._key(event,start.isoformat())]=self._proof(event,(start+timedelta(minutes=1)).isoformat())
            sequence=barrier['sequence']; gaps=[]; cutoff=None
            for event in sorted(pages['quote_trade']['events'],key=lambda e:(_time(e['available_at']),e['sequence'])):
                if event['type'] not in {'TRADE','QUOTE'} or event.get('regular') is not True:
                    continue
                receipt=_time(event['available_at'])
                end=receipt.replace(second=0,microsecond=0)
                if receipt==end:
                    end-=timedelta(minutes=1)
                start=end-timedelta(minutes=1)
                # The regular session's first minute has no predecessor BAR.
                if start.astimezone(ZoneInfo('America/New_York')).time().isoformat()<'09:30:00':
                    continue
                key=self._key(event,start.isoformat())
                if key in resolved:
                    continue
                if now-end>=timedelta(seconds=90) and not pages['massive'].get('has_more'):
                    gap={'event_id':'composite-gap:'+sha256(key.encode()).hexdigest(),
                        'source_id':'composite-barrier-v2','sequence':sequence,'type':'DATA_GAP',
                        'instrument_key':event['instrument_key'],'session':event['session'],
                        'at':start.isoformat(),'available_at':now.isoformat(),
                        'reason':'BAR_WAIT_TIMEOUT','source_at':start.isoformat()}
                    gap['envelope_sha256']=sha256(canonical(gap)).hexdigest()
                    gaps.append(gap);sequence+=1;resolved[key]=self._proof(gap,end.isoformat())
                else:
                    cutoff=receipt-timedelta(microseconds=1)
                    break
            held=cutoff is not None
            if held:
                pages['quote_trade']=self.quote_trade.prepare_events(now,cursors['quote_trade'],
                    snapshot=frozen['quote_trade'],read_clock=read_clock,receipt_cutoff=cutoff)
                if pages['quote_trade']['diagnostics']:
                    return dict(events=[],diagnostics=pages['quote_trade']['diagnostics'],cursor=cursor)
            _require(len(resolved)<=self.MAX_PROOFS,'COMPOSITE_BARRIER_LIMIT')
            events=gaps+[e for p in pages.values() for e in p['events']]
            ids=[e['event_id'] for e in events]
            _require(len(ids)==len(set(ids)),'COMPOSITE_ID_COLLISION')
            _require(len(canonical(resolved))<=1_900_000,'COMPOSITE_BARRIER_BYTE_LIMIT')
            receipts={k:v for p in pages.values() for k,v in p.get('raw_receipts',{}).items()}
            receipts.update({e['event_id']:e['envelope_sha256'] for e in gaps})
            return dict(events=events,diagnostics=[],cursor={'version':2,**{n:p['cursor'] for n,p in pages.items()},
                    'barrier':{'resolved':resolved,'sequence':sequence}},
                raw_receipts=receipts,skipped_receipts=[r for p in pages.values() for r in p.get('skipped_receipts',[])],
                snapshot=frozen,has_more=pages['massive'].get('has_more',False) or
                    (not held and pages['quote_trade'].get('has_more',False)))
        except (SourceUnavailable,OSError,ValueError,TypeError,KeyError,OverflowError):
            return dict(events=[],diagnostics=[{'code':'COMPOSITE_SOURCE_UNVERIFIED'}],cursor=cursor)

    @staticmethod
    def _proof(event,end):
        return {'end_at':end,'event_id':event['event_id'],'envelope_sha256':event['envelope_sha256']}

    @staticmethod
    def _key(event, start):
        return event['instrument_key']+'|'+event['session']+'|'+_time(start).isoformat()
