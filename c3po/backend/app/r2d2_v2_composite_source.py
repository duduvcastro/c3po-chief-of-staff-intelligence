"""Offline composite event port. Worker activation is not wired here."""
from .r2d2_v2_sources import SourceUnavailable, _require, _time


class CompositeEventSource:
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
            elif set(cursor)=={'version','quote_trade','massive'} and cursor['version']==1:
                cursors=cursor
            else:
                raise SourceUnavailable('COMPOSITE_CURSOR_MIGRATION_REQUIRED')
            _require(snapshot is None or type(snapshot) is dict and set(snapshot)=={'quote_trade','massive'},'COMPOSITE_SNAPSHOT')
            sources={'quote_trade':self.quote_trade,'massive':self.massive}
            pages={name:source.prepare_events(now,cursors[name],snapshot=snapshot[name] if snapshot else None,
                    read_clock=read_clock) for name,source in sources.items()}
            _require(not any(p['diagnostics'] for p in pages.values()),'COMPOSITE_CHILD_UNVERIFIED')
            horizons=[_time(p['page']['cutoff_received_at']) for p in pages.values()
                      if p.get('has_more') and p.get('page',{}).get('cutoff_received_at')]
            _require(all(not p.get('has_more') or p.get('page',{}).get('cutoff_received_at') for p in pages.values()),'COMPOSITE_HORIZON_MISSING')
            frozen={name:p['snapshot'] for name,p in pages.items()}
            if horizons:
                cutoff=min(horizons)
                pages={name:source.prepare_events(now,cursors[name],snapshot=frozen[name],
                    read_clock=read_clock,receipt_cutoff=cutoff) for name,source in sources.items()}
                _require(not any(p['diagnostics'] for p in pages.values()),'COMPOSITE_CHILD_UNVERIFIED')
                _require(all(_time(e['available_at'])<=cutoff for p in pages.values() for e in p['events']),'COMPOSITE_EVENT_BEYOND_HORIZON')
            events=[e for p in pages.values() for e in p['events']]
            ids=[e['event_id'] for e in events]
            _require(len(ids)==len(set(ids)),'COMPOSITE_ID_COLLISION')
            receipts={k:v for p in pages.values() for k,v in p.get('raw_receipts',{}).items()}
            return dict(events=events,diagnostics=[],cursor={'version':1,**{n:p['cursor'] for n,p in pages.items()}},
                raw_receipts=receipts,skipped_receipts=[r for p in pages.values() for r in p.get('skipped_receipts',[])],
                snapshot=frozen,has_more=any(p.get('has_more',False) for p in pages.values()))
        except (SourceUnavailable,OSError,ValueError,TypeError,KeyError,OverflowError):
            return dict(events=[],diagnostics=[{'code':'COMPOSITE_SOURCE_UNVERIFIED'}],cursor=cursor)
