"""Fixed GitHub #429 documentary channel. Never an independent human signature.

Originals are complete, canonical JSON comment bodies from elected author IDs,
two exact GETs and a fully paginated real collection. A POST is reserved durably
before sending; an uncertain send is reconciled by reads, never repeated.
"""
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import timedelta
from common import Hold, canonical, digest, instant, need, sha, strict
from runtime import physical

PREFIX='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence/'


class GitHub429:
    def __init__(self,guard,token_path,token_sha256,*,since=None,opener=None):
        self.guard=guard;self.token_path=token_path;self.token_pin=sha(token_sha256)
        self.since=since
        if since is not None:instant(since)
        # Standard opener verifies TLS and rejects redirects (including token leak).
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):raise Hold('CHANNEL_REDIRECT')
        self.opener=opener or urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def _http(self,path,method='GET',body=None):
        need(re.fullmatch(r'issues/comments/[1-9][0-9]*|issues/429/comments(?:\?per_page=100&page=[1-9][0-9]*(?:&since=[A-Za-z0-9%_.:-]+)?)?',path),
             'CHANNEL_ENDPOINT')
        need(method in ('GET','POST') and (method=='GET' or path=='issues/429/comments'),'CHANNEL_METHOD')
        raw,ident=physical(self.token_path,maximum=4096)
        need(digest(raw)==self.token_pin and ident['mode']==0o400 and ident['uid']==self.guard.value['measurement']['euid'],
             'CHANNEL_TOKEN_PERMISSION')
        token=raw.strip().decode('ascii');need(token and not any(c.isspace() for c in token),'CHANNEL_TOKEN_FORMAT')
        self.guard.recheck()
        headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+token,
                 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'c3po-server-v2','Content-Type':'application/json'}
        req=urllib.request.Request(PREFIX+path,data=body,headers=headers,method=method)
        try:
            with self.opener.open(req,timeout=15) as response:
                need(response.status==(201 if method=='POST' else 200),'CHANNEL_HTTP_STATUS')
                raw=response.read(8*1024*1024+1)
                need(len(raw)<=8*1024*1024,'CHANNEL_RESPONSE_SIZE')
        except (urllib.error.URLError,TimeoutError,OSError):raise Hold('CHANNEL_UNCERTAIN') from None
        self.guard.recheck();return strict(raw,8*1024*1024)

    def collection(self):
        rows=[];ids=set()
        from urllib.parse import quote
        since=getattr(self,'since',None)
        suffix=('&since='+quote(since,safe='')) if since is not None else ''
        for page in range(1,101):
            chunk=self._http('issues/429/comments?per_page=100&page=%s'%page+suffix)
            need(type(chunk) is list and len(chunk)<=100,'CHANNEL_PAGE')
            for row in chunk:
                need(row['id'] not in ids,'CHANNEL_DUPLICATE_ID');ids.add(row['id']);rows.append(row)
            if len(chunk)<100:return rows
        raise Hold('CHANNEL_PAGINATION_INCOMPLETE')

    def original(self,reference,collection):
        need(type(reference['id']) is int and reference['id']>0,'CHANNEL_COMMENT_ID')
        a=self._http('issues/comments/%s'%reference['id']);b=self._http('issues/comments/%s'%reference['id'])
        matches=[r for r in collection if r['id']==reference['id']]
        need(len(matches)==1,'CHANNEL_ORIGINAL_NOT_UNIQUE');row=matches[0]
        need(a==b==row and row['user']['id']==reference['author_id'] and row['user']['type']==reference['author_type']
             and row['created_at']==row['updated_at'],'CHANNEL_ORIGINAL_EDITED_OR_AUTHOR')
        need(row['issue_url']==PREFIX+'issues/429','CHANNEL_ORIGINAL_WRONG_ISSUE')
        raw=row['body'].encode('utf-8');need(digest(raw)==sha(reference['body_sha256']),'CHANNEL_ORIGINAL_HASH')
        value=strict(raw);need(canonical(value)==raw,'CHANNEL_ORIGINAL_NOT_CANONICAL')
        return {'raw':raw,'value':value,'created_UTC':row['created_at'],'id':row['id']}

    def originals(self,references):
        collection=self.collection()
        need(set(references)=={'request','question','owner','bound','authority','review'},'CHANNEL_ORIGINAL_SET')
        result={role:self.original(ref,collection) for role,ref in references.items()}
        question,owner=result['question'],result['owner']
        # Publication time is an API fact learned AFTER POST. Requiring a
        # question to contain its future created_at would create a fixed point.
        signed=instant(owner['value']['signed_at_UTC']);published=instant(question['created_UTC'])
        need(published<=signed<=instant(owner['created_UTC'])
             and (instant(owner['created_UTC'])-signed).total_seconds()<=60,'CHANNEL_OWNER_ORIGINAL_TIME')
        return result

    def post_once(self,prepared):
        """Caller MUST already have journaled the publication reservation."""
        need(type(prepared) is bytes and len(prepared)<=60000,'CHANNEL_POST_SIZE')
        return self._http('issues/429/comments','POST',canonical({'body':prepared.decode('utf-8')}))

    def recover_post(self,prepared,author_id):
        rows=self.collection();matches=[r for r in rows if digest(r['body'].encode())==digest(prepared)
              and r['user']['id']==author_id]
        need(len(matches)==1,'CHANNEL_POST_UNKNOWN_OR_AMBIGUOUS');row=matches[0]
        ref={'id':row['id'],'author_id':author_id,'author_type':row['user']['type'],'body_sha256':digest(prepared)}
        # Publication summaries need not be JSON, so read and compare directly.
        a=self._http('issues/comments/%s'%ref['id']);b=self._http('issues/comments/%s'%ref['id'])
        need(a==b==row and row['created_at']==row['updated_at'],'CHANNEL_POST_READBACK')
        return {'id':row['id'],'body_sha256':digest(prepared),'executor_repeated':False}
