"""Read-only assembler for original runtime/slot reviews, never an installer.

An independently reviewed physical measurement follows root preparation.
Actual REQUEST/question/owner/BOUND originals then populate finite slots. The
stable journal seed remains the prepared installation election. Final units
are generated only after this acceptance; their exact bytes require a separate
installation packet and literal owner response before any enablement.
"""
from datetime import timedelta,timezone
from common import canonical,context,digest,fields,instant,need,sha,strict
from runtime import measure
from control import OPERATIONS

BRT=timezone(timedelta(hours=-3))
ORIGINALS={'request','question','owner','bound','authority','review'}


def build(spec_raw,measurement_raw,prepared_raw,manifest_raw,definition_raw,*,channel,clock,fixture=False):
    spec,measurement,prepared,manifest,definition=map(strict,(spec_raw,measurement_raw,prepared_raw,manifest_raw,definition_raw))
    need(all(canonical(v)==raw for v,raw in zip((spec,measurement,prepared,manifest,definition),
        (spec_raw,measurement_raw,prepared_raw,manifest_raw,definition_raw))),'ACCEPTANCE_CANONICAL')
    ctx=context(spec['context']);mode=spec['mode'];now=instant(clock())
    need((fixture and mode=='FIXTURE') or (not fixture and mode=='REAL'),'ACCEPTANCE_FIXTURE_NOT_REAL')
    need(prepared['schema']=='SERVER_INSTALLATION_PREPARED_V2' and prepared['mode']==mode and prepared['context']==ctx
         and prepared['timers_installed']==0 and prepared['operational_GO'] is False,'ACCEPTANCE_PREPARATION')
    seed=prepared['journal_election']
    need(seed['schema']=='SERVER_JOURNAL_INSTALLATION_ELECTION_V2' and seed['mode']==mode
         and seed['context']==ctx and seed['installation_plan_sha256']==prepared['plan_sha256'],'ACCEPTANCE_JOURNAL_SEED')
    need(measure(spec)==measurement and measurement['mode']==mode and measurement['context']==ctx
         and instant(prepared['prepared_UTC'])<=now,'ACCEPTANCE_PHYSICAL_MEASUREMENT')
    need(set(prepared['roots'])<=set(spec['roots']) and all(prepared['roots'][role]==measurement['roots'][role][-1]['identity']
         for role in prepared['roots']),'ACCEPTANCE_PREPARED_ROOTS')
    registry_pin=sha(prepared['registry_sha256']);need(spec['files']['registry']['sha256']==registry_pin,'ACCEPTANCE_REGISTRY')
    need(spec['files']['source_manifest']['sha256']==digest(manifest_raw),'ACCEPTANCE_MANIFEST_MEASURED')
    source_pins={row['name']:sha(row['sha256']) for row in manifest['files'] if row['name'].endswith('.py')}
    need(source_pins and all(name in spec['files'] and spec['files'][name]['sha256']==pin
         for name,pin in source_pins.items()),'ACCEPTANCE_SOURCE_MEASUREMENT')
    fields(definition,('schema','mode','context','slots','runtime_review','extensions'),'ACCEPTANCE_DEFINITION_FIELDS')
    need(definition['schema']=='SERVER_RUNTIME_ELECTION_DEFINITION_V2' and definition['mode']==mode and definition['context']==ctx
         and type(definition['slots']) is dict and definition['slots'] and len(definition['slots'])<=64,'ACCEPTANCE_SLOTS')
    collection=channel.collection();slots={};operations=set();mp=digest(measurement_raw)
    for slot,elected in definition['slots'].items():
        fields(elected,('references','owner_deadline_UTC','max_lateness_seconds'),'ACCEPTANCE_SLOT_FIELDS')
        refs=elected['references'];need(set(refs)==ORIGINALS,'ACCEPTANCE_ORIGINAL_SET')
        originals={role:channel.original(ref,collection) for role,ref in refs.items()}
        request,question,owner,bound,authority,review=[originals[k]['value'] for k in
                              ('request','question','owner','bound','authority','review')]
        pins={k:digest(v['raw']) for k,v in originals.items()};operation=request['operation']
        need(request['schema']=='SERVER_FAMILY_REQUEST_V2' and context(request['context'])==ctx
             and request['authority_slot']==slot and operation in OPERATIONS,'ACCEPTANCE_REQUEST')
        start,end=instant(request['start_UTC']),instant(request['end_UTC']);signed=instant(owner['signed_at_UTC'])
        published=instant(originals['question']['created_UTC']);registered=instant(originals['owner']['created_UTC'])
        local=signed.astimezone(BRT)
        need(published<=signed<start and signed<=instant(elected['owner_deadline_UTC']) and signed<=registered
             and (registered-signed).total_seconds()<=60 and registered<=instant(originals['bound']['created_UTC'])<start
             and all(instant(v['created_UTC'])<start for v in originals.values()) and now<start
             and 7<=local.hour and (local.hour,local.minute,local.second,local.microsecond)<=(21,45,0,0), 'ACCEPTANCE_OWNER_TIME')
        need(type(request['budget_seconds']) is int and 0<request['budget_seconds']<=120
             and (end-start).total_seconds()>request['budget_seconds']
             and type(elected['max_lateness_seconds']) is int and 0<=elected['max_lateness_seconds']<=5,'ACCEPTANCE_WINDOW')
        need(question['schema']=='SERVER_OWNER_QUESTION_V2' and question['request_sha256']==pins['request']
             and owner['schema']=='SERVER_OWNER_RESPONSE_V2' and owner['request_sha256']==pins['request']
             and owner['question_sha256']==pins['question'] and owner['literal']=='Assino'
             and owner['channel']=='REGISTRO_PELA_FABLE','ACCEPTANCE_OWNER')
        need(authority['schema']=='SERVER_OPERATION_AUTHORITY_V2' and authority['context']==ctx and authority['slot']==slot
             and authority['request_sha256']==pins['request'] and authority['registry_sha256']==registry_pin
             and authority['runtime_measurement_sha256']==mp and authority['operation']==operation,'ACCEPTANCE_AUTHORITY')
        need(review['schema']=='SERVER_OPERATION_REVIEW_V2' and review['context']==ctx and review['request_sha256']==pins['request']
             and review['verdict']=='ACCEPTED_OWN_BYTES' and review['authority_sha256']==pins['authority']
             and review['source_pins']==source_pins,'ACCEPTANCE_OPERATION_REVIEW')
        need(bound['schema']=='SERVER_BOUND_V2' and bound['context']==ctx and bound['request_sha256']==pins['request']
             and bound['question_sha256']==pins['question'] and bound['owner_sha256']==pins['owner']
             and bound['review_sha256']==pins['review'] and bound['runtime_measurement_sha256']==mp
             and bound['gate_selectors_sha256']==digest(canonical(request['gate_selectors']))
             and request['pins']['runtime_measurement_sha256']==mp,'ACCEPTANCE_BOUND')
        slots[slot]=dict(elected,operation=operation,authority_sha256=pins['authority'],review_sha256=pins['review'],
             pins=request['pins'],start_UTC=request['start_UTC'],end_UTC=request['end_UTC'],budget_seconds=request['budget_seconds'])
        operations.add(operation)
    extensions=definition['extensions'];need(type(extensions) is dict and set(extensions)<= {'reader_registry','writer_registry','family_contracts'},'ACCEPTANCE_EXTENSIONS')
    if 'F4_K12_LAUNCH' in operations:need(set(extensions['family_contracts'])=={'K12_LAUNCH'},'ACCEPTANCE_K12_CONTRACT')
    if 'F5_H16_READ' in operations:need('H16_SERVER_READER_V2' in extensions['reader_registry'],'ACCEPTANCE_H16_READER')
    subject={'spec_sha256':digest(spec_raw),'measurement_sha256':mp,'prepared_sha256':digest(prepared_raw),
        'manifest_sha256':digest(manifest_raw),'slots_sha256':digest(canonical(slots)),'extensions_sha256':digest(canonical(extensions)),
        'context':ctx,'mode':mode}
    rr=channel.original(definition['runtime_review'],collection);review=rr['value']
    need(review['schema']=='SERVER_RUNTIME_REVIEW_V2' and review['subject']==subject
         and review['verdict']=='ACCEPTED_OWN_BYTES_AND_PHYSICAL_RUNTIME'
         and review['rollback_independence_verified'] is True and review['mode']==mode,'ACCEPTANCE_INDEPENDENT_RUNTIME_REVIEW')
    need(instant(rr['created_UTC'])<=now and now<min(instant(v['start_UTC']) for v in slots.values()),'ACCEPTANCE_REVIEW_TIME')
    result={'schema':'SERVER_RUNTIME_ACCEPTANCE_V2','accepted':True,'spec':spec,'measurement':measurement,
        'measurement_sha256':mp,'source_pins':source_pins,'registry_sha256':registry_pin,
        'journal_election':seed,'election':{'mode':mode,'context':ctx,'slots':slots},
        'allowed_operations':sorted(operations),'review_sha256':digest(rr['raw']),
        'installation_authority_sha256':sha(prepared['owner_original_sha256']),**extensions}
    # Re-read the physical identity after network readbacks. This produces no
    # root-controlled installation, unit activation, GO or fabricated review.
    need(measure(spec)==measurement,'ACCEPTANCE_RUNTIME_CHANGED_DURING_READBACK')
    return canonical(result)
