"""Fixtures of the token placement: the emulated host as supervisor operation 2 leaves it (the configuration directory
/etc/c3po-bar, root:root 0700, with its two children), a deploy environment file that holds a FAKE token, the plan a
binder copies from the read-only receipts, and the scans that prove nothing of the token leaves a run.

Every token here is fake. The main one spells "fake token for tests only" in alternating case: no four consecutive
characters of it can occur in a receipt by chance (a receipt holds lower-case hex, upper-case codes, lower-case keys,
paths and instants), so a scan for every substring of four characters or more is meaningful."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
NOW=datetime(2026,10,3,17,0,tzinfo=timezone.utc)
TOKEN='FaKeToKeNfOrTeStSoNlY'                      # 21 characters, inside the grammar
LONGER='FaKeLoNgErToKeNfOrTeStSoNlYqUiTeA'          # another length: a receipt must not depend on it
LITERAL='FAKE-TOKEN-FOR-TESTS-0001'                 # the plain fake value of the task (exact-match scans only)
CONFIG='/etc/c3po-bar'
TOKEN_PATH=CONFIG+'/token'
DEPLOY=hostemu.DEPLOY
ENV_FILE=hostemu.ENV_FILE
# what the hostemu environment file already holds (two synthetic secrets), then the token line
BASE_ENV=bytes(hostemu.world().tree.get(ENV_FILE).content)

def K():return f.load(DIRECTORY)

def env_with(token=TOKEN,key='MASSIVE_API_TOKEN',before=b'',after=b''):
    """The environment file of the emulated host with one plain definition of the token."""
    return BASE_ENV+before+key.encode()+b'='+token.encode()+b'\n'+after

class TokenHost(hostemu.FakeHost):
    """The emulated host of the core, with one difference: the source writes the token from a memoryview of a bytearray
    (so that the bytearray can be zeroed afterwards), which the real os.write accepts and the core's emulation, written
    for create_file's bytes, asserts against. The view is copied here; the bytearray behind it is kept for the tests."""
    def write(self,fd,data):
        assert type(data) is memoryview and type(data.obj) is bytearray and data.contiguous and data.format=='B'
        self.written_from=getattr(self,'written_from',[])+[data.obj]
        return hostemu.FakeHost.write(self,fd,data.tobytes())

def world(env=None):
    """(k, host): the host after supervisor operation 2, the environment file holding the fake token."""
    k=K();host=f.world(k);host.__class__=TokenHost;hostemu.provision_supervisor(host)
    host.tree.get(ENV_FILE).content=bytearray(env_with() if env is None else env)
    return k,host

def fields(host,**changes):
    out={'config_chain':hostemu.rows(host,CONFIG),'deploy_directory':DEPLOY,'evidence_boot_id_sha256':f.BOOT_SHA}
    out.update(changes);return out

def case(now=None,env=None):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k,host=world(env);return f.Docs(k,fields(host),now=now or NOW),host

def token_node(host):return host.tree.get(TOKEN_PATH)
def state_of(host):return host.tree.snapshot()

def substrings(value,shortest=4):
    return sorted({value[start:start+size] for size in range(shortest,len(value)+1) for start in range(len(value)-size+1)},key=len)
def leaks(text,value=TOKEN,shortest=4):
    """Every substring of the token of at least `shortest` characters that occurs in text (bytes or str)."""
    if type(text) is bytes:text=text.decode('utf-8','replace')
    return [item for item in substrings(value,shortest) if item in text]
def line(receipt):return f.line(receipt)

def without_identity(receipt):
    """The receipt with what differs between two runs on a real filesystem (the inode of the file created, the instant
    the clock gave) taken out, and its own hash recomputed: for the comparison of two runs that differ in the token only."""
    value=json.loads(f.line(receipt));value.pop('metadata_sha256',None)
    for key in ('device','inode'):
        if key in (value.get('token_file') or {}):value['token_file'][key]=None
    return value


# ---------------------------------------------------------------- the release, when a tree of it is at hand
RELEASE='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RELEASE_FILES={'c3po/deployment/massive-supervisor/README.md':'644c6211c7351de1dfd17d880842deaf4d5e5b34ea63d23a274c5f4e463461c5',
               'c3po/backend/app/r2d2_v2_massive_supervisor.py':'215a25d38568287c16c894a0587037876e18fa4e1c9b739f65b881d4fa7aec24',
               'c3po/backend/app/config.py':'91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897',
               'c3po/compose.yml':'fd214c8e36e47cc88f58e947eebf33c959e81c42929c4ecbb9149f87bdbd499e',
               'c3po/backend/app/r2d2_v2_sources.py':'03d3099bf06916ddaf49c0ce8ef9b4afe59371d82930377bbb7eb2deb655ce8d'}
def release_tree():
    """A directory that holds the files of the release this operation is frozen against (each compared by hash), or
    None. Looked for in HOSTOPS02_TEST_RELEASE_TREE, in work/release of this operation directory (an extraction of
    dd4ec4bb), and in the directories above it (a checkout of the release that holds this one)."""
    candidates=[Path(os.environ['HOSTOPS02_TEST_RELEASE_TREE'])] if os.environ.get('HOSTOPS02_TEST_RELEASE_TREE') else []
    candidates+=[DIRECTORY/'work'/'release']+list(DIRECTORY.parents)[:6]
    for candidate in candidates:
        try:
            if all(f.sha((candidate/name).read_bytes())==pin for name,pin in RELEASE_FILES.items()):return candidate.resolve()
        except OSError:continue
    return None
