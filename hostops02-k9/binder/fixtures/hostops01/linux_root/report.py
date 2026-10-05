"""What the Linux job produced, printed for the job log. Reads only; changes nothing; exit 0 always (the status of
the job is run.sh's).

For each of the four output files of run.sh: its SHA-256 and size. Of the two junit files only the counts of the
test suite and the name and message of every failure, error and skip, never the whole XML. The two small files
(SHAPES.linux-root.json, VERIFY.linux-root.txt) in full when they are under 64 KiB.

usage: /usr/bin/python3 -I -B linux_root/report.py [file ...]      (default: the four files next to this script)
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET

HERE=os.path.dirname(os.path.abspath(__file__))
JUNIT=('TESTS.linux-root.xml','TESTS.linux-user.xml')
FULL=('SHAPES.linux-root.json','VERIFY.linux-root.txt')
LIMIT=64*1024
MAX_ROWS=200
COUNTS=('tests','failures','errors','skipped','time','timestamp')

def clip(text,limit=300):
    text=' '.join(str(text or '').split());return text if len(text)<=limit else text[:limit]+' ...'

def junit(raw):
    """Counts of each test suite, then one line per test that failed, errored or was skipped."""
    lines=[]
    try:root=ET.fromstring(raw)
    except ET.ParseError as error:return ['not a junit file: '+clip(error)+' | first bytes: '+clip(raw[:200].decode('utf-8','replace'))]
    suites=[root] if root.tag=='testsuite' else root.findall('testsuite')
    for suite in suites:
        lines.append('testsuite '+' '.join('%s=%s'%(key,suite.get(key)) for key in COUNTS if suite.get(key) is not None))
        rows=0
        for case in suite.iter('testcase'):
            for kind in ('failure','error','skipped'):
                for item in case.findall(kind):
                    rows+=1
                    if rows<=MAX_ROWS:lines.append('%s %s::%s | %s'%(kind,case.get('classname'),case.get('name'),clip(item.get('message'))))
        if rows>MAX_ROWS:lines.append('... %d more rows not printed'%(rows-MAX_ROWS))
        if not rows:lines.append('no failure, no error, no skip')
    return lines or ['no testsuite element']

def report(path):
    name=os.path.basename(path);lines=['==== '+name]
    try:
        with open(path,'rb') as handle:raw=handle.read()
    except OSError as error:return lines+['MISSING: '+clip(error.strerror)]
    lines.append('sha256 %s  bytes %d'%(hashlib.sha256(raw).hexdigest(),len(raw)))
    if name in JUNIT or name.endswith('.xml'):lines+=junit(raw)
    elif len(raw)<LIMIT:lines+=['---- content']+raw.decode('utf-8','replace').splitlines()+['---- end of '+name]
    else:lines.append('content not printed: %d bytes is not under %d'%(len(raw),LIMIT))
    return lines

def main():
    paths=sys.argv[1:] or [os.path.join(HERE,name) for name in JUNIT+FULL]
    for path in paths:print('\n'.join(report(path)))
    return 0

if __name__=='__main__':raise SystemExit(main())
