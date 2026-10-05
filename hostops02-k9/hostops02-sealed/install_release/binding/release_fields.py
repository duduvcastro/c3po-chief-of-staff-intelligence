"""Offline, for the binder of K10: the `release` member of the plan, computed from the release file, and refused
unless the file is the release that was approved and verified for the deployed revision.

  python3 -B binding/release_fields.py <release file> --expect-sha256 <64 hex> --expect-code-revision <40 hex>
                                                      --expect-package-sha <64 hex>

The release bytes are not part of the sealed source: they are a bind-time input. The source itself judges
code_revision and implementation_package_sha by grammar only (it would install any well-formed release of this epoch,
and a release the deployed application refuses would end as a complete install that the epoch readback then rejects,
with no removal operation in the family). The precedents refused such a release before any write, as a constant of
the payload; here the refusal is made at binding, by this tool, and nothing is bound without it (CONTRACT section 6).

Three expectations are REQUIRED arguments, each taken by command from where it was established, never from the
release file itself:
  --expect-sha256          the SHA-256 of the release bytes the three hands approved and K11 PRE verified
  --expect-code-revision   the deployed revision (the build revision of the image K11 PRE ran the verification in)
  --expect-package-sha     the implementation package of that revision
Besides them, DEPLOYED below holds the revision and the package this directory was built and reviewed for. A release
cut for another revision is refused even when the arguments name it: a deploy after the seal is a new seal of this
directory (this tool and the contract), which does not move the payload hash.

The tool reads the file once (a regular file, at most the source's MAX_RELEASE_BYTES) and prints one JSON object:
  release    the plan member {path, content_b64, sha256, bytes}: the bytes embedded, their SHA-256 and size pinned
  facts      what the release says of itself, as the source's own release_facts() reads it (it enters the effects)
  expected   the three expectations that were compared, and expectations_met true
  request_bytes_added   how many bytes the member adds to the canonical request (a signed document holds 65536)
Everything is computed by the functions of the assembled source itself (build/install_release.py, loaded without any
action): a release this tool accepts is one the source's validate_plan accepts, and a refusal of the source here is
the refusal the dispatcher would raise before any claim. Nothing is written, nothing is contacted, no hash is typed.
Exit 0 with the object on standard output; exit 1 with one line "REFUSED <CODE>" on standard error; exit 2 on a
call that is not the usage above.

Refusals of this tool (beyond the source's own): EXPECTATION_INVALID, RELEASE_SHA256_NOT_THE_EXPECTED_HASH,
RELEASE_CODE_REVISION_NOT_THE_EXPECTED_REVISION, RELEASE_PACKAGE_NOT_THE_EXPECTED_PACKAGE,
EXPECTATION_NOT_THE_DEPLOYED_RELEASE, RELEASE_IS_A_SYNTHETIC_FIXTURE."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'build'/'install_release.py'
# What is deployed, as the family was told on 2026-10-02 (main and the implementation package of the release).
DEPLOYED={'code_revision':'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858',
          'implementation_package_sha':'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'}
# The test fixture of this directory says SYNTHETIC_FIXTURE in every reference it carries: it must never be bound.
SYNTHETIC_MARK='SYNTHETIC_FIXTURE'
OPTIONS={'--expect-sha256':('sha256','[0-9a-f]{64}'),'--expect-code-revision':('code_revision','[0-9a-f]{40}'),
         '--expect-package-sha':('implementation_package_sha','[0-9a-f]{64}')}

class Refusal(ValueError):pass

def load_source(path=SOURCE):
    """The assembled source as a private module object. It has no action on import."""
    raw=Path(path).read_bytes();name='_hostops02_install_release_binding_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled install_release.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__)
    return module,hashlib.sha256(raw).hexdigest()

def read_release(path,limit):
    """The bytes of one regular file, opened without following a link, unchanged while read."""
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:raise ValueError('RELEASE_FILE_NOT_REGULAR_OR_TOO_LARGE')
        chunks=[]
        while True:
            block=os.read(fd,65536)
            if not block:break
            chunks.append(block)
        raw=b''.join(chunks);after=os.fstat(fd)
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns) or len(raw)!=before.st_size:
            raise ValueError('RELEASE_FILE_CHANGED_DURING_READ')
        return raw
    finally:os.close(fd)

def member(module,raw):
    """(plan member, facts): built here, then judged by the source's own functions."""
    item={'path':module.RELEASE_PATH,'content_b64':base64.b64encode(raw).decode('ascii'),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    decoded=module.release_of({'release':item})
    if decoded!=raw:raise ValueError('RELEASE_ROUND_TRIP')
    return item,module.release_facts(decoded)

def strings(value):
    """Every text of a decoded JSON value, keys included."""
    if type(value) is str:yield value
    elif type(value) is dict:
        for key,item in value.items():
            yield key
            for found in strings(item):yield found
    elif type(value) is list:
        for item in value:
            for found in strings(item):yield found

def arguments_of(arguments):
    """(release file, expectations) of a call in the exact usage, or None. Each option exactly once, in any order."""
    paths=[];expected={};index=0
    while index<len(arguments):
        word=arguments[index]
        if word in OPTIONS:
            if index+1>=len(arguments) or OPTIONS[word][0] in expected:return None
            expected[OPTIONS[word][0]]=arguments[index+1];index+=2
        elif word.startswith('-'):return None
        else:paths.append(word);index+=1
    if len(paths)!=1 or set(expected)!={name for name,_ in OPTIONS.values()}:return None
    return paths[0],expected

def judged(module,raw,expected,deployed):
    """The member and the facts of raw, or a Refusal: the expectations, the release against them, the fixture, and
    last the revision and the package this directory was built for."""
    for option,(name,pattern) in sorted(OPTIONS.items()):
        if type(expected.get(name)) is not str or re.fullmatch(pattern,expected[name]) is None or expected[name]=='0'*len(expected[name]):
            raise Refusal('EXPECTATION_INVALID')
    if hashlib.sha256(raw).hexdigest()!=expected['sha256']:raise Refusal('RELEASE_SHA256_NOT_THE_EXPECTED_HASH')
    item,facts=member(module,raw)
    if facts['code_revision']!=expected['code_revision']:raise Refusal('RELEASE_CODE_REVISION_NOT_THE_EXPECTED_REVISION')
    if facts['implementation_package_sha']!=expected['implementation_package_sha']:raise Refusal('RELEASE_PACKAGE_NOT_THE_EXPECTED_PACKAGE')
    if any(text.startswith(SYNTHETIC_MARK) for text in strings(module.strict(raw))):raise Refusal('RELEASE_IS_A_SYNTHETIC_FIXTURE')
    if (expected['code_revision'],expected['implementation_package_sha'])!=(deployed['code_revision'],deployed['implementation_package_sha']):
        raise Refusal('EXPECTATION_NOT_THE_DEPLOYED_RELEASE')
    return item,facts

def main(arguments,deployed=None,out=None,err=None):
    """deployed, out and err exist for the tests of this tool; the command line never sets them."""
    deployed=DEPLOYED if deployed is None else deployed;out=sys.stdout if out is None else out;err=sys.stderr if err is None else err
    parsed=arguments_of(list(arguments))
    if parsed is None:
        err.write(__doc__);return 2
    path,expected=parsed;module,source_sha256=load_source()
    try:
        raw=read_release(path,module.MAX_RELEASE_BYTES);item,facts=judged(module,raw,expected,deployed)
    except (ValueError,OSError) as error:
        code=str(error) if isinstance(error,ValueError) and module.text(str(error),module.CODE) else 'RELEASE_FILE_UNREADABLE'
        err.write('REFUSED %s\n'%code);return 1
    result={'schema':'HOSTOPS02_INSTALL_RELEASE_BINDING_FIELDS_V2','payload_sha256':source_sha256,'release':item,'facts':facts,
            'expected':dict(expected,expectations_met=True),
            'request_bytes_added':len(module.canonical(item))-len(module.canonical({'path':module.RELEASE_PATH,'content_b64':None,'sha256':None,'bytes':None}))}
    out.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');return 0

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
