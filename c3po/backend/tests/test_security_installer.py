"""Execute the installer against isolated filesystem/systemd substitutes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_bootstrap_is_held_before_timers_and_reinstall_preserves_activation(tmp_path):
    source = Path(__file__).resolve().parents[3]
    root = tmp_path/'project'
    root.mkdir()
    shutil.copytree(source/'scripts', root/'scripts')
    shutil.copytree(source/'ops', root/'ops')
    (root/'.deploy-version').write_text('a'*40)
    local = tmp_path/'local'
    etc = tmp_path/'etc'
    (local/'sbin').mkdir(parents=True)
    (etc/'systemd/system').mkdir(parents=True)
    snapshot = local/'sbin/c3po-host-security-snapshot'
    snapshot.touch()
    snapshot.chmod(0o755)
    bindir = tmp_path/'bin'
    bindir.mkdir()
    install = bindir/'install'
    install.write_text('#!'+sys.executable+'\n'+'''import os, pathlib, shutil, sys
args=sys.argv[1:]; operands=[]; directory=False; i=0
while i<len(args):
    if args[i] in ('-o','-g','-m'): i+=2; continue
    if args[i]=='-d': directory=True
    else: operands.append(args[i])
    i+=1
if directory:
    for p in operands: pathlib.Path(p).mkdir(parents=True,exist_ok=True)
else:
    dest=pathlib.Path(operands[-1])
    for p in operands[:-1]: shutil.copyfile(p, dest/pathlib.Path(p).name if dest.is_dir() else dest)
''')
    install.chmod(0o755)
    systemctl = bindir/'systemctl'
    systemctl.write_text('#!'+sys.executable+'\n'+'''import json, os, pathlib, sys
hold=pathlib.Path(os.environ['TEST_HOLD'])
with open(os.environ['TEST_EVENTS'],'a') as f: f.write(json.dumps({'args':sys.argv[1:], 'hold':hold.read_text() if hold.exists() else None})+'\\n')
''')
    systemctl.chmod(0o755)
    verify=bindir/'systemd-analyze'
    verify.write_text('#!/bin/sh\nexit 0\n'); verify.chmod(0o755)
    script=(source/'scripts/install-security-daily.sh').read_text()
    script=script.replace('/opt/chief-of-staff-digital',str(root)).replace('/usr/local',str(local)).replace('/etc/',str(etc)+'/')
    hold=etc/'c3po/security-maintenance.hold'
    events=tmp_path/'events.jsonl'
    env={**os.environ,'PATH':str(bindir)+':'+os.environ['PATH'],'TEST_HOLD':str(hold),'TEST_EVENTS':str(events)}
    def run():
        events.write_text('')
        subprocess.run(['bash','-c',script],env=env,check=True,capture_output=True,text=True)
        return [json.loads(line) for line in events.read_text().splitlines()]
    assert all(row['hold']=='bootstrap: pending post-install acceptance\n' for row in run())
    hold.unlink()  # Authorized acceptance releases only bootstrap.
    assert all(row['hold'] is None for row in run())
    hold.write_text('operator hold unchanged')
    assert all(row['hold']=='operator hold unchanged' for row in run())
