"""Portable offline candidate suite; no host execution or acceptance of seals."""
import os,sys,subprocess, tempfile, shutil, json, hashlib
from pathlib import Path
base=Path(__file__).resolve().parent
env=dict(os.environ)
env.update(BIND_TEST_REVIEWED_REFERENCE_ROOT=str(base/'references'),BIND_TEST_W1=str(base/'fixtures/w1'),BIND_TEST_HOSTOPS=str(base/'fixtures/hostops01'),
 BIND_TEST_HOSTOPS02=str(base/'fixtures/hostops02'),BIND_TEST_HOSTOPS02_SOURCES=str(base/'fixtures/hostops02'),
 BIND_TEST_PROGRAMS=str(base/'test-inputs/programs-final-candidate'),
 BIND_TEST_K9R=str(base/'test-inputs/k9_phase_read.rev4-snapshot-20261005T0128Z'),
 BIND_TEST_K4E0=str(base/'test-inputs/k4_e0.sealed-63c75348'),
 BIND_TEST_K9W=str(base/'test-inputs/k9_phase_step.sealed-92203431'),
 BIND_TEST_RUNNER=str(base/'test-inputs/k9_runner.rev2-563a4797/k9_runner.py'))
# Isolated test-only acceptance: privacy-adapted historical fixtures have new hashes.
# The shipped operational acceptance list is never changed.
trial=Path(tempfile.mkdtemp(prefix='binder-offline-proof-'))
shutil.copytree(base,trial,dirs_exist_ok=True)
config=Path(os.environ['BIND_TEST_K8_CONFIG'])
assert hashlib.sha256(config.read_bytes()).hexdigest()=='91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897', 'K8 dependency bytes differ'
shutil.copyfile(config,trial/'bind/k8_verifier/c3po/backend/app/config.py')
env.update(BIND_CANDIDATE_ROOT=str(trial),BIND_WORK_ROOT=str(trial/'optional-work'),BIND_TEST_OPERATIONAL_SEALS=str(base/'bind/ACCEPTED_SEALS.json'))
seals_path=trial/'bind/ACCEPTED_SEALS.json'
seals=json.loads(seals_path.read_text())
fixtures={}
for name in ['fixtures/w1','fixtures/hostops01','fixtures/hostops02/epoch_readback']:
    directory=base/name
    sums=(directory/'SHA256SUMS').read_bytes()
    fixtures[name]=hashlib.sha256(sums).hexdigest()
for row in seals['seals']:
    if row['family']=='W1PREFLIGHT01':row['sha256sums_sha256']=fixtures['fixtures/w1']
    if row['family']=='HOSTOPS02_EPOCH_READBACK':row['sha256sums_sha256']=fixtures['fixtures/hostops02/epoch_readback']
seals_path.write_text(json.dumps(seals,indent=2)+'\n')
manifest=trial/'bind/SHA256SUMS'
manifest.write_text(''.join(hashlib.sha256((manifest.parent/line.split('  ',1)[1]).read_bytes()).hexdigest()+'  '+line.split('  ',1)[1]+'\n' for line in manifest.read_text().splitlines()))
args=sys.argv[1:]
raise SystemExit(subprocess.call([sys.executable,'-B','-m','pytest','-p','no:cacheprovider',str(trial/'bind/tests'),'-q','--tb=short']+args,env=env))
