"""Public-safety scan of what the K9 proof branch adds to the release: hostops02-k9/ and the one workflow file.

  /usr/bin/python3 -I -B proof/public_safety.py                 (on the branch: hostops02-k9/ and .github/workflows/)
  /usr/bin/python3 -I -B proof/public_safety.py <path> ...      (any files or directories, e.g. before staging)
  ... --json                                                    (one JSON line per finding, then a summary line)

The classes and the patterns are those of the token proof branch's proof/public_safety.py (ops/hostops02-token-proof,
fce3fb1a), unchanged: an absolute path of a workstation or of a home directory, the temporary directories of a
workstation, key material and tokens of the common forms, an IPv4 address that is not a documentation, loopback or
unspecified one, and a mail-like or user@host word outside the reserved domains. Prints the class, the file and the
line number of each finding, never the text. Exit 0 only when nothing is found.

What it cannot find: a number or an identifier copied from a receipt of the host, and names that are only private by
context. Those are looked for by other means before a push (README.md, "Public safety").
"""
import json
import os
import re
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
FAMILY=os.path.dirname(HERE)
REPOSITORY=os.path.dirname(FAMILY)
SKIPPED_PARTS=('__pycache__','.pytest_cache')
RESERVED=('.invalid','.example','.test','example.com','example.org','example.net','noreply.anthropic.com','users.noreply.github.com')
CLASSES=(
    ('WORKSTATION_HOME_PATH',re.compile(r'/(?:Users|home)/(?!runner/)[A-Za-z0-9._-]+/')),
    ('WORKSTATION_TEMPORARY_PATH',re.compile(r'/private/(?:tmp|var)/|/var/f[o]lders/|pytest-of-[A-Za-z0-9._-]+')),
    ('PRIVATE_KEY_BLOCK',re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('TOKEN_OF_A_KNOWN_FORM',re.compile(r'\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bsk-[A-Za-z0-9_-]{32,}')),
    ('IPV4_ADDRESS',re.compile(r'(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])')),
    ('MAIL_OR_USER_AT_HOST',re.compile(r'(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){1,8}')),
)
NEEDS={'WORKSTATION_HOME_PATH':('/'+'Users'+'/','/'+'home'+'/'),'WORKSTATION_TEMPORARY_PATH':('/private/','/var/f','pytest-of-'),'PRIVATE_KEY_BLOCK':('PRIVATE KEY',),
       'TOKEN_OF_A_KNOWN_FORM':('ghp_','gho_','ghs_','ghu_','ghr_','github_pat_','AKIA','xox','sk-'),'IPV4_ADDRESS':('.',),'MAIL_OR_USER_AT_HOST':('@',)}
HARMLESS_IPV4=re.compile(r'(?:0\.0\.0\.0|127\.[0-9]+\.[0-9]+\.[0-9]+|192\.0\.2\.[0-9]+|198\.51\.100\.[0-9]+|203\.0\.113\.[0-9]+|255\.255\.255\.[0-9]+)')

def harmless(name,found):
    if name=='IPV4_ADDRESS':
        return bool(HARMLESS_IPV4.fullmatch(found)) or any(int(part)>255 for part in found.split('.'))
    if name=='MAIL_OR_USER_AT_HOST':return found.lower().endswith(RESERVED)
    if name=='TOKEN_OF_A_KNOWN_FORM':return found.endswith('EXAMPLE')
    return False

def files(roots):
    for root in roots:
        if os.path.isfile(root) or os.path.islink(root):
            if os.path.isfile(root):yield root
            continue
        for folder,names,found in os.walk(root):          # links to directories are not followed: what they name is scanned where it lies
            names[:]=sorted(name for name in names if name not in SKIPPED_PARTS and not (folder==HERE and name=='out'))
            for name in sorted(found):
                path=os.path.join(folder,name)
                if not name.endswith('.pyc') and os.path.isfile(path) and not os.path.islink(path):yield path

def scan(roots):
    findings=[];count=0
    for path in files(roots):
        count+=1
        with open(path,'rb') as handle:text=handle.read().decode('utf-8','replace')
        for number,line in enumerate(text.split('\n'),1):
            for name,pattern in CLASSES:
                if not any(word in line for word in NEEDS[name]):continue
                if any(not harmless(name,item.group(0)) for item in pattern.finditer(line)):findings.append((name,path,number))
    return count,findings

def main(arguments):
    as_json='--json' in arguments;arguments=[item for item in arguments if item!='--json']
    roots=[os.path.abspath(item) for item in arguments] or [FAMILY,os.path.join(REPOSITORY,'.github','workflows')]
    base=os.path.commonpath(roots) if arguments else REPOSITORY
    if os.path.isfile(base):base=os.path.dirname(base)
    accepted=set()
    if not arguments and os.path.isfile(os.path.join(HERE,'UNITS.json')):
        # files published with a finding by the owner's decision (stage_branch.sh "accept"): reported, not counted
        with open(os.path.join(HERE,'UNITS.json'),'rb') as handle:accepted={row['file'] for row in json.load(handle).get('accepted_findings',[])}
    count,findings=scan(roots)
    counted=0
    for name,path,number in findings:
        relative=os.path.relpath(path,base)
        verdict='ACCEPTED' if os.path.relpath(path,FAMILY) in accepted else 'FOUND'
        counted+=verdict=='FOUND'
        print(json.dumps({'class':name,'file':relative,'line':number,'verdict':verdict},sort_keys=True) if as_json else '%s %s %s:%d'%(verdict,name,relative,number))
    print('PUBLIC_SAFETY_%s files %d findings %d accepted %d'%('CLEAN' if not counted else 'FINDINGS',count,counted,len(findings)-counted))
    return 0 if not counted else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
