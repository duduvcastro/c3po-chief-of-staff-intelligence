"""Offline composite event port. Worker activation is not wired here."""
from datetime import timedelta
from hashlib import sha256
import re
from zoneinfo import ZoneInfo
from typing import Any, cast
from .r2d2_v2_sources import SourceUnavailable, _require, _time, canonical


class CompositeEventSource:
    minute_bar_enabled = True
    MAX_PROOFS = 16384
    MAX_PENDING_RAW = 1024
    MAX_RAW_SCOPES = 8192
    MAX_BARRIER_BYTES = 1_900_000
    MAX_CURSOR_BYTES = 2_000_000
    # Keep room for one 550-name missing-minute round while BAR ingestion is
    # paused. This is headroom inside the existing limits, not a larger cap.
    GAP_HEADROOM_BYTES = 400_000

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
            scoped=hasattr(self.quote_trade,'prepare_scoped_events')
            version=3 if scoped else 2
            if not cursor:
                cursors={'quote_trade':{},'massive':{}}
            elif set(cursor)=={'version','quote_trade','massive','barrier'} and type(cursor['version']) is int and cursor['version']==version:
                cursors=cursor
            else:
                raise SourceUnavailable('COMPOSITE_CURSOR_MIGRATION_REQUIRED')
            barrier: dict[str, Any] = cursors.get('barrier', {'resolved': {}, 'sequence': 0})
            extended={'resolved','sequence','pending_raw','read_cursor','scope_sequences'}
            _require(type(barrier) is dict and set(barrier) in ({'resolved','sequence'},extended)
                and type(barrier['resolved']) is dict and len(barrier['resolved'])<=self.MAX_PROOFS
                and type(barrier['sequence']) is int and barrier['sequence']>=0,'COMPOSITE_BARRIER_CURSOR')
            barrier=cast(dict[str, Any],barrier)
            _require(len(canonical(cursor)) <= 2_000_000, 'COMPOSITE_CURSOR_LIMIT')
            pending_raw=dict(barrier.get('pending_raw',{}))
            scope_sequences=dict(barrier.get('scope_sequences',{}))
            read_cursor=barrier.get('read_cursor',cursors['quote_trade'])
            if scoped:
                _require(not cursor or set(barrier)==extended,'COMPOSITE_SCOPED_CURSOR')
                self._validate_scoped(barrier,retained=cursors['quote_trade'])
                replay=self.quote_trade.replay_references(now,pending_raw) if pending_raw else []
            else:
                _require(set(barrier)=={'resolved','sequence'},'COMPOSITE_CURSOR')
                replay=[]
            raw_reader=self.quote_trade.prepare_scoped_events if scoped else self.quote_trade.prepare_events
            def raw_prepare(*args,**kwargs):
                page=raw_reader(*args,**kwargs)
                if scoped and not page['diagnostics']:
                    prospective=dict(scope_sequences)
                    for item in page['events']:
                        if item['event_id'] in page.get('raw_references',{}):
                            scope=item['instrument_key']+'|'+item['session']+'|'+item['source_id']
                            prospective[scope]=prospective.get(scope,0)+1
                    # Reserve only evidence actually retained, not the maximum
                    # possible pending payload. The finalized proposal is checked
                    # again with its exact newly-held references below.
                    page['_scoped_reserve']=2+len(canonical({'read_cursor':page['cursor'],
                        'scope_sequences':prospective,'pending_raw':pending_raw}))
                return page
            for key, value in cast(dict[str, dict[str, Any]], barrier['resolved']).items():
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
            pages={'quote_trade':raw_prepare(now,read_cursor,snapshot=snapshot['quote_trade'] if snapshot else None,read_clock=read_clock),
                'massive':self.massive.prepare_events(now,cursors['massive'],snapshot=snapshot['massive'] if snapshot else None,read_clock=read_clock)}
            diagnostics=[d for p in pages.values() for d in p['diagnostics']]
            if diagnostics:
                return dict(events=[],diagnostics=diagnostics,cursor=cursor)
            frozen={name:p['snapshot'] for name,p in pages.items()}
            # Preserve the untrimmed raw frontier: a horizon-held page is not
            # evidence that the raw backlog has reached the current clock.
            raw_page=pages['quote_trade']
            oldest=min([_time(e['available_at']) for e in replay+raw_page['events']] or [now])
            resolved={key:value for key,value in cast(dict[str, Any],barrier['resolved']).items()
                if (not raw_page['events'] and raw_page.get('has_more'))
                or oldest-_time(value['end_at']) <= timedelta(minutes=2)}
            staged=self._extend(resolved,pages['massive']['events'])
            if not self._fits(staged,pages,barrier['sequence'],ingest=True):
                # A large raw file cursor can leave less than one full BAR
                # page of room even with no cached proofs. Ask the immutable
                # child for the largest bounded prefix that fits; never skip
                # receipts or acknowledge the discarded read-ahead suffix.
                unread=pages['massive']['events']
                low=0;high=len(unread)+1
                # Most throttled polls cannot admit even one proof. Avoid
                # repeatedly searching the entire already-verified page.
                if unread and not self._fits(self._extend(resolved,unread[:1]),pages,
                                              barrier['sequence'],ingest=True):
                    high=1
                while high-low>1:
                    middle=(low+high)//2
                    prefix=unread[:middle]
                    if self._fits(self._extend(resolved,prefix),pages,barrier['sequence'],ingest=True):
                        low=middle
                    else:
                        high=middle
                if low>0:
                    limited=self.massive.prepare_events(now,cursors['massive'],snapshot=frozen['massive'],
                        read_clock=read_clock,event_limit=low)
                    if limited['diagnostics']:
                        return dict(events=[],diagnostics=limited['diagnostics'],cursor=cursor)
                    pages['massive']=limited
                    staged=self._extend(resolved,limited['events'])
            massive_paused=not self._fits(staged,pages,barrier['sequence'],ingest=True)
            if massive_paused:
                # Keep the BAR cursor at its durable ACK and consume the raw
                # backlog using proofs already committed. The next BAR page
                # remains in the journal and is offered again after space frees.
                unread=pages['massive']['events']
                horizon=(min(_time(e['available_at']) for e in unread)-timedelta(microseconds=1)
                         if unread else None)
                # Unoffered suffix receipts can precede this page after a wall
                # clock rollback. Pausing may narrow, never advance, that proof.
                child_horizon=pages['massive'].get('page',{}).get('cutoff_received_at')
                if child_horizon is not None:
                    child_horizon=_time(child_horizon)
                    horizon=min(horizon,child_horizon) if horizon is not None else child_horizon
                pages['massive']={**pages['massive'],'events':[],'raw_receipts':{},
                    'cursor':cursors['massive'],'has_more':bool(unread) or pages['massive'].get('has_more',False),
                    'page':{'cutoff_received_at':horizon.isoformat() if horizon is not None else None}}
            else:
                resolved=staged
            # Read the BAR feed independently: a later BAR receipt may be the
            # very evidence needed to unblock an earlier raw page.
            massive_page=pages['massive']
            if massive_page.get('has_more'):
                cutoff=massive_page.get('page',{}).get('cutoff_received_at')
                _require(cutoff is not None,'COMPOSITE_HORIZON_MISSING')
                pages['quote_trade']=raw_prepare(now,read_cursor,
                    snapshot=frozen['quote_trade'],read_clock=read_clock,receipt_cutoff=_time(cutoff))
                if pages['quote_trade']['diagnostics']:
                    return dict(events=[],diagnostics=pages['quote_trade']['diagnostics'],cursor=cursor)
            # Raw receipts stay at their child cursor until a BAR or explicit
            # gap resolves the preceding minute. No private tick is buffered
            # outside its immutable source, and retention sees the held cursor.
            sequence=cast(int,barrier['sequence']); gaps=[]; cutoff=None
            blocked=set(); blocked_scopes=set()
            raw_events=replay+pages['quote_trade']['events']
            if scoped:
                # Original physical source order is authoritative even when
                # receipt clocks tie/regress or JSON object keys are reordered.
                raw_events.sort(key=lambda e:(e['source_id'],e['sequence'],e['event_id']))
            references={**pending_raw,**pages['quote_trade'].get('raw_references',{})}
            ordered=raw_events if scoped else sorted(raw_events,key=lambda e:(_time(e['available_at']),e['sequence']))
            for event in ordered:
                if event['type'] not in {'TRADE','QUOTE'} or event.get('regular') is not True:
                    continue
                event_scope=(event['instrument_key'],event['session'])
                if scoped and event_scope in blocked_scopes and event['event_id'] in references:
                    blocked.add(event['event_id']);continue
                receipt=_time(event['available_at'])
                end=receipt.replace(second=0,microsecond=0)
                start=end-timedelta(minutes=1)
                # The regular session's first minute has no predecessor BAR.
                if start.astimezone(ZoneInfo('America/New_York')).time().isoformat()<'09:30:00':
                    continue
                key=self._key(event,start.isoformat())
                if key in resolved:
                    continue
                verified_horizon=pages['massive'].get('page',{}).get('cutoff_received_at')
                deadline_passed=(not pages['massive'].get('has_more') or verified_horizon is not None
                    and _time(verified_horizon)>=end+timedelta(seconds=90))
                if now-end>timedelta(seconds=90) and deadline_passed:
                    gap={'event_id':'composite-gap:'+sha256(key.encode()).hexdigest(),
                        'source_id':'composite-barrier-v2','sequence':sequence,'type':'DATA_GAP',
                        'instrument_key':event['instrument_key'],'session':event['session'],
                        'at':start.isoformat(),'available_at':now.isoformat(),
                        'reason':'BAR_WAIT_TIMEOUT','source_at':start.isoformat()}
                    gap['envelope_sha256']=sha256(canonical(gap)).hexdigest()
                    proof=self._proof(gap,end.isoformat())
                    if not self._fits({**resolved,key:proof},pages,sequence+1):
                        if scoped and event['event_id'] in references:
                            blocked.add(event['event_id']);blocked_scopes.add(event_scope);continue
                        cutoff=receipt-timedelta(microseconds=1)
                        break
                    gaps.append(gap);sequence+=1;resolved[key]=proof
                else:
                    if scoped and event['event_id'] in references:
                        blocked.add(event['event_id']);blocked_scopes.add(event_scope);continue
                    cutoff=receipt-timedelta(microseconds=1)
                    break
            held=cutoff is not None
            if held:
                pages['quote_trade']=raw_prepare(now,read_cursor,
                    snapshot=frozen['quote_trade'],read_clock=read_clock,receipt_cutoff=cutoff)
                if pages['quote_trade']['diagnostics']:
                    return dict(events=[],diagnostics=pages['quote_trade']['diagnostics'],cursor=cursor)
            extra={}
            if scoped:
                # A blocked symbol retains exact immutable byte locators while
                # other symbols commit independently. The visible child cursor
                # remains the minimum retained position, not the read-ahead ACK.
                _require(not held,'COMPOSITE_UNSCOPED_RAW_EVENT')
                if len(blocked)>self.MAX_PENDING_RAW or len(canonical({i:references[i] for i in blocked}))>600_000:
                    # Finite memory: retain the prior durable raw read position
                    # and retry after BAR/GAP evidence resolves this bounded page.
                    # Resource pressure is not missing market evidence.
                    pages['quote_trade']={**pages['quote_trade'],'events':[], 'cursor':read_cursor,
                        'raw_receipts':{},'skipped_receipts':[],'has_more':False}
                    raw_events=sorted(replay,key=lambda e:(e['source_id'],e['sequence'],e['event_id']))
                    blocked.intersection_update(pending_raw)
                pending_raw={identity:references[identity] for identity in blocked}
                delivered=[]
                for event in raw_events:
                    if event['event_id'] in blocked:continue
                    if event['event_id'] not in references:
                        delivered.append(event);continue
                    scope=event['instrument_key']+'|'+event['session']+'|'+event['source_id']
                    seq=scope_sequences.get(scope,0)
                    scoped_event=self.quote_trade.scoped_event(event,scope,seq)
                    scope_sequences[scope]=seq+1
                    delivered.append(scoped_event)
                _require(len(scope_sequences)<=self.MAX_RAW_SCOPES,'COMPOSITE_RAW_SCOPE_LIMIT')
                next_read=pages['quote_trade']['cursor']
                retained={'files':{name:dict(saved) for name,saved in next_read.get('files',{}).items()}}
                for ref in pending_raw.values():
                    saved=retained['files'][ref['path']]
                    if ref['offset']<saved['offset']:
                        retained['files'][ref['path']]={key:ref[key] for key in
                            ('offset','sequence','device','inode','witness','received_max')}
                pages['quote_trade']={**pages['quote_trade'],'events':delivered,'cursor':retained,
                    'raw_receipts':{e['event_id']:e['envelope_sha256'] for e in delivered
                                    if e['event_id'] in references}}
                extra={'pending_raw':pending_raw,'read_cursor':next_read,'scope_sequences':scope_sequences}
                pages['quote_trade']['_scoped_reserve']=2+len(canonical(extra))
            _require(len(resolved)<=self.MAX_PROOFS,'COMPOSITE_BARRIER_LIMIT')
            events=gaps+[e for p in pages.values() for e in p['events']]
            ids=[e['event_id'] for e in events]
            _require(len(ids)==len(set(ids)),'COMPOSITE_ID_COLLISION')
            _require(self._fits(resolved,pages,sequence),
                'COMPOSITE_CURSOR_CAPACITY' if scoped else 'COMPOSITE_BARRIER_BYTE_LIMIT')
            receipts={k:v for p in pages.values() for k,v in p.get('raw_receipts',{}).items()}
            receipts.update({e['event_id']:e['envelope_sha256'] for e in gaps})
            proposed={'version':version,**{n:p['cursor'] for n,p in pages.items()},
                'barrier':{'resolved':resolved,'sequence':sequence,**extra}}
            _require(len(canonical(proposed))<=self.MAX_CURSOR_BYTES,'COMPOSITE_CURSOR_LIMIT')
            if scoped:
                self._validate_scoped(proposed['barrier'],retained=proposed['quote_trade'])
                _require(not (massive_paused and pages['massive'].get('has_more') and proposed==cursor),
                    'COMPOSITE_CURSOR_CAPACITY')
            return dict(events=events,diagnostics=[],cursor=proposed,
                raw_receipts=receipts,skipped_receipts=[r for p in pages.values() for r in p.get('skipped_receipts',[])],
                snapshot=frozen,has_more=pages['massive'].get('has_more',False) or
                    (not held and pages['quote_trade'].get('has_more',False)))
        except SourceUnavailable as error:
            code='COMPOSITE_CURSOR_CAPACITY' if str(error)=='COMPOSITE_CURSOR_CAPACITY' else 'COMPOSITE_SOURCE_UNVERIFIED'
            return dict(events=[],diagnostics=[{'code':code}],cursor=cursor)
        except (OSError,ValueError,TypeError,KeyError,OverflowError):
            return dict(events=[],diagnostics=[{'code':'COMPOSITE_SOURCE_UNVERIFIED'}],cursor=cursor)

    def _fits(self,resolved,pages,sequence,*,ingest=False):
        proposed={'version':2,**{name:page['cursor'] for name,page in pages.items()},
                  'barrier':{'resolved':resolved,'sequence':sequence}}
        reserve=pages.get('quote_trade',{}).get('_scoped_reserve',0)
        headroom=self.GAP_HEADROOM_BYTES if ingest else 0
        if ingest and reserve:
            fixed={**proposed,'barrier':{'resolved':{},'sequence':sequence}}
            available=max(0,self.MAX_CURSOR_BYTES-reserve-len(canonical(fixed)))
            # Preserve gap room proportionate to the remaining budget. A large
            # physical file inventory must not consume a fixed fictitious reserve
            # that prevents even one otherwise fitting BAR from being admitted.
            headroom=min(headroom,available//4)
        if len(resolved)>self.MAX_PROOFS or len(canonical(resolved))>self.MAX_BARRIER_BYTES-headroom:
            return False
        return len(canonical(proposed))<=self.MAX_CURSOR_BYTES-headroom-reserve

    def _extend(self,resolved,events):
        result=dict(resolved)
        for event in events:
            if event['type']=='BAR' and event.get('coverage_complete') is True:
                result[self._key(event,event['at'])]=self._proof(event,event['end_at'])
            elif event['type']=='DATA_GAP':
                start=_time(event['at']).replace(second=0,microsecond=0)
                result[self._key(event,start.isoformat())]=self._proof(event,(start+timedelta(minutes=1)).isoformat())
        return result

    @staticmethod
    def _proof(event,end):
        return {'end_at':end,'event_id':event['event_id'],'envelope_sha256':event['envelope_sha256']}

    @staticmethod
    def _key(event, start):
        return event['instrument_key']+'|'+event['session']+'|'+_time(start).isoformat()

    @classmethod
    def _validate_scoped(cls, barrier: dict[str, Any], *, retained: Any=None):
        from .r2d2_v2_raw_source import SpoolShadowSource
        if set(barrier)=={'resolved','sequence'}:
            return
        pending=barrier['pending_raw'];scopes=barrier['scope_sequences']
        _require(type(pending) is dict and len(pending)<=cls.MAX_PENDING_RAW
            and type(scopes) is dict and len(scopes)<=cls.MAX_RAW_SCOPES
            and type(barrier['read_cursor']) is dict and set(barrier['read_cursor'])<={'files'},
            'COMPOSITE_SCOPED_CURSOR')
        pending=cast(dict[str, dict[str, Any]],pending)
        scopes=cast(dict[str, int],scopes)
        for identity,ref in pending.items():SpoolShadowSource.validate_reference(identity,ref)
        for scope,sequence in cast(dict[str, Any],scopes).items():
            _require(type(scope) is str and len(scope)<=256
                and re.fullmatch(r'US:[A-Z0-9._-]+\|\d{4}-\d{2}-\d{2}\|raw-[0-9a-f]{64}',scope) is not None
                and type(sequence) is int and sequence>=0,'COMPOSITE_SCOPED_SEQUENCE')

        files=barrier['read_cursor'].get('files',{})
        _require(type(files) is dict and len(files)<=4096,'COMPOSITE_SCOPED_FILES')
        totals={}
        for scope,sequence in scopes.items():
            source=scope.rsplit('|',1)[1];totals[source]=totals.get(source,0)+sequence
        expected={'files':{}}
        for path,saved in cast(dict[str, dict[str, Any]],files).items():
            _require(type(path) is str and re.fullmatch(r'session_date=\d{4}-\d{2}-\d{2}/feed=(quote|trade)-part-\d{5,}\.ndjson',path) is not None
                and type(saved) is dict and set(saved)=={'offset','sequence','device','inode','witness','received_max'}
                and all(type(saved[k]) is int and cast(int,saved[k])>=0 for k in ('offset','sequence','device','inode'))
                and type(saved['witness']) is str and re.fullmatch(r'[0-9a-f]{64}',saved['witness']) is not None,
                'COMPOSITE_SCOPED_FILES')
            saved=cast(dict[str, Any],saved)
            if saved['received_max'] is not None:_time(saved['received_max'])
            expected['files'][path]=dict(saved)
            refs=[ref for ref in pending.values() if ref['path']==path]
            source='raw-'+sha256(path.encode()).hexdigest()
            _require(saved['sequence']==totals.pop(source,0)+len(refs),'COMPOSITE_SCOPED_ACCOUNTING')
            _require(len({ref['sequence'] for ref in refs})==len(refs),'COMPOSITE_SCOPED_ACCOUNTING')
            for ref in refs:
                _require(ref['offset']+ref['bytes']<=saved['offset'] and ref['sequence']<saved['sequence']
                    and (ref['device'],ref['inode'])==(saved['device'],saved['inode']),'COMPOSITE_SCOPED_REFERENCE_RANGE')
                if ref['offset']<expected['files'][path]['offset']:
                    expected['files'][path]={k:ref[k] for k in ('offset','sequence','device','inode','witness','received_max')}
        _require(not totals and all(ref['path'] in files for ref in pending.values()),'COMPOSITE_SCOPED_ACCOUNTING')
        if retained is not None:
            _require(retained==expected or retained=={} and expected=={'files':{}},'COMPOSITE_RETENTION_FLOOR')
