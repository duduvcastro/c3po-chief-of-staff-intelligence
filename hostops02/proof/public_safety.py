"""Public-safety scan of what this branch adds to the release: hostops02/, hostops02-tok/ and the one workflow file.

  /usr/bin/python3 -I -B proof/public_safety.py

Looks, in every file, for the classes a pattern can name without naming a private value: an absolute path of a
workstation or of a home directory, the temporary directories of a workstation, key material and tokens of the
common forms, an IPv4 address that is not a documentation, loopback or unspecified one, and a mail-like or
user@host word outside the reserved domains. Prints the class, the file and the line number of each finding, never
the text. Exit 0 only when nothing is found.

What it cannot find, and what was looked for by other means before this branch was made (README.txt, section
"Public safety"): a number or an identifier copied from a receipt of the host (it was looked for value by value,
offline, against the receipts themselves), and names that are only private by context.
"""
import os
import re
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
FAMILY=os.path.dirname(HERE)
REPOSITORY=os.path.dirname(FAMILY)
ROOTS=(FAMILY,os.path.join(REPOSITORY,'hostops02-tok'),os.path.join(REPOSITORY,'.github','workflows'))
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
# a substring every match of the class contains, or one of several
NEEDS={'WORKSTATION_HOME_PATH':('/Users/','/home/'),'WORKSTATION_TEMPORARY_PATH':('/private/','/var/f','pytest-of-'),'PRIVATE_KEY_BLOCK':('PRIVATE KEY',),
       'TOKEN_OF_A_KNOWN_FORM':('ghp_','gho_','ghs_','ghu_','ghr_','github_pat_','AKIA','xox','sk-'),'IPV4_ADDRESS':('.',),'MAIL_OR_USER_AT_HOST':('@',)}
HARMLESS_IPV4=re.compile(r'(?:0\.0\.0\.0|127\.[0-9]+\.[0-9]+\.[0-9]+|192\.0\.2\.[0-9]+|198\.51\.100\.[0-9]+|203\.0\.113\.[0-9]+|255\.255\.255\.[0-9]+)')

def harmless(name,found):
    if name=='IPV4_ADDRESS':
        return bool(HARMLESS_IPV4.fullmatch(found)) or any(int(part)>255 for part in found.split('.'))
    if name=='MAIL_OR_USER_AT_HOST':return found.lower().endswith(RESERVED)
    if name=='TOKEN_OF_A_KNOWN_FORM':return found.endswith('EXAMPLE')      # the provider's documented example identifier, used by a test as a word that is not a code
    return False

def files():
    for root in ROOTS:
        for folder,names,found in os.walk(root):
            names[:]=[name for name in names if name not in SKIPPED_PARTS and not (folder==HERE and name=='out')]
            for name in sorted(found):
                if not name.endswith('.pyc'):yield os.path.join(folder,name)

def main():
    findings=[];count=0
    for path in files():
        count+=1
        with open(path,'rb') as handle:text=handle.read().decode('utf-8','replace')
        for number,line in enumerate(text.split('\n'),1):
            for name,pattern in CLASSES:
                if not any(word in line for word in NEEDS[name]):continue          # a cheap look first: some files are one line of a megabyte
                if any(not harmless(name,item.group(0)) for item in pattern.finditer(line)):
                    findings.append((name,os.path.relpath(path,REPOSITORY),number))
    for name,path,number in findings:print('FOUND %s %s:%d'%(name,path,number))
    print('PUBLIC_SAFETY_%s files %d findings %d'%('CLEAN' if not findings else 'FINDINGS',count,len(findings)))
    return 0 if not findings else 1

if __name__=='__main__':raise SystemExit(main())
