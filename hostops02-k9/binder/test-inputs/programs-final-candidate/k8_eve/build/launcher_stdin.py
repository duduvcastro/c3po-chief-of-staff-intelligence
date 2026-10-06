"""Offline deterministic final-byte builder; it never launches the payload."""
import base64
import hashlib

MAX_SOURCE=1024*1024
MAX_DOCUMENT=65536

def build(source, request, authority, go, *, expected_payload_sha256,
          expected_request_sha256, expected_authority_sha256, expected_go_sha256):
    values=(source,request,authority,go)
    if any(type(v) is not bytes for v in values) or not 0<len(source)<=MAX_SOURCE or any(not 0<len(v)<=MAX_DOCUMENT for v in values[1:]):
        raise ValueError('BUILD_SIZE')
    pins={'payload':expected_payload_sha256,'request':expected_request_sha256,
          'authority':expected_authority_sha256,'go':expected_go_sha256}
    if any(hashlib.sha256(v).hexdigest()!=pins[k] for v,k in zip(values,('payload','request','authority','go'))):
        raise ValueError('BUILD_PIN')
    encoded={k:base64.b64encode(v).decode('ascii') for k,v in zip(('source','request','authority','go'),values)}
    prefix='DATA='+repr(encoded)+'\nPINS='+repr(pins)+'\n'
    body=r'''
import base64,hashlib,json,sys,types,re
result=None
exit_code=1
try:
    raw={k:base64.b64decode(v,validate=True) for k,v in DATA.items()}
    if hashlib.sha256(raw['source']).hexdigest()!=PINS['payload']:
        raise ValueError('STDIN_SOURCE_PIN')
    for key in ('request','authority','go'):
        if hashlib.sha256(raw[key]).hexdigest()!=PINS[key]:
            raise ValueError('STDIN_DOCUMENT_PIN')
    module=types.ModuleType('_pinned_hostops')
    sys.modules[module.__name__]=module
    exec(compile(raw['source'],'<pinned-hostops>','exec'),module.__dict__)
    exit_code=3;result=module.run(raw['request'],raw['authority'],raw['go'],pins=module.Pins(**PINS),
                          payload_bytes=raw['source'])
    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)
except Exception as error:
    code=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',str(error)) else 'STDIN_EXECUTION_REFUSED'
    result={'schema':'HOSTOPS_STDIN_RESULT_V1','status':'REFUSED' if exit_code==1 else 'RUN_RAISED_STATE_UNKNOWN','code':code}
encoded=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
if len(encoded)>4*1024*1024:
    encoded=b'{"status":"REFUSED","code":"STDIN_RESULT_LIMIT"}';exit_code=1
sys.stdout.buffer.write(encoded+b'\n')
raise SystemExit(exit_code)
'''
    return (prefix+body).encode('utf-8')

if __name__=='__main__':
    raise SystemExit('REFUSED: use reviewed document pins; builder does not fetch, bind GO or launch')
