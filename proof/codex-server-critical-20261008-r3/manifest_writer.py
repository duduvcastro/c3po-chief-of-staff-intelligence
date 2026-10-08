"""New K12 V2-store consumer and manifest writer. Not the historical DB writer.

Only already retained, individually pinned causal bar bodies are read. This
program does not query a provider/DB or fabricate missing data. The fixed new
image/argv/config/source must be elected and proven before a real launch.
"""
from datetime import date
import math
from common import PinnedDirectory,canonical,context,digest,fields,need,sha,strict
from families import ManifestStore
from k12 import WRITER_SCHEMA


def publish(config,capacity_store,bar_store,*,recheck):
    fields(config,('schema','context','capacity_request_raw','capacity_day_sha256','selected_sha256','through_session',
                   'bars','capacity_config_sha256','producer_sha256'),'WRITER_CONFIG_FIELDS')
    need(config['schema']=='SERVER_K12_WRITER_CONFIG_V2','WRITER_NEW_MODEL');ctx=context(config['context'])
    sha(config['producer_sha256']);sha(config['capacity_config_sha256'])
    day_raw=capacity_store.read('CAPACITY_DAY.json',pin=config['capacity_day_sha256'],modes=(0o600,0o400))
    selected_raw=capacity_store.read('CAPACITY_SELECTED.private.json',pin=config['selected_sha256'],modes=(0o600,0o400))
    cap_raw=config['capacity_request_raw'].encode();cap=strict(cap_raw)
    need(canonical(cap)==cap_raw and cap['context']==ctx and cap['capacity_config_sha256']==config['capacity_config_sha256'],
         'WRITER_CAPACITY_REQUEST')
    selected,day=strict(selected_raw),strict(day_raw)
    need(day['status']==day['documentary_authority']=='VERIFIED' and day['capacity_gate_verified'] is True
         and selected['context']==day['context'] and all(day['context'][k]==ctx[k] for k in ('model','epoch','session','release_sha256')),
         'WRITER_CAPACITY_GATE')
    symbols=selected['open_preserved']+selected['new_admitted']
    need(len(set(symbols))==len(symbols)<=550 and symbols and set(config['bars'])==set(symbols),'WRITER_SELECTED_SYMBOLS')
    through=date.fromisoformat(config['through_session']);need(through<date.fromisoformat(ctx['session']),'WRITER_NO_FUTURE_BARS')
    manifest={'schema':'SERVER_K12_MANIFEST_V2','context':ctx,'capacity_day_sha256':digest(day_raw),
              'selected_sha256':digest(selected_raw),'capacity_request_sha256':digest(cap_raw),'through_session':through.isoformat(),
              'symbols':symbols,'inputs':config['bars'],'checks':{'capacity_verified':True,'exact_symbols':True,'actual_bodies':True},
              'producer_sha256':config['producer_sha256']}
    # Validate all input bodies before the irreversible private publication.
    name='manifest-'+ctx['session']+'.json';need(not bar_store.exists(name),'WRITER_ALREADY_PUBLISHED')
    for symbol,ref in config['bars'].items():
        fields(ref,('name','sha256'),'WRITER_INPUT_FIELDS')
        raw=bar_store.read(ref['name'],pin=sha(ref['sha256']),modes=(0o400,0o600));value=strict(raw)
        need(value['schema']=='SERVER_CAUSAL_BAR_INPUT_V2' and value['context']==ctx and value['symbol']==symbol
             and value['through_session']==through.isoformat() and value['status']=='VERIFIED','WRITER_BAR_BINDING')
        need(type(value['bars']) is list and value['bars'],'WRITER_BARS_EMPTY');previous=None
        for bar in value['bars']:
            fields(bar,('session','open','high','low','close','volume'),'WRITER_BAR_FIELDS')
            day=date.fromisoformat(bar['session']);need(previous is None or day>previous,'WRITER_BAR_ORDER');previous=day
            need(all(type(bar[k]) in (int,float) and math.isfinite(bar[k]) and bar[k]>0 for k in ('open','high','low','close'))
                 and type(bar['volume']) in (int,float) and math.isfinite(bar['volume']) and bar['volume']>=0
                 and bar['low']<=min(bar['open'],bar['close'])<=max(bar['open'],bar['close'])<=bar['high'],'WRITER_BAR_VALUES')
        need(previous==through,'WRITER_LAST_SESSION')
    recheck();bar_store.create(name,canonical(manifest));recheck()
    line={'schema':WRITER_SCHEMA,'status':'PUBLISHED_VERIFIED','code':None,'session':ctx['session'],'epoch':ctx['epoch'],
          'release_sha256':ctx['release_sha256'],'mode':'PUBLISH','capacity_config_sha256':config['capacity_config_sha256'],
          'manifest_sha256':digest(canonical(manifest)),'symbol_count':len(symbols),'prepare_status':'PRECOMMITTED'}
    # Independent consumer re-reads every original. No flag-only promotion.
    ManifestStore(bar_store,capacity_store).verify({'context':ctx},cap,line)
    return canonical(line)
