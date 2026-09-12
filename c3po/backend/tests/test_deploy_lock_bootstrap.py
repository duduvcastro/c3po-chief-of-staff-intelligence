"""Execute the exact workflow bootstrap; preserve a lock held by another process."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


def bootstrap_source():
    workflow = Path(__file__).resolve().parents[3]/'.github/workflows/c3po-pipeline.yml'
    jobs = yaml.safe_load(workflow.read_text())['jobs']
    steps = [step for job in jobs.values() for step in job.get('steps', [])]
    script = next(step['run'] for step in steps if step.get('name') == 'Deploy and verify')
    return script.split("<<'LOCK_BOOTSTRAP'\n", 1)[1].split('\nLOCK_BOOTSTRAP', 1)[0]


def bootstrap(path):
    return subprocess.run([sys.executable, '-', str(path), str(os.getuid()), str(os.getgid())],
                          input=bootstrap_source(), text=True, capture_output=True)


def test_first_deploy_creates_parent_and_writable_lock(tmp_path):
    lock = tmp_path/'security/deployment.lock'
    result = bootstrap(lock)
    assert result.returncode == 0, result.stderr
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert lock.stat().st_uid == os.getuid()
    assert lock.stat().st_mode & 0o777 == 0o644


def test_bootstrap_preserves_existing_bytes_inode_and_exclusion(tmp_path):
    lock = tmp_path/'deployment.lock'
    lock.write_text('existing lock evidence')
    inode = lock.stat().st_ino
    with lock.open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = bootstrap(lock)
        assert result.returncode == 0, result.stderr
        assert lock.stat().st_ino == inode
        assert lock.read_text() == 'existing lock evidence'
        with lock.open('a') as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with lock.open('a') as contender:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_bootstrap_refuses_link_aliases(tmp_path, kind):
    target = tmp_path/'target'
    target.write_text('untouched')
    lock = tmp_path/'deployment.lock'
    if kind == 'symlink':
        lock.symlink_to(target)
    else:
        os.link(target, lock)
    result = bootstrap(lock)
    assert result.returncode != 0
    assert target.read_text() == 'untouched'
