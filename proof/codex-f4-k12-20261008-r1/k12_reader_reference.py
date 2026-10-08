"""Exact original pure K12 reader function; no host/app import or executor."""
import base64,re
from common import Hold as Refused,need,strict as document,digest as sha
from k12 import PERSIST_SCHEMA as K12_PERSISTED_SCHEMA,PERSIST_KEYS as K12_PERSISTED_KEYS
K12_STDOUT_MAX_BYTES=16384
CONTAINER_ID=r"[0-9a-f]{64}"
def hexpin(v): return type(v) is str and bool(re.fullmatch(r"[0-9a-f]{64}",v))
def integer(v,lo=0,hi=2**63): return type(v) is int and lo<=v<=hi
def text(v,pattern): return type(v) is str and bool(re.fullmatch(pattern,v))

def k12_persisted(raw,expected):
    """The persisted writer receipt (written by k12_window PERSIST): canonical JSON with exactly K12_PERSISTED_KEYS, its
    members equal to the expected ones, and the standard output it carries equal to its own hash and size. Returns
    (document, stdout bytes). Raises Refused('PERSISTED_RECEIPT_INVALID')."""
    try:value=document(raw)
    except Refused:raise Refused('PERSISTED_RECEIPT_INVALID') from None
    need(set(value)==set(K12_PERSISTED_KEYS) and value['schema']==K12_PERSISTED_SCHEMA
         and all(value[key]==expected[key] for key in expected),'PERSISTED_RECEIPT_INVALID')
    need(type(value['stdout_b64']) is str and hexpin(value['stdout_sha256']) and integer(value['stdout_bytes'],0,K12_STDOUT_MAX_BYTES)
         and type(value['exit_code']) is int and type(value['oom_killed']) is bool and text(value['container_id'],CONTAINER_ID)
         and hexpin(value['persist_request_sha256']),'PERSISTED_RECEIPT_INVALID')
    try:stdout=base64.b64decode(value['stdout_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('PERSISTED_RECEIPT_INVALID') from None
    need(len(stdout)==value['stdout_bytes'] and sha(stdout)==value['stdout_sha256'],'PERSISTED_RECEIPT_INVALID')
    return value,stdout
