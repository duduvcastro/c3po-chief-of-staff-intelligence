"""Finite read-only authority observer for a separately elected control feed.

It cannot manufacture absence of veto/deploy/concurrent work. The complete
control-feed original must be independently produced, fresh and reviewed. An
absent, stale or malformed feed is HOLD; observation never activates a unit.
"""
from datetime import timedelta
from common import canonical,context,digest,fields,instant,need,sha,strict
from runtime import physical


class Observer:
    def __init__(self,guard,control_store,entry,*,clock):
        self.guard,self.control_store,self.entry,self.clock=guard,control_store,entry,clock

    def observe(self):
        self.guard.recheck();e=self.entry;now=instant(self.clock())
        raw=self.control_store.read(e['feed_name'],modes=(0o400,0o600));original=strict(raw)
        fields(original,('schema','mode','producer_sha256','runtime_sha256','review_sha256',
               'authority_sha256','view','complete'),'GLOBAL_CONTROL_ORIGINAL_FIELDS')
        need(original['schema']=='SERVER_GLOBAL_CONTROL_ORIGINAL_V2' and original['complete'] is True
             and original['mode']==self.guard.mode and original['producer_sha256']==sha(e['feed_producer_sha256'])
             and original['runtime_sha256']==sha(e['feed_runtime_sha256'])
             and original['review_sha256']==sha(e['feed_review_sha256'])
             and original['authority_sha256']==sha(e['feed_authority_sha256']),'GLOBAL_CONTROL_NOT_ELECTED')
        v=original['view'];fields(v,('schema','context','veto','revoked_shas','concurrent_attempts',
                   'deploy_in_progress','release_sha256','observed_UTC','valid_until_UTC'),'GLOBAL_CONTROL_VIEW_FIELDS')
        need(v['schema']=='SERVER_AUTHORITY_VIEW_V2' and context(v['context'])==self.guard.context
             and type(v['veto']) is bool and type(v['deploy_in_progress']) is bool
             and type(v['revoked_shas']) is list and all(sha(x) for x in v['revoked_shas'])
             and type(v['concurrent_attempts']) is list and all(sha(x) for x in v['concurrent_attempts']),
             'GLOBAL_CONTROL_VIEW_INVALID')
        began,end=instant(v['observed_UTC']),instant(v['valid_until_UTC'])
        need(began<=now<end and (now-began).total_seconds()<=5 and 0<(end-began).total_seconds()<=10,
             'GLOBAL_CONTROL_STALE')
        release,_=physical(e['release_path']);actual=strict(release)
        need(actual['context']==self.guard.context and actual['release_sha256']==v['release_sha256']
             ==self.guard.context['release_sha256'] and digest(release)==sha(e['release_document_sha256']),
             'GLOBAL_CONTROL_RELEASE_DIVERGED')
        # Keep the upstream expiry. Exporting an old view never refreshes it.
        record={'schema':'SERVER_AUTHORITY_OBSERVER_ORIGINAL_V2','producer_sha256':sha(e['producer_sha256']),
                'observer_runtime_sha256':self.guard.value['measurement_sha256'],
                'observer_review_sha256':sha(e['review_sha256']),'view':v}
        self.guard.recheck();return canonical(record)
