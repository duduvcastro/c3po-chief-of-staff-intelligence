"""The zsh blocks of RUNBOOK.md, run literally, each in a fresh shell, in REHEARSAL mode with the real clock.

Blocks marked `host` (resume) or `manual` are not run. Blocks marked `rede` (gh) are run with a FAKE `gh`: a script
written by this rehearsal into its own workspace and put first on the PATH of these shells only. It contacts nothing: it
records its arguments and prints a comment URL, or a creation time, in the shape the blocks read. Every block, the
resume one included, is also parsed by `zsh -n` (syntax only, nothing runs). Everything happens below one workspace whose
name starts with "rehearsal-"; RUN_BASE points the blocks at it instead of bind/runs, and ARCHIVE at a directory inside it
instead of the durable directory.

  python3 runbook_blocks.py <workspace that does not exist> <sealed W1 family>
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BIND = HERE.parent
LABEL = 'w1-runbook-rehearsal'
MARKER_ANSWER = 'REHEARSAL_NO_OWNER_ANSWER'
MARKER_PUBLICATION = 'REHEARSAL-NO-PUBLICATION'
NOT_RUN = ('preparar-run', 'resume')
GH_STUB = r'''#!/bin/zsh
# REHEARSAL STUB, NOT gh: contacts nothing. Records its arguments and prints what the runbook blocks read.
print -r -- "$*" >> "${GH_STUB_LOG}"
if [[ "$1 $2" == "issue comment" ]]; then
  print -r -- "https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/issues/429#issuecomment-9$(printf '%09d' $(( $(wc -l < "${GH_STUB_LOG}") )))"
elif [[ "$1" == "api" && "$2" == */issues/comments/* ]]; then
  date -u +%Y-%m-%dT%H:%M:%SZ
elif [[ "$1" == "api" ]]; then
  :          # the search for an intent comment: nothing found
else
  exit 64
fi
'''


def blocks():
    text = (BIND / 'RUNBOOK.md').read_text(encoding='utf-8')
    found = {}
    for match in re.finditer(r'<!-- bloco: ([a-z0-9-]+)((?: [a-z]+)*) -->\n```zsh\n(.*?)\n```\n', text, re.S):
        name, flags, body = match.group(1), match.group(2).split(), match.group(3)
        assert name not in found and '<label>' in body.splitlines()[0] and set(flags) <= {'rede', 'host', 'manual'}, name
        found[name] = (flags, body)
    assert text.count('```zsh\n') == len(found) + 1          # every zsh block of section 3 carries a marker (section 8 has one plain example)
    return found


def zulu(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def tree(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path(directory).rglob('*')) if path.is_file()}


def run(workspace, family):
    workspace = Path(workspace)
    assert workspace.is_absolute() and workspace.name.startswith('rehearsal-') and not os.path.lexists(str(workspace))
    os.umask(0o077)
    workspace.mkdir(mode=0o700)
    workspace = workspace.resolve()
    (workspace / 'REHEARSAL_MARKER.txt').write_text('REHEARSAL ONLY: the blocks of RUNBOOK.md run in rehearsal mode, fake transport, fake gh, no owner, no host.\n')
    copy = workspace / 'family-copy'
    shutil.copytree(str(family), str(copy), ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    done = subprocess.run(['/usr/bin/python3', '-B', str(BIND / 'bind_once.py'), 'rehearsal-reference', '--out', str(workspace / 'rehearsal-transport')],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert done.returncode == 0, done.stdout
    stub_directory = workspace / 'rehearsal-fake-gh'
    stub_directory.mkdir(mode=0o700)
    (stub_directory / 'gh').write_text(GH_STUB)
    (stub_directory / 'gh').chmod(0o700)
    stub_log = workspace / 'fake-gh-calls.log'
    run_directory = workspace / 'runs' / LABEL
    run_directory.mkdir(parents=True, mode=0o700)
    out = run_directory / 'rehearsal-bound'
    # what block 1a writes by hand in a real run, here with the rehearsal values
    (run_directory / 'run.env').write_text('FAMILY=%s\nOP=GO_READONLY_W1PREFLIGHT_01\nMODE=rehearsal\nPARAMS=%s\nOUT=%s\nREFERENCE=%s\nARCHIVE=%s\n' % (
        copy, run_directory / 'PARAMETERS.json', out, workspace / 'rehearsal-transport' / 'REHEARSAL_TRANSPORT_REFERENCE.json', workspace / 'rehearsal-archive'))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    end = min(now + timedelta(minutes=50), now.replace(hour=23, minute=59, second=59))
    (run_directory / 'PARAMETERS.json').write_text(json.dumps({
        'schema': 'BIND_ONCE_PARAMETERS_V1', 'operation': 'GO_READONLY_W1PREFLIGHT_01', 'label': LABEL, 'signature_model': 'IND', 'not_before': zulu(now),
        'not_after': zulu(end), 'candidates': {'release_directories': [], 'capacity_roots': []},
        'purpose_pt': 'ENSAIO dos blocos do runbook; nenhum dono é consultado e nenhum servidor é contactado.'}, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    (workspace / 'rehearsal-archive').mkdir(mode=0o700)
    found = blocks()
    transcript = []
    environment = {'PATH': '%s:/usr/bin:/bin:/usr/sbin:/sbin' % stub_directory, 'HOME': os.environ.get('HOME', '/'), 'RUN_BASE': str(workspace / 'runs'),
                   'BIND_CANDIDATE_ROOT':str(BIND.parent),'BIND_WORK_ROOT':str(workspace/'optional-work'), 'LANG': 'en_US.UTF-8', 'GH_STUB_LOG': str(stub_log)}
    for name, (flags, body) in sorted(found.items()):          # every block parses, the ones that are never run here included
        parsed = subprocess.run(['/bin/zsh', '-n', '-c', body.replace('<label>', LABEL)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        assert parsed.returncode == 0, (name, parsed.stdout.decode('utf-8', 'replace'))

    def save():
        (workspace / 'TRANSCRIPT.json').write_text(json.dumps(transcript, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')

    def block(name, repeat=False, answer=MARKER_ANSWER, label=LABEL):
        flags, body = found[name]
        assert name not in NOT_RUN and set(flags) <= {'rede'}, name
        done = subprocess.run(['/bin/zsh', '-c', body.replace('<label>', label).replace('<resposta>', answer)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              env=environment, timeout=300)
        text = done.stdout.decode('utf-8', 'replace')
        transcript.append({'block': name, 'repeat': repeat, 'zsh_exit': done.returncode, 'output': text})
        save()
        print('%-20s%s zsh exit=%d' % (name, ' (again)' if repeat else '', done.returncode), flush=True)
        assert 'Traceback' not in text and 'command not found' not in text and 'parse error' not in text and 'file exists' not in text, text[-800:]
        return text

    def once_more(name):
        """The same block again: it says so, runs nothing, clobbers nothing."""
        before, calls = tree(run_directory), stub_log.read_text() if stub_log.exists() else ''
        text = block(name, repeat=True)
        assert 'JÁ FEITO' in text and 'exit=' not in text.replace('gh exit=', ''), text[-800:]
        assert tree(run_directory) == before and (stub_log.read_text() if stub_log.exists() else '') == calls, name

    def wait_for_the_intent():
        started = json.loads((out / '.dispatch-root' / (LABEL + '-once') / 'intent.json').read_bytes())['started_at']
        while datetime.now(timezone.utc).replace(microsecond=0) < datetime.fromisoformat(started):
            time.sleep(0.2)
    ran = []
    text = block('verificar')
    ran.append('verificar')
    assert 'FAILED' not in text or os.environ.get('BIND_TEST_MANIFEST_MAY_BE_STALE'), text[-800:]
    # a label that is not the one of the parameters: the block stops before the binder
    text = block('prepare', label='another-label')
    assert 'exit=' not in text and not out.exists() and not (workspace / 'runs' / 'another-label').exists(), text[-800:]
    (workspace / 'runs' / 'another-label').mkdir(mode=0o700)
    (workspace / 'runs' / 'another-label' / 'run.env').write_text((run_directory / 'run.env').read_text())
    text = block('prepare', label='another-label')
    assert 'PARADO: o label de PARAMETERS.json não é another-label' in text and not out.exists(), text[-800:]
    text = block('prepare')
    ran.append('prepare')
    assert 'exit=0' in text and '"mode": "REHEARSAL"' in text and (run_directory / 'prepare.json').is_file() and 'label %s confere com a folha' % LABEL in text, text[-800:]
    once_more('prepare')
    text = block('publicar-pedido')
    ran.append('publicar-pedido')
    assert 'request bound, NOT signed' in text and (run_directory / 'request_publication_url.txt').is_file(), text[-800:]
    once_more('publicar-pedido')
    text = block('pergunta')
    ran.append('pergunta')
    assert 'ENSAIO' in text and 'PEDIDO DE ASSINATURA' in text and json.loads((run_directory / 'prepare.json').read_bytes())['prepare_json_sha256'] in text
    # an answer that is not the signature: nothing is recorded, and the sign block then refuses to run
    for answer in ('sim', 'Assino'):          # in a rehearsal not even the owner's word is a signature
        text = block('resposta', answer=answer)
        assert 'NÃO É ASSINATURA' in text and not (run_directory / 'owner_answer.txt').exists() and not (run_directory / 'signed_at_utc.txt').exists(), text[-800:]
    text = block('sign')
    assert 'PARADO: não há resposta de assinatura gravada' in text and not (run_directory / 'sign.json').exists() and not (out / 'DISPATCH.BOUND.json').exists()
    text = block('resposta')
    ran.append('resposta')
    assert 'resposta gravada: %s às 2026-' % MARKER_ANSWER in text and (run_directory / 'owner_answer.txt').read_text() == MARKER_ANSWER + '\n', text[-800:]
    once_more('resposta')
    text = block('sign')
    ran.append('sign')
    assert 'exit=0' in text and 'BOUND_NOT_DISPATCHED' in text and (run_directory / 'sign.json').is_file(), text[-800:]
    once_more('sign')
    text = block('check')
    ran.append('check')
    assert 'exit=0' in text and '"verdict": "VALID_WINDOW_OPEN"' in text and '"wrote_nothing": true' in text, text[-800:]
    text = block('publicar-ancora')
    ran.append('publicar-ancora')
    assert 'bound and signed, NOT dispatched' in text and (run_directory / 'anchor_publication_url.txt').is_file(), text[-800:]
    once_more('publicar-ancora')
    text = block('dispatcher-prepare')
    ran.append('dispatcher-prepare')
    assert 'exit=2 (2 é o esperado)' in text and 'AWAITING_PUBLICATION_NO_SPAWN' in text and (run_directory / 'dispatch-prepare.json').is_file(), text[-800:]
    assert 'prefixo de cache continuou vazio e foi removido' in text and not list(run_directory.glob('pycache-prefix.*')), text[-800:]
    once_more('dispatcher-prepare')
    text = block('check')          # after the claim exists the verdict and the exit code say so
    assert 'exit=1' in text and '"verdict": "VALID_ALREADY_PREPARED"' in text and '"attempt_phase": "PREPARED_AWAITING_PUBLICATION"' in text, text[-800:]
    text = block('achar-intent')          # before any publication: nothing found, nothing written
    ran.append('achar-intent')
    assert 'achados 0; publication_url.txt NÃO foi escrito' in text and not (run_directory / 'publication_url.txt').exists(), text[-800:]
    text = block('publicar-intent')
    ran.append('publicar-intent')
    assert 'publication_url https://github.com/' in text and (run_directory / 'publication_url.txt').is_file(), text[-800:]
    once_more('publicar-intent')
    once_more('achar-intent')
    wait_for_the_intent()
    text = block('id-e-hora')
    ran.append('id-e-hora')
    assert 'publication_ref 9' in text and (run_directory / 'published_at_utc.txt').is_file(), text[-800:]
    once_more('id-e-hora')
    # the fake gh gave a numeric id, as the real one does: on a rehearsal set the binder refuses it, and nothing is written
    text = block('publish-proof')
    assert 'exit=2' in text and 'REHEARSAL_SET_WITH_A_REAL_PUBLICATION' in text and not (run_directory / 'proof.json').exists() and not list(out.glob('PUBLICATION.PROOF*'))
    (run_directory / 'publication_ref.txt').write_text(MARKER_PUBLICATION + '\n')          # the only publication reference a rehearsal set takes
    transcript.append({'note': 'publication_ref.txt replaced by the rehearsal marker by the harness: the binder refuses a real comment id on a rehearsal set'})
    text = block('publish-proof')
    ran.append('publish-proof')
    assert 'exit=0' in text and 'PROOF_WRITTEN_NOT_DISPATCHED' in text and (run_directory / 'proof.json').is_file(), text[-800:]
    once_more('publish-proof')
    text = block('publicar-prova')
    ran.append('publicar-prova')
    assert 'publication proof written, resume NOT run' in text and (run_directory / 'proof_publication_url.txt').is_file(), text[-800:]
    once_more('publicar-prova')
    text = block('status')
    ran.append('status')
    assert 'exit=1' in text and 'PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN' in text and '"claim_root_read": "OF_THIS_DIRECTORY"' in text, text[-800:]
    text = block('arquivar')
    ran.append('arquivar')
    assert 'cópia idêntica' in text and '"bound_set_is_a_relocated_copy": true' in text and '"claim_root_read": "ORIGINAL_NAMED_ON_THE_SHEET"' in text, text[-800:]
    archived = workspace / 'rehearsal-archive' / ('once-' + LABEL)
    assert tree(archived / 'rehearsal-bound') == tree(out) and (archived / 'sign.json').is_file()
    assert not (out / '.dispatch-root' / (LABEL + '-once') / 'spawn.claim').exists()          # resume was never run
    # what was "published": four bodies, by the fake gh only, none with a value of the (fake) transport
    calls = stub_log.read_text().splitlines()
    assert len([row for row in calls if row.startswith('issue comment 429 --repo duduvcastro/c3po-chief-of-staff-intelligence --body-file ')]) == 4, calls
    config = json.loads((out / 'DISPATCH.BOUND.json').read_bytes())
    bodies = ''.join(path.read_text(encoding='utf-8') for path in sorted(run_directory.glob('publish-*.md')))
    assert len(list(run_directory.glob('publish-*.md'))) == 4 and all(value not in bodies for value in (
        config['target'], config['target'].split('@')[1], config['ssh_key']['path'], config['known_hosts']['path']))
    assert sorted(set(found) - set(ran)) == sorted(NOT_RUN)
    transcript.append({'note': 'blocks run literally: %s; not run (host, or by hand): %s; the gh of every `rede` block was the fake one of this workspace'
                               % (', '.join(ran), ', '.join(sorted(NOT_RUN)))})
    save()
    return {'blocks_run': ran, 'blocks_not_run': sorted(NOT_RUN), 'blocks_parsed_by_zsh_n': sorted(found), 'fake_gh_calls': len(calls), 'workspace': str(workspace)}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1], sys.argv[2]), indent=1))
