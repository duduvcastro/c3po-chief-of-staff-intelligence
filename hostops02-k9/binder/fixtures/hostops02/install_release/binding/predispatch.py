"""Offline, on Monday, before M1 (or the spare M1') is prepared and again before it is resumed: would the host refuse it?

  python3 -B binding/predispatch.py --step prepare|resume --role primary|spare
        --request <bound REQUEST of M1 or M1'> --evidence <the OP_PRECHECK receipt the request names>
        --m0-request <bound REQUEST of M0> --m0-receipt <M0's stdout.private.json> --m0-exit <M0's exit.json>
        [--primary-go <bound GO of M1> --claim-root <the dispatch root of M1>]        (role spare: both required)

Why this exists. By the signed order a refused install_release ends the epoch; a request that is never dispatched does
not. Every refusal of K10's host precheck except the clock depends on state that can change after Sunday and that the
Monday snapshot M0 (the W1 read, 05:00) observes 27 minutes before M1. The dispatcher looks at none of it: boot,
parents, pin, destination and free space are only looked at on the host, after the claim and the SSH spawn. The spare
carries the same rows and the same boot, so it is no hedge against any of these states. This tool reads M0's receipt
and answers DISPATCH_ALLOWED only when nothing in it predicts a refusal; on DO_NOT_DISPATCH neither M1 nor M1' is
prepared, and the way out is a new OP_PRECHECK receipt, a new binding and a new owner signature (CONTRACT section 6).

What each check predicts (the code K10 would answer on the host) is in the output, with true or false and nothing
else: no row, no device or inode number, no name of the host is printed. What M0 cannot show is listed as not_covered.
The M0 request must name the destination among its release directory candidates: W1 emits no name, only the answer
for a candidate the request signs. A check that cannot be evaluated (a missing or reduced section) is false.

One JSON object on standard output. Exit 0 DISPATCH_ALLOWED, 1 DO_NOT_DISPATCH, 2 usage or an unreadable input.
Nothing is written, nothing is contacted. The clock is this machine's (the one the dispatcher also uses)."""
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'build'/'install_release.py'
OPTIONS=('--step','--role','--request','--evidence','--m0-request','--m0-receipt','--m0-exit','--primary-go','--claim-root')
REQUIRED=OPTIONS[:7]
M0_RECEIPT_SCHEMA='READONLY_W1PREFLIGHT01_RECEIPT_V1'
# The W1 source whose receipt this tool reads and was tested with (tests/fixtures/M0_FIXTURE.W1_EMULATION.json): the bytes
# dispatched as W1 on 2026-10-02. A snapshot taken with other bytes may have another shape; it is not read as an answer.
M0_PAYLOAD_SHA256='7d1df28da31d3f3bd6c9dab7d9de3a98bef8291730a2bed7c28e8b1f1fa979f8'
EVIDENCE_RECEIPT_SCHEMA='READONLY_HOSTOPS_PRECHECK_RECEIPT_V1'
HARD_LINK_FILESYSTEMS=('ext4','ext3','xfs','btrfs')        # what W1 names of the local filesystems that have hard links
BOOT_MARGIN_SECONDS=60               # the boot of M0 began at least this long before the evidence was taken
CLOCK_SKEW_SECONDS=30                # the host's clock against this machine's, measured at the end of M0
M0_MAX_AGE_SECONDS=3600              # an older snapshot says nothing about now
RESUME_AFTER_SECONDS=120             # resume no earlier than not_before plus this, by this machine's clock
WATCHDOG_SECONDS=80                  # the dispatcher's latest start is not_after minus this
FREE_BYTES_FACTOR=16                 # the floor of the source times this, so that other writers do not reach it by 05:27
FREE_INODES_FLOOR=1024               # the run needs two; the inode table of an ext filesystem is fixed at mkfs
LIMIT=4*1024*1024
NOT_COVERED=('the boot identifier itself: the same boot is inferred from M0 running a boot that began before the evidence was taken',
             'whatever changes on the host between M0 and the dispatch',
             'the clock of the host at the instant of the dispatch: it was measured at the end of M0 only',
             'group inheritance or a default ACL on the volume root: the owner of the pin is the only witness',
             'the latency of fsync on the data volume at that minute',
             'that the mount of the worker still has the data volume as its source (K11 and K6a read it)')

def sha(raw):return hashlib.sha256(raw).hexdigest()

def load_source(path=SOURCE):
    """The assembled source as a private module object. It has no action on import."""
    raw=Path(path).read_bytes();name='_hostops02_install_release_predispatch_'+sha(raw)[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled install_release.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__)
    return module,sha(raw)

def arguments_of(arguments):
    """{option: value} of a call in the exact usage, or None."""
    found={};index=0
    while index<len(arguments):
        word=arguments[index]
        if word not in OPTIONS or word in found or index+1>=len(arguments):return None
        found[word]=arguments[index+1];index+=2
    if any(name not in found for name in REQUIRED) or found['--step'] not in ('prepare','resume') or found['--role'] not in ('primary','spare'):return None
    spare=found['--role']=='spare'
    if spare!=('--primary-go' in found) or spare!=('--claim-root' in found):return None
    return found

def sealed(module,receipt):
    """True when a receipt carries the hash of its own canonical bytes (the family's metadata_sha256)."""
    body=dict(receipt);pin=body.pop('metadata_sha256',None);return module.hexpin(pin) and sha(module.canonical(body))==pin

def epoch(module,value):return module.instant(value).timestamp()

def checks_of(module,source_sha256,step,role,blobs,now,primary_claim_exists):
    """[(identifier, what K10 would answer, True or False)] in order. A check that raises is false."""
    request=module.decode(blobs['request']);evidence=module.decode(blobs['evidence'])
    m0_request=module.decode(blobs['m0-request']);m0=module.decode(blobs['m0-receipt']);m0_exit=module.decode(blobs['m0-exit'])
    out=[]
    def check(name,predicts,test):
        try:ok=test() is True
        except Exception:ok=False
        out.append((name,predicts,ok))
    plan=request.get('plan') if type(request.get('plan')) is dict else {}
    sections=m0['observation']['sections'] if type(m0.get('observation')) is dict and type(m0['observation'].get('sections')) is dict else {}
    volume=sections.get('data_volume') if type(sections.get('data_volume')) is dict else {}
    filesystem=volume.get('filesystem') if type(volume.get('filesystem')) is dict else {}
    mount=volume.get('mount') if type(volume.get('mount')) is dict else {}
    listing=volume.get('root') if type(volume.get('root')) is dict else {}
    start=lambda:epoch(module,request['not_before']);end=lambda:epoch(module,request['not_after'])
    # ---- the inputs are what they are said to be
    check('REQUEST_IS_OF_THIS_PAYLOAD','REQUEST_OR_EXECUTOR_UNBOUND',lambda:request['schema']==module.REQUEST_SCHEMA and request['operation']==module.OPERATION
          and request['status']=='BOUND' and request['payload_sha256']==source_sha256 and request['date'] in module.DATES and module.document(blobs['request'])==request)
    def plan_valid():
        module.validate_common(plan);module.validate_plan(plan);return True
    check('PLAN_IS_ONE_THE_SOURCE_ACCEPTS','the refusal of validate_plan',plan_valid)
    check('EVIDENCE_IS_THE_PRECHECK_RECEIPT_THE_REQUEST_NAMES','EVIDENCE_OPERATION_MISSING',lambda:evidence['schema']==EVIDENCE_RECEIPT_SCHEMA
          and evidence['operation']==module.PRECHECK_OPERATION and sealed(module,evidence)
          and any(item['operation']==module.PRECHECK_OPERATION and item['receipt_sha256']==evidence['metadata_sha256'] for item in request['evidence'])
          and evidence['items']['boot']['status']=='COMPLETE' and evidence['items']['boot']['boot_id_sha256']==plan['evidence_boot_id_sha256'])
    check('M0_RECEIPT_IS_SEALED_AND_OF_THE_M0_REQUEST','nothing: the snapshot itself',lambda:m0['schema']==M0_RECEIPT_SCHEMA and sealed(module,m0)
          and m0['request_sha256']==sha(blobs['m0-request']) and m0['host_binding_sha256']==request['host_binding_sha256']==m0_request['host_binding_sha256'])
    check('M0_IS_OF_THE_W1_BYTES_THIS_TOOL_READS','nothing: the snapshot itself',lambda:m0['payload_sha256']==M0_PAYLOAD_SHA256)
    check('M0_EXIT_IS_OF_THAT_RECEIPT','nothing: the snapshot itself',lambda:m0_exit['status'] in ('KNOWN_COMPLETE','KNOWN_PARTIAL')
          and m0_exit['stdout_sha256']==sha(blobs['m0-receipt']) and m0_exit['request_sha256']==sha(blobs['m0-request']))
    check('M0_SECTIONS_COMPLETE','nothing: the snapshot itself',lambda:all(item.get('status')=='COMPLETE' for item in
          (sections['runtime']['boot'],volume,filesystem,mount,listing,sections['release_directories'],sections['clock'])))
    # ---- time
    host_end=lambda:epoch(module,sections['clock']['utc_end'])
    check('M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR','nothing: the snapshot itself',lambda:module.instant(m0['observed_at']).date().isoformat()==request['date']
          and -CLOCK_SKEW_SECONDS<=now.timestamp()-host_end()<=M0_MAX_AGE_SECONDS)
    check('HOST_CLOCK_AGREES_WITH_THIS_MACHINE','OUTSIDE_GO_WINDOW',lambda:abs(epoch(module,m0_exit['finished_at'])-host_end())<=CLOCK_SKEW_SECONDS)
    latest=lambda:end()-WATCHDOG_SECONDS
    if step=='prepare':
        check('TIME_LEFT_TO_PREPARE_PUBLISH_AND_RESUME','DISPATCH_WINDOW',lambda:now.timestamp()<latest()-60 and start()+RESUME_AFTER_SECONDS<latest()-60)
    else:
        check('RESUME_NOT_BEFORE_NOT_BEFORE_PLUS_120_SECONDS','OUTSIDE_GO_WINDOW',lambda:now.timestamp()>=start()+RESUME_AFTER_SECONDS)
        check('RESUME_BEFORE_THE_LATEST_START','WINDOW_WITH_WATCHDOG',lambda:now.timestamp()<latest()-15)
    # ---- what K10 looks at on the host before the first creation, in its order
    check('EXECUTOR_IS_ROOT','EXECUTOR_IDENTITY',lambda:m0['observation']['actor']=={'uid':0,'gid':0})
    check('SAME_BOOT_AS_THE_EVIDENCE','EVIDENCE_FROM_EARLIER_BOOT',lambda:type(sections['runtime']['boot']['boot_epoch_utc']) is int
          and sections['runtime']['boot']['boot_epoch_utc']+BOOT_MARGIN_SECONDS<=epoch(module,evidence['observed_at'])<=host_end())
    def rows_equal():
        seen=volume['ancestors'];signed=plan['parent']
        return (volume['source']==module.DATA_VOLUME and len(seen)==len(signed)==3 and all(
            row['type']=='dir' and (row['path'],row['device'],row['inode'],row['uid'],row['gid'],int(row['mode_octal'],8))
            ==(want['path'],want['device'],want['inode'],want['uid'],want['gid'],want['mode']) for row,want in zip(seen,signed)))
    check('PARENT_ROWS_ARE_THE_SIGNED_ROWS','PARENT_IDENTITY_MISMATCH',rows_equal)
    check('VOLUME_IS_MOUNTED_READ_WRITE','FILESYSTEM_READ_ONLY',lambda:filesystem['read_only'] is False and mount['read_write'] is True
          and mount['mount_point_is_the_path'] is True and mount['device_equals_the_directory_device'] is True and mount['mount_point']==module.DATA_VOLUME)
    check('FILESYSTEM_HAS_HARD_LINKS','FILESYSTEM_ERROR at the link',lambda:mount['filesystem_type'] in HARD_LINK_FILESYSTEMS)
    check('PIN_IS_A_REGULAR_FILE_OF_ROOT_ROOT','MAINTENANCE_PIN_ABSENT, MAINTENANCE_PIN_NOT_A_REGULAR_FILE, MAINTENANCE_PIN_NOT_ROOT_OWNED',
          lambda:listing['pin']['exists'] is True and (listing['pin']['type'],listing['pin']['uid'],listing['pin']['gid'])==('file',0,0))
    def destination_absent():
        names=m0_request['collection']['candidates']['release_directories']
        rows=[row for row in sections['release_directories']['candidates'] if row.get('candidate_index')==names.index(module.RELEASE_DIRECTORY_NAME)]
        return names.count(module.RELEASE_DIRECTORY_NAME)==1 and len(rows)==1 and rows[0]['status']=='COMPLETE' and rows[0]['exists'] is False
    check('DESTINATION_IS_ABSENT_BY_ITS_EXACT_NAME','DESTINATION_PRESENT',destination_absent)
    check('FREE_BYTES_FAR_ABOVE_THE_FLOOR','DATA_VOLUME_FREE_SPACE_BELOW_FLOOR, FILESYSTEM_FULL',lambda:type(filesystem['f_bavail']) is int
          and type(filesystem['f_frsize']) is int and filesystem['f_bavail']*filesystem['f_frsize']>=FREE_BYTES_FACTOR*module.FREE_BYTES_FLOOR)
    check('FREE_INODES_FAR_ABOVE_TWO','FILESYSTEM_FULL at the mkdir or at the temporary',lambda:type(filesystem['f_favail']) is int and filesystem['f_favail']>=FREE_INODES_FLOOR)
    # ---- the spare is not a retry
    if role=='spare':
        primary=module.decode(blobs['primary-go'])
        check('PRIMARY_WAS_NEVER_DISPATCHED','DESTINATION_PRESENT',lambda:primary['schema']==module.GO_SCHEMA and primary['payload_sha256']==source_sha256
              and primary['request_sha256']!=sha(blobs['request']) and primary_claim_exists is False)
    return out

def read(path):
    raw=Path(path).read_bytes()
    if not 0<len(raw)<=LIMIT:raise ValueError('INPUT_SIZE')
    return raw

def main(arguments,clock=None,out=None):
    """clock and out exist for the tests of this tool; the command line never sets them."""
    out=sys.stdout if out is None else out;now=(clock or (lambda:datetime.now(timezone.utc)))()
    found=arguments_of(list(arguments))
    if found is None:
        sys.stderr.write(__doc__);return 2
    module,source_sha256=load_source();blobs={};claim=None
    try:
        for option in ('--request','--evidence','--m0-request','--m0-receipt','--m0-exit','--primary-go'):
            if option in found:blobs[option[2:]]=read(found[option])
        if found['--role']=='spare':
            root=Path(found['--claim-root'])
            if not root.is_dir():raise ValueError('CLAIM_ROOT')
            name='.go-'+sha(blobs['primary-go'])+'.claim';claim=any(item.name==name for item in root.iterdir())
        checks=checks_of(module,source_sha256,found['--step'],found['--role'],blobs,now,claim)
    except (OSError,ValueError):
        sys.stderr.write('REFUSED INPUT_UNREADABLE\n');return 2
    failed=[name for name,_,ok in checks if not ok]
    result={'schema':'HOSTOPS02_INSTALL_RELEASE_PREDISPATCH_V1','decision':'DISPATCH_ALLOWED' if not failed else 'DO_NOT_DISPATCH',
            'step':found['--step'],'role':found['--role'],'payload_sha256':source_sha256,'request_sha256':sha(blobs['request']),
            'm0_receipt_sha256':sha(blobs['m0-receipt']),'evaluated_at':now.isoformat(),'failed':failed,
            'checks':[{'id':name,'predicts':predicts,'ok':ok} for name,predicts,ok in checks],'not_covered':list(NOT_COVERED)}
    out.write(module.canonical(result).decode('ascii')+'\n')
    return 0 if not failed else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
