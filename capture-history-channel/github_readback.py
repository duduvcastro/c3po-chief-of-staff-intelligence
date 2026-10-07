"""Capture-only authenticated GitHub GET bridge; never posts/signs/dispatches.

Private packet is evidence of API readback, not independent cryptographic evidence
that a human authored a comment. Exact dated outside-Mac authority remains required.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import urllib.error
import urllib.request

API = 'https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence/issues/comments/'
HELPER_SHA = '9a3a6605176215b22be0613f7e0be1f8b0093ca147ca2bf63e0f16e7a962c814'
LIMIT = 65536
class Refused(ValueError): pass

def need(ok, code):
    if not ok: raise Refused(code)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def strict(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'API_DUPLICATE_FIELD'); out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused('API_NONFINITE')))
    except (TypeError, ValueError): raise Refused('API_JSON_INVALID')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Refused('API_REDIRECT_FORBIDDEN')

class GitHubGET:
    def __init__(self, token, opener=None):
        need(type(token) is str and token and not re.search(r'[\s\x00-\x1f]', token), 'API_TOKEN_INVALID')
        self.token = token
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
    def comment(self, cid):
        need(type(cid) is int and cid > 0, 'API_COMMENT_ID_INVALID')
        url = API + str(cid)
        req = urllib.request.Request(url, method='GET', headers={
            'Authorization':'Bearer '+self.token, 'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'capture-readback-candidate'})
        try:
            with self.opener.open(req, timeout=20) as reply:
                need(reply.status == 200 and reply.geturl() == url, 'API_STATUS_OR_LOCATION')
                need(reply.headers.get_content_type() == 'application/json', 'API_CONTENT_TYPE')
                raw = reply.read(LIMIT + 1)
        except Refused: raise
        except (urllib.error.URLError, OSError, TimeoutError):
            raise Refused('API_READ_FAILED_NO_RETRY')
        need(len(raw) <= LIMIT, 'API_RESPONSE_TOO_LARGE')
        value = strict(raw)
        need(type(value) is dict and value.get('id') == cid and type(value.get('id')) is int
             and value.get('url') == url, 'API_COMMENT_ID_OR_LOCATION')
        return value

def validator():
    path = Path(__file__).with_name('owner_response.py')
    raw = path.read_bytes()
    need(sha(raw) == HELPER_SHA, 'API_OWNER_HELPER_CHANGED')
    namespace = {'__name__':'checked_owner_response','__builtins__':__builtins__}
    exec(compile(raw, 'checked_owner_response', 'exec'), namespace)
    return namespace['validate_owner_response']

def collect(client, question_id, answer_id, question_body, context, clock=None):
    """No retries. IDs supplied by operator; exact body from own owner-request.

    Obtain each complete snapshot twice. A change refuses the packet. This function
    only accepts an explicitly labelled Fable record of an owner answer nor fetches a future policy receipt.
    """
    need(type(question_body) is str and len(question_body.encode()) <= 4096, 'API_QUESTION_INVALID')
    need(type(context) is dict and sha(question_body.encode()) == context.get('question_body_sha256'), 'API_QUESTION_PIN')
    q1, q2 = client.comment(question_id), client.comment(question_id)
    need(q1 == q2 and q1.get('body') == question_body
         and q1.get('created_at') == q1.get('updated_at') == context.get('question_created_at')
         and q1.get('issue_url') == API.rsplit('/comments/',1)[0]+'/429', 'API_QUESTION_READBACK')
    a1, a2 = client.comment(answer_id), client.comment(answer_id)
    now = (clock if clock is not None else lambda:dt.datetime.now(dt.timezone.utc))()
    need(isinstance(now, dt.datetime) and now.tzinfo == dt.timezone.utc, 'API_CLOCK_INVALID')
    observed = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    try: record = validator()(a1, a2, context, observed)
    except ValueError: raise Refused('API_OWNER_RESPONSE_REFUSED')
    packet = dict(question_first=q1,question_readback=q2,first=a1,readback=a2,observed_at=observed)
    raw = (json.dumps(packet,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw) <= LIMIT, 'API_PACKET_TOO_LARGE')
    return raw, record

def private_read(path, maximum):
    p=Path(path)
    need(p.is_absolute(), 'API_INPUT_RELATIVE')
    for part in (p.parent, *p.parent.parents): need(not part.is_symlink(), 'API_INPUT_SYMLINK_ANCESTOR')
    st=p.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1
         and stat.S_IMODE(st.st_mode)==0o600 and st.st_size<=maximum, 'API_INPUT_NOT_PRIVATE')
    fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno());raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
    named=p.lstat()
    need((before.st_dev,before.st_ino,before.st_mtime_ns,before.st_ctime_ns,before.st_size)==
         (after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns,after.st_size)==
         (named.st_dev,named.st_ino,named.st_mtime_ns,named.st_ctime_ns,named.st_size) and len(raw)<=maximum, 'API_INPUT_CHANGED')
    return raw

def store_packet(out, raw):
    p=Path(out);need(p.is_absolute() and not p.exists(), 'API_OUTPUT_EXISTS_OR_RELATIVE')
    parent=p.parent;st=parent.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,
         'API_OUTPUT_NOT_PRIVATE')
    # Refuse symlink ancestors and use exclusive/no-follow creation. No overwrite.
    for part in (parent, *parent.parents):need(not part.is_symlink(),'API_OUTPUT_SYMLINK_ANCESTOR')
    fd=os.open(str(p),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return dict(status='API_READBACK_STORED_NOT_SIGNED',packet_sha256=sha(raw),operational_READY=False)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Exact authenticated readback only; never signs.',allow_abbrev=False)
    parser.add_argument('--question-id',type=int,required=True)
    parser.add_argument('--answer-id',type=int,required=True)
    parser.add_argument('--question-body',required=True)
    parser.add_argument('--context',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    try:
        body=private_read(args.question_body,4096).decode('utf-8')
        context=strict(private_read(args.context,4096))
        raw,record=collect(GitHubGET(os.environ.get('CAPTURE_GITHUB_READ_TOKEN','')),
                           args.question_id,args.answer_id,body,context)
        result=store_packet(args.out,raw)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (Refused,OSError,UnicodeError,ValueError):
        print(json.dumps({'status':'API_READBACK_REFUSED_NO_RETRY','operational_READY':False}))
        return 2

if __name__=='__main__': raise SystemExit(main())
