"""Binder revision 4: the other sealed programs of the epoch (SEALED_PROGRAMS: K8, K12 p/w/c, K6b, K5, DBR, reader units,
K4 files, K3 secret.env, K13, K13r) and the second core of a sealed copy. Synthetic only; no host or Linux approval.

What is exercised: each directory in the explicit fixture snapshot (current K12 and a local K3 core candidate)
verified, its operation selected, its source loaded, and the core it names (the tier's core, or its own core directory for
K6b and K3) checked by the binder's hostops02_core with the core's own `assemble.py --check`; the common rule and the extra
rules on synthetic contexts with each program's own source module (every refusal code); the owner texts; sealed-copy with
two cores. NOT exercised: a prepare/sign of these programs end to end (their cited receipts would have to be produced by
their predecessors' emulated hosts, one chain per program): a stated gap (DESIGN_REV4.md)."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import types

import pytest

import helpers as h
from helpers import refused
import hostops02_fixtures as x

b = h.b
UTC = timezone.utc
PROGRAMS = Path(os.environ.get('BIND_TEST_PROGRAMS', str(h.BIND.parent / 'test-inputs' / 'programs-20261005T0215Z')))
DIRECTORIES = {'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01':'capacity_probe', 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01': 'k8_eve', 'GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01': 'k12_preflight',
               'GO_WRITE_HOSTOPS02_K12_WINDOW_01': 'k12_window', 'GO_READONLY_HOSTOPS02_K12_COLLECT_01': 'k12_collect',
               'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01': 'k6b', 'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01': 'supervisor_activate',
               'GO_READONLY_HOSTOPS02_DB_PRIV_01':'db_priv', 'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01': 'db_preflight', 'GO_WRITE_HOSTOPS02_READER_UNITS_01': 'reader_units',
               'GO_WRITE_HOSTOPS02_K4_FILES_01': 'k4_files', 'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01': 'k3_secret_env',
               'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01': 'k13_reader_switch', 'GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01': 'k13r_reader_liveness'}
OWN_CORE = {'k6b': 'core-k6b', 'k3_secret_env': 'core_k3'}
BOOT = 'b0' * 32
START = datetime(2026, 10, 5, 20, 38, tzinfo=UTC)          # seg 17:38 BRT


@pytest.fixture(scope='module')
def programs(tmp_path_factory):
    if not (PROGRAMS / 'k8_eve' / 'SHA256SUMS').is_file():
        pytest.skip('the snapshots of the sealed programs are not at hand')
    root = h.resolved(tmp_path_factory.mktemp('programs'))
    copy = x.sealed_copy(root / 'tier')
    for name in list(DIRECTORIES.values()) + list(OWN_CORE.values()):
        shutil.copytree(str(PROGRAMS / name), str(copy / name), symlinks=True, ignore=shutil.ignore_patterns('__pycache__'))
    accepted = json.loads((h.BIND / 'ACCEPTED_SEALS.json').read_bytes())['seals']
    core = [item['core'] for item in accepted if 'core' in item][0]
    extra = []
    for operation, name in DIRECTORIES.items():
        seal_core = dict(core)
        if name in OWN_CORE:
            directory = copy / OWN_CORE[name]
            seal_core = {'sha256sums_sha256': b.sha((directory / 'CORE_SHA256SUMS').read_bytes()), 'generation_sha256': b.sha((directory / 'assemble.py').read_bytes()),
                         'directory': OWN_CORE[name]}
        extra.append({'family': 'TEST_' + name.upper(), 'revision': 'SEALED', 'sha256sums_sha256': b.sha((copy / name / 'SHA256SUMS').read_bytes()), 'core': seal_core})
    modules = {}
    for operation, name in DIRECTORIES.items():
        family = b.verify_family(copy / name, accepted + extra)
        selected = b.select_operation(family, operation)
        modules[operation] = (family, selected, b.load_runtime(selected['files'], selected['source_name'], selected['directory']))
    return types.SimpleNamespace(copy=copy, accepted=accepted, extra=extra, modules=modules, root=root)


@pytest.fixture(autouse=True)
def program_seals(request, monkeypatch):
    if 'programs' not in request.fixturenames:
        return
    env = request.getfixturevalue('programs')
    original = b.binder_identity
    monkeypatch.setattr(b, 'k8_documents', lambda ctx: {'isolated_rule_fixture': True})
    monkeypatch.setattr(b, 'binder_identity', lambda: (original()[0], json.loads(json.dumps(original()[1])) + json.loads(json.dumps(env.extra))))


def seal_of(env, operation):
    family = env.modules[operation][0]
    return b.accepted_seal(env.accepted + env.extra, family['sums_sha256'])


def test_every_program_is_one_of_the_table_with_a_fixed_text(programs):
    assert set(DIRECTORIES) == set(b.SEALED_PROGRAMS) and all(operation in b.HOSTOPS02 and b.RULES_OF[operation] is b.sealed_program_rules for operation in DIRECTORIES)
    titles = [b.HOSTOPS02_TEXT_PT[operation][0] for operation in DIRECTORIES]
    assert len(set(titles)) == len(titles)
    for operation in DIRECTORIES:
        texts = b.HOSTOPS02_TEXT_PT[operation]
        assert len(texts) == 3 and all(line.isprintable() for part in texts for line in part.split('\n'))
        assert all(b.REAL_ANSWER.lower() not in part.lower() for part in texts) and (operation, None) in b.OUTCOME_TEXT_PT
        m = programs.modules[operation][2]['source']
        assert m.OPERATION == operation and (b.SEALED_PROGRAMS[operation]['container'] or True)
        assert ('GRAVAÇÃO' in texts[0] or 'SYSTEMCTL' in texts[0]) == bool(m.WRITES_ALLOWED)


def test_each_sealed_directory_and_the_core_it_names_check_with_the_binder(programs):
    """The tier's core for ten programs; its own core directory for K6b (core-k6b) and K3 (core_k3), named by the seal."""
    results = {}
    for operation, name in DIRECTORIES.items():
        family, selected, rt = programs.modules[operation]
        seal = seal_of(programs, operation)
        assert b.core_directory_of(seal) == OWN_CORE.get(name, 'core')
        try:
            core = b.hostops02_core(family, seal, selected, rt)
            results[name] = core['assembly_check']['answer']
        except b.Refused as error:
            results[name] = str(error)
    # A broken historical core is not an acceptable positive fixture.
    # The local K3 candidate passes integrity here; its independent approval remains pending.
    assert all(results[name] == 'BUILD_EQUAL' for name in DIRECTORIES.values()), results


def test_a_seal_naming_its_core_directory_is_valid_and_a_bad_name_is_not():
    assert b.core_directory_of({'core': {'sha256sums_sha256': 'a' * 64, 'generation_sha256': 'b' * 64}}) == 'core'
    assert b.core_directory_of({'core': {'directory': 'core-k6b'}}) == 'core-k6b'
    assert b.core_directory_of({'core': {'directory': '../core'}}) is None and b.core_directory_of({'core': {'directory': 'k6b'}}) is None


def test_sealed_copy_holds_a_second_core(programs, base, monkeypatch):
    """K6b with its own core beside the tier's: the copy holds core/ and core-k6b/, each with only its listed files."""
    k6b = [item for item in programs.extra if item['family'] == 'TEST_K6B'][0]
    monkeypatch.setattr(b, 'binder_identity', lambda: ({}, json.loads(json.dumps(programs.accepted)) + [k6b]))
    result = b.sealed_copy(Path(base) / 'copy', [str(PROGRAMS)] + [str(path) for path in x.sources()])
    assert {'core', 'core-k6b', 'k6b'} <= set(result['directories'])
    assert b.sha((Path(base) / 'copy' / 'core-k6b' / 'CORE_SHA256SUMS').read_bytes()) == k6b['core']['sha256sums_sha256']
    # two seals that name the same core directory with two different cores: refused
    clash = dict(k6b, core=dict(k6b['core'], directory='core'))
    monkeypatch.setattr(b, 'binder_identity', lambda: ({}, json.loads(json.dumps(programs.accepted)) + [clash]))
    with refused('SEALED_COPY_SOURCE_NOT_FOUND'):
        b.sealed_copy(Path(base) / 'copy2', [str(PROGRAMS)] + [str(path) for path in x.sources()])


def ctx_of(programs, operation, plan=None, receipts=None, facts=None, mode=b.REHEARSAL, params=None, start=START, minutes=6, copied=None):
    m = programs.modules[operation][2]['source']
    if receipts is None:
        receipts = {'R%d' % index: (needed, {'operation': needed, 'effects': {'evidence_boot_id_sha256': BOOT}})
                    for index, needed in enumerate(getattr(m, 'EVIDENCE_OPERATIONS', ()))}
    if plan is None:
        modes = b.sealed_program_modes(m)
        plan = {'evidence_boot_id_sha256': BOOT}
        if operation == 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01':
            plan['day'] = '2026-10-06'
        if operation == 'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01':plan['step']='CALENDAR'
        if modes is not None:
            plan['mode'] = modes[0]
        if operation == 'GO_READONLY_HOSTOPS02_K12_COLLECT_01':plan['mode']='TREE'
        if operation == 'GO_WRITE_HOSTOPS02_READER_UNITS_01':
            plan['units']=[{'key':key,'destination_name':name,'expect':'ABSENT'} for key,name in m.UNIT_ORDER]
    if operation == b.CAPACITY_SWITCH_OPERATION and receipts:
        activation = next((row for op,row in receipts.values() if op == b.ACTIVATE_OPERATION), None)
        if activation is not None:
            activation['effects'].update(data_root='/fixture/data',files=[{'key':'OVERRIDE','path':'/fixture/live/override.yml'}],
                recreate={'image_id':'sha256:'+'a'*64,'environment':{'A':'B'},'project':'fixture',
                          'env_file':'/fixture/.env','files':['/fixture/compose.yml','/fixture/live/override.yml']})
            plan.update(data_root='/fixture/data',worker={'image_id':'sha256:'+'a'*64},
                        override={'directory':[{'path':'/fixture/live'}],'name':'override.yml','environment':{'A':'B'}},
                        compose={'project':'fixture','env_file':'/fixture/.env','files':['/fixture/compose.yml']})
    if operation == 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01' and receipts:
        first = next(iter(receipts))
        receipt = receipts[first][1]
        receipt.update(mode='TREE', outcome=b.K9_TREE_OUTCOME, boot_id_sha256=BOOT,
                       items={'directory:DAYS': {'observed_rows': [{'device':1,'inode':2}]}})
        plan.setdefault('days_parent', [{'device':1,'inode':2}])
        receipts['COMMIT'] = (b.K9R_OPERATION, {'operation':b.K9R_OPERATION, 'mode':'RESULT',
            'k9_operation':'commit_result','day':'2026-10-06','phase_result':'COMPLETE',
            'outcome':'K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED','boot_id_sha256':BOOT})
    if operation == 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01' and copied is None and receipts:
        tree_role = next(role for role, (_, row) in receipts.items() if row.get('mode') == 'TREE')
        copied = [{'plan_pointer':'/days_parent','evidence_role':tree_role,'receipt_pointer':'/items/directory:DAYS/observed_rows'}]
    end = start + timedelta(minutes=minutes) - timedelta(seconds=1)
    return {'operation': operation, 'plan': plan, 'params': params if params is not None else {}, 'rt': {'source': m}, 'mode': mode,
            'request': {'writes_allowed': m.WRITES_ALLOWED}, 'window': {'start': start, 'end': end, 'gate_start': start, 'gate_end': end},
            'watchdog': 80, 'entries': [{'role': role, 'operation': op} for role, (op, _) in receipts.items()],
            'receipts': {role: receipt for role, (_, receipt) in receipts.items()},
            'evidence_facts': facts if facts is not None else [{'role': role, 'complete': True} for role in receipts], 'copied': copied or []}


def test_the_common_rule_passes_for_every_program(programs):
    for operation in DIRECTORIES:
        if operation in ('GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01', 'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01','GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01','GO_WRITE_HOSTOPS02_K12_WINDOW_01','GO_WRITE_HOSTOPS02_K4_FILES_01','GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01','GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01','GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01'):
            continue          # their first modes (ACTIVATE, PRIV) pass below with their extra rules
        rules = b.sealed_program_rules(ctx_of(programs, operation))['sealed_program']
        assert rules['program'] == b.SEALED_PROGRAMS[operation]['key'] and rules['sendable_seconds'] >= 180


def test_the_common_rule_refusals(programs):
    k12w = 'GO_WRITE_HOSTOPS02_K12_WINDOW_01'
    with refused('SEALED_PROGRAM_EVIDENCE_NOT_CITED'):
        b.sealed_program_rules(ctx_of(programs, k12w, receipts={}))
    with refused('SEALED_PROGRAM_EVIDENCE_NOT_COMPLETE'):
        ctx = ctx_of(programs, k12w)
        b.sealed_program_rules(dict(ctx, evidence_facts=[{'role': fact['role'], 'complete': False} for fact in ctx['evidence_facts']]))
    with refused('EVIDENCE_NOT_OF_THE_SAME_BOOT'):
        b.sealed_program_rules(ctx_of(programs, k12w, plan={'mode': 'LAUNCH', 'evidence_boot_id_sha256': 'c1' * 32}))
    with refused('SEALED_PROGRAM_MODE_INVALID'):
        b.sealed_program_rules(ctx_of(programs, k12w, plan={'mode': 'EXPLODE', 'evidence_boot_id_sha256': BOOT}))
    with refused('K9_SENDABLE_SECONDS_BELOW_180'):          # K6b starts a container: never 18:58:40-19:25:59 BRT
        b.sealed_program_rules(ctx_of(programs, 'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01', start=datetime(2026, 10, 5, 22, 0, tzinfo=UTC)))
    with refused('LINUX_JOB_RECORD_REQUIRED'):
        b.sealed_program_rules(ctx_of(programs, 'GO_WRITE_HOSTOPS02_K4_FILES_01', mode=b.REAL))
    b.sealed_program_rules(ctx_of(programs, 'GO_WRITE_HOSTOPS02_K4_FILES_01', mode=b.REAL, params={'linux_job': {}}))
    b.sealed_program_rules(ctx_of(programs, 'GO_READONLY_HOSTOPS02_DB_PRIV_01', mode=b.REAL))          # a read: no job record


def test_k5_reset_signs_an_invocation_copied_from_a_read(programs):
    k5 = 'GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01'
    m = programs.modules[k5][2]['source']
    b.sealed_program_rules(ctx_of(programs, k5, plan={'mode': 'ACTIVATE', 'evidence_boot_id_sha256': BOOT}))
    read = [operation for operation in m.EVIDENCE_OPERATIONS if operation.startswith('GO_READONLY_')][0]
    receipts = {'R%d' % index: (needed, {'operation': needed, 'effects': {'evidence_boot_id_sha256': BOOT}}) for index, needed in enumerate(m.EVIDENCE_OPERATIONS)}
    role = [role for role, (op, _) in receipts.items() if op == read][0]
    plan = {'mode': 'RESET', 'evidence_boot_id_sha256': BOOT, 'invocation_id': 'f' * 32}
    rules = b.sealed_program_rules(ctx_of(programs, k5, plan=plan, receipts=receipts, copied=[{'plan_pointer': '/invocation_id', 'evidence_role': role}]))
    assert rules['sealed_program']['extra'] == {'invocation_id_from': role}
    with refused('K5_INVOCATION_ID_NOT_COPIED_FROM_A_READ'):
        b.sealed_program_rules(ctx_of(programs, k5, plan=plan, receipts=receipts))
    write = [role for role, (op, _) in receipts.items() if not op.startswith('GO_READONLY_')][0]
    with refused('K5_INVOCATION_ID_NOT_COPIED_FROM_A_READ'):
        b.sealed_program_rules(ctx_of(programs, k5, plan=plan, receipts=receipts, copied=[{'plan_pointer': '/invocation_id', 'evidence_role': write}]))


def test_dbr_queries_sign_the_cited_priv_receipt(programs):
    dbr = 'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01'
    m = programs.modules[dbr][2]['source']
    for mode in ('PRIV',):
        with refused('DBR_SPLIT_PRIV_PROGRAM_REQUIRED'):
            b.dbr_rules(ctx_of(programs,dbr,plan={'mode':mode,'evidence_boot_id_sha256':BOOT}))
    privop = 'GO_READONLY_HOSTOPS02_DB_PRIV_01'
    priv = {'operation': privop, 'mode': 'PRIV', 'outcome': m.PRIV_COMPLETE_OUTCOME, 'metadata_sha256': 'd1' * 32, 'boot_id_sha256': BOOT,
            'observed_at': '2026-10-05T20:30:00+00:00', 'effects': {'evidence_boot_id_sha256': BOOT, 'mode': 'PRIV'}}
    receipts = {'R%d' % index: (needed, {'operation': needed, 'effects': {'evidence_boot_id_sha256': BOOT}}) for index, needed in enumerate(m.EVIDENCE_OPERATIONS)}
    receipts = {k:v for k,v in receipts.items() if v[0]!=privop}
    receipts['PRIV'] = (privop, priv)
    signed = {'operation': privop, 'mode': 'PRIV', 'outcome': m.PRIV_COMPLETE_OUTCOME, 'receipt_sha256': 'd1' * 32, 'observed_at': '2026-10-05T20:30:00+00:00',
              'boot_id_sha256': BOOT}
    plan = {'mode': 'QUERIES', 'evidence_boot_id_sha256': BOOT, 'priv_receipt': signed}
    assert b.dbr_priv_receipt_members(ctx_of(programs,dbr,plan=plan,receipts=receipts),privop) == {'priv_receipt_role': 'PRIV'}
    with refused('DBR_PRIV_RECEIPT_NOT_THE_CITED_ONE'):
        b.dbr_priv_receipt_members(ctx_of(programs,dbr,plan=dict(plan,priv_receipt=dict(signed,receipt_sha256='d2'*32)),receipts=receipts),privop)
    with refused('DBR_PRIV_RECEIPT_NOT_THE_CITED_ONE'):
        b.dbr_priv_receipt_members(ctx_of(programs,dbr,plan=plan,receipts=dict(receipts,PRIV=(privop,dict(priv,outcome='PARTIAL_OBSERVED')))),privop)
    without = {role: item for role, item in receipts.items() if role != 'PRIV'}
    with refused('DBR_PRIV_RECEIPT_NOT_CITED'):
        b.dbr_priv_receipt_members(ctx_of(programs,dbr,plan=plan,receipts=without),privop)
    # a cited PRIV receipt is complete by its own mode's outcome (the program's success_of on the signed mode)
    source = programs.modules[privop][2]['source']
    assert b.success_of_the_signed_mode(source, priv, source.COMPLETE_OUTCOME) == m.PRIV_COMPLETE_OUTCOME

    # Member checking does not approve the combined family above or invent the future PRIV operation.
    old=dict(priv,observed_at='2026-10-04T20:30:00+00:00')
    old_plan=dict(plan,priv_receipt=dict(signed,observed_at=old['observed_at']))
    with refused('DBR_PRIV_NOT_OF_THE_SAME_UTC_DAY'):
        b.dbr_priv_receipt_members(ctx_of(programs,dbr,plan=old_plan,receipts=dict(receipts,PRIV=(privop,old))),privop)


def test_the_effects_lines_and_the_question_of_a_sealed_program(programs):
    effects = {'operation': 'GO_WRITE_HOSTOPS02_K4_FILES_01', 'mode': 'PINS', 'activation': False,
               'files': [{'key': 'PINS', 'path': '/var/lib/c3po-capacity/config/pins.env', 'mode_octal': '0600', 'expect': 'ABSENT', 'sha256': 'e' * 64, 'bytes': 120}],
               'config_parent': {'path': '/var/lib/c3po-capacity/config', 'rows': [{'device': 1, 'inode': 99}]}}
    lines = b.hostops02_effects_lines({'operation': 'GO_WRITE_HOSTOPS02_K4_FILES_01'}, effects, {})
    assert lines[0] == '- programa K4, modo PINS' and any('/var/lib/c3po-capacity/config/pins.env' in line and 'mode_octal 0600' in line for line in lines)
    assert all('inode' not in line for line in lines) and lines[-1].endswith('EFFECTS.json')


def test_new_family_contract_is_derived_only_from_sealed_runtime_and_fixed_owner_text(programs):
    operation = 'GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01'
    family, selected, runtime = programs.modules[operation]
    assert 'CONTRACT.txt' not in family['files']
    document = {'schema': 'CODEX_FIXED_BINDING_CONTRACT_01', 'operation': operation,
                'runtime_sha256': b.strict_json(selected['files']['DISPATCH.UNBOUND.json'], 'TEST')['runtime_sha256'],
                'owner_text_pt': b.HOSTOPS02_TEXT_PT[operation], 'outcome_text_pt': b.OUTCOME_TEXT_PT[(operation, None)]}
    assert selected['contract_sha256'] == b.sha(b.canonical(document))


def test_missing_contract_is_still_refused_for_old_families(programs):
    core_families = json.loads((h.BIND / 'ACCEPTED_SEALS.json').read_bytes())['seals']
    operation = b.CATALOG_OPERATION
    family = b.verify_family(programs.copy / 'catalog_init', core_families)
    files = dict(family['files']); del files['CONTRACT.txt']
    with refused('FAMILY_FILE_SET'):
        b.select_operation(dict(family, files=files), operation)

@pytest.mark.parametrize('operation',sorted(DIRECTORIES))
def test_each_family_rejects_a_required_receipt_from_another_boot(programs,operation):
    ctx=ctx_of(programs,operation)
    if not ctx['receipts']:
        # The readonly collector has no required predecessor, but a cited receipt must still match boot.
        ctx['receipts']['EXTRA']={'operation':operation,'effects':{'evidence_boot_id_sha256':BOOT}}
    role=next(iter(ctx['receipts']))
    ctx['receipts'][role]['effects']['evidence_boot_id_sha256']='c1'*32
    with refused('EVIDENCE_NOT_OF_THE_SAME_BOOT'):
        b.sealed_program_rules(ctx)

@pytest.mark.parametrize('operation',sorted(set(DIRECTORIES)-{'GO_READONLY_HOSTOPS02_K12_COLLECT_01','GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01'}))
def test_each_family_rejects_missing_required_receipt(programs,operation):
    ctx=ctx_of(programs,operation)
    assert ctx['entries']
    ctx['entries']=[];ctx['receipts']={};ctx['evidence_facts']=[]
    with refused('SEALED_PROGRAM_EVIDENCE_NOT_CITED'):
        b.sealed_program_rules(ctx)

@pytest.mark.parametrize('operation',sorted(set(DIRECTORIES)-{'GO_READONLY_HOSTOPS02_K12_COLLECT_01','GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01'}))
def test_each_family_rejects_incomplete_required_evidence(programs,operation):
    ctx=ctx_of(programs,operation)
    assert ctx['evidence_facts']
    ctx['evidence_facts'][0]['complete']=False
    with refused('SEALED_PROGRAM_EVIDENCE_NOT_COMPLETE'):
        b.sealed_program_rules(ctx)


@pytest.mark.parametrize('operation', sorted(set(DIRECTORIES)-{'GO_READONLY_HOSTOPS02_K12_COLLECT_01','GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01'}))
def test_required_evidence_without_boot_cannot_release_a_dependent(programs, operation):
    ctx = ctx_of(programs, operation)
    first = next(iter(ctx['receipts'].values()))
    first['effects'].pop('evidence_boot_id_sha256')
    first.pop('boot_id_sha256', None)
    with refused('SEALED_PROGRAM_EVIDENCE_BOOT_UNKNOWN'):
        b.sealed_program_rules(ctx)


@pytest.mark.parametrize('start,end,accepted', [
    ('2026-10-05T20:38:00+00:00','2026-10-05T23:55:00+00:00',True),
    ('2026-10-05T20:37:59+00:00','2026-10-05T20:45:00+00:00',False),
    ('2026-10-05T23:50:00+00:00','2026-10-05T23:55:01+00:00',False),
    ('2026-10-06T00:00:00+00:00','2026-10-06T00:06:00+00:00',False),
])
def test_k8_e6_does_not_inherit_after_2100_spare(start,end,accepted):
    ctx = {'plan': {'day': '2026-10-06'}, 'window': {'start':datetime.fromisoformat(start),'end':datetime.fromisoformat(end)}}
    if accepted:
        assert b.k8_e6_band(ctx)['spare_after_2100_authorized'] is False
    else:
        with refused('K8_E6_WINDOW_OUTSIDE_A2_BAND'):
            b.k8_e6_band(ctx)


def test_k8_tree_and_commit_are_distinct_cited_reads(programs):
    operation = 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'
    ctx = ctx_of(programs, operation)
    assert b.k8_rules(ctx)['commit_result_role'] == 'COMMIT'
    ctx['plan']['days_parent'] = [{'device':1,'inode':3}]
    with refused('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT'):
        b.k8_rules(ctx)


@pytest.mark.parametrize('case', ['absent','partial','other_day','other_step'])
def test_k8_does_not_deliver_without_this_days_complete_commit(programs, case):
    ctx = ctx_of(programs, 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01')
    commit = ctx['receipts']['COMMIT']
    code = 'K8_COMMIT_RESULT_NOT_CITED'
    if case == 'absent':
        del ctx['receipts']['COMMIT']
        ctx['entries'] = [e for e in ctx['entries'] if e['role'] != 'COMMIT']
    elif case == 'partial':
        commit['phase_result'] = 'UNCERTAIN'
        code = 'K8_COMMIT_RESULT_NOT_COMPLETE'
    elif case == 'other_day':
        commit['day'] = '2026-10-07'
    else:
        commit['k9_operation'] = 'collect_result'
    with refused(code):
        b.k8_rules(ctx)


def test_k8_input_bytes_hashes_and_sizes_must_all_be_computed_from_files():
    operation = 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'
    plan = {'files': {'template':{}, 'capacity_config:regular':{}}}
    required = b.input_members(operation,plan)
    assert len(required) == 9
    used = [{'plan_pointer':pointer,'input':name,'as':form} for pointer,(name,form) in required.items()]
    b.required_inputs(used, required)
    for omitted in range(len(used)):
        with refused('PLAN_MEMBER_NOT_FROM_ITS_INPUT_FILE'):
            b.required_inputs(used[:omitted]+used[omitted+1:], required)


def test_k8_thirteen_input_limit_is_specific_and_excess_names_refused(tmp_path):
    operation = 'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'
    allowed = b.HOSTOPS02[operation]['inputs']
    assert len(allowed) == 13
    path = tmp_path/'input.json'
    path.write_bytes(b'{}')
    inputs = {name:str(path) for name in allowed}
    assert len(b.load_inputs({'inputs':inputs},tmp_path,allowed)) == 13
    with refused('BIND_INPUTS_INVALID'):
        b.load_inputs({'inputs':dict(inputs, extra=str(path))},tmp_path,allowed)
    with refused('BIND_INPUTS_INVALID'):
        b.load_inputs({'inputs':inputs},tmp_path,('release',))


def test_k8_invalid_session_day_is_refused():
    with refused('K8_SESSION_DAY_INVALID'):
        b.k8_e6_band({'plan':{'day':'not-a-day'},'window':{}})


@pytest.mark.parametrize('kind',['absent','duplicate','partial'])
def test_k8_requires_exactly_one_complete_tree(programs,kind):
    ctx=ctx_of(programs,'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01')
    role=next(e['role'] for e in ctx['entries'] if ctx['receipts'][e['role']].get('mode')=='TREE')
    if kind=='absent':ctx['entries']=[e for e in ctx['entries'] if e['role']!=role]
    elif kind=='duplicate':
        ctx['entries'].append({'role':'EXTRA_TREE','operation':b.K9R_OPERATION})
        ctx['receipts']['EXTRA_TREE']=dict(ctx['receipts'][role])
    else:ctx['evidence_facts']=[dict(f,complete=False) if f['role']==role else f for f in ctx['evidence_facts']]
    with refused('K8_TREE_NOT_ONE_COMPLETE_READ'):b.k8_rules(ctx)


@pytest.mark.parametrize('files',[None,{'bad/name':{}},{'bad~name':{}}])
def test_k8_invalid_delivery_input_shape_refused(files):
    with refused('PLAN_DELIVERY_INPUTS_INVALID'):
        b.input_members('GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01',{'files':files})


@pytest.mark.parametrize('bad',['typed','wrong_rows','partial','unknown_boot'])
def test_host_identity_provenance_refuses_unproved_or_typed_rows(bad):
    row={'device':1,'inode':2,'uid':0,'gid':0,'mode':0o700}
    receipt={'rows':[dict(row)],'boot_id_sha256':BOOT}
    ctx={'plan':{'unit_rows':[row],'evidence_boot_id_sha256':BOOT},'receipts':{'READ':receipt},
         'evidence_facts':[{'role':'READ','complete':True}],
         'copied':[{'plan_pointer':'/unit_rows','evidence_role':'READ','receipt_pointer':'/rows'}]}
    if bad=='typed':ctx['copied']=[]
    elif bad=='wrong_rows':receipt['rows'][0]['inode']=3
    elif bad=='partial':ctx['evidence_facts'][0]['complete']=False
    else:receipt.pop('boot_id_sha256')
    with refused('SEALED_HOST_IDENTITY_NOT_FROM_PROVED_RECEIPT'):b.sealed_metadata_provenance(ctx)


def test_whole_chain_copy_proves_each_host_identity():
    rows=[{'device':1,'inode':2},{'device':1,'inode':3}]
    ctx={'plan':{'nested':{'rows':rows},'evidence_boot_id_sha256':BOOT},
         'receipts':{'READ':{'observed':rows,'boot_id_sha256':BOOT}},'evidence_facts':[{'role':'READ','complete':True}],
         'copied':[{'plan_pointer':'/nested/rows','evidence_role':'READ','receipt_pointer':'/observed'}]}
    assert b.sealed_metadata_provenance(ctx)==[{'plan_pointer':'/nested/rows/0','evidence_role':'READ'},
                                             {'plan_pointer':'/nested/rows/1','evidence_role':'READ'}]


def test_k6b_activation_members_must_match(programs):
    ctx=ctx_of(programs,b.CAPACITY_SWITCH_OPERATION)
    assert b.capacity_switch_rules(ctx)['activation_role']
    for field,value in [('data_root','/other'),('worker',{'image_id':'sha256:'+'c'*64}),
                        ('compose',{'project':'other'}),('override',{'environment':{'A':'X'}})]:
        changed=dict(ctx,plan=dict(ctx['plan'],**{field:value}))
        with refused('K6B_ACTIVATION_MEMBERS_NOT_THE_CITED_ONES'):b.capacity_switch_rules(changed)


def capacity_load_ctx(programs,enable=False):
    operation=b.CAPACITY_SWITCH_OPERATION if enable else b.CAPACITY_PROBE_OPERATION
    ctx=ctx_of(programs,operation)
    mount={'mode':'MOUNT','metadata_sha256':'d1'*32,'effects':{'evidence_boot_id_sha256':BOOT},
           'clock':{'utc_end':'2026-10-05T20:20:00+00:00'}}
    load={'step':'LOAD','metadata_sha256':'d2'*32,'effects':{'evidence_boot_id_sha256':BOOT,
          'load':{'mount_receipt':{'receipt_sha256':'d1'*32}}},
          'clock':{'utc_start':'2026-10-05T20:21:00+00:00','utc_end':'2026-10-05T20:25:00+00:00'}}
    ctx['receipts'].update(MOUNT=mount,LOAD=load)
    ctx['entries'] += [{'role':'MOUNT','operation':b.CAPACITY_SWITCH_OPERATION},
                      {'role':'LOAD','operation':b.CAPACITY_PROBE_OPERATION}]
    ctx['evidence_facts'] += [{'role':r,'complete':True} for r in ('MOUNT','LOAD')]
    if enable:ctx['plan'].update(mode='ENABLE',probe_load_receipt_sha256='d2'*32)
    else:ctx['plan'].update(step='LOAD',load={'mount_receipt_sha256':'d1'*32})
    return ctx


@pytest.mark.parametrize('enable',[False,True])
def test_capacity_mount_load_enable_chain_is_exact(programs,enable):
    ctx=capacity_load_ctx(programs,enable)
    rule=b.capacity_switch_rules if enable else b.capacity_probe_rules
    assert rule(ctx)['mount_role']=='MOUNT'


@pytest.mark.parametrize('case',['missing','partial','boot','hash','clock'])
@pytest.mark.parametrize('enable',[False,True])
def test_capacity_load_chain_refuses_missing_or_uncertain_proof(programs,case,enable):
    ctx=capacity_load_ctx(programs,enable)
    rule=b.capacity_switch_rules if enable else b.capacity_probe_rules
    role='LOAD' if enable else 'MOUNT'
    if case=='missing':ctx['entries']=[e for e in ctx['entries'] if e['role']!=role]
    elif case=='partial':next(f for f in ctx['evidence_facts'] if f['role']==role)['complete']=False
    elif case=='boot':ctx['receipts'][role]['effects'].pop('evidence_boot_id_sha256')
    elif case=='hash':ctx['receipts'][role]['metadata_sha256']='d3'*32
    else:ctx['receipts'][role]['clock']={}
    code = ('K6B_LOAD_NOT_COMPLETE_CITED' if enable else 'PROBE_MOUNT_NOT_COMPLETE_CITED') if case in ('missing','partial','boot') else (('K6B_LOAD_HASH_NOT_CITED' if enable else 'PROBE_MOUNT_HASH_NOT_CITED') if case=='hash' else ('K6B_LOAD_NOT_FINISHED_BEFORE_ENABLE' if enable else 'PROBE_MOUNT_NOT_FINISHED_BEFORE_LOAD'))
    with refused(code):rule(ctx)


@pytest.mark.parametrize('step',['CALENDAR','IDENT'])
def test_enable_does_not_accept_a_read_instead_of_load(programs,step):
    ctx=capacity_load_ctx(programs,True);ctx['receipts']['LOAD']['step']=step
    with refused('K6B_LOAD_NOT_COMPLETE_CITED'):b.capacity_switch_rules(ctx)


def test_probe_complete_outcome_is_the_signed_step(programs):
    m=programs.modules[b.CAPACITY_PROBE_OPERATION][2]['source']
    for step in ('CALENDAR','IDENT','LOAD'):
        assert b.success_of_the_signed_mode(m,{'operation':b.CAPACITY_PROBE_OPERATION,'effects':{'step':step}},m.COMPLETE_OUTCOME)==m.success_of({'step':step})


def test_probe_outside_its_signed_band_is_a_closed_refusal(programs):
    ctx=ctx_of(programs,b.CAPACITY_PROBE_OPERATION,start=datetime(2026,10,5,20,37,tzinfo=UTC))
    with refused('PROBE_WINDOW_OUTSIDE_SIGNED_BAND'):b.capacity_probe_rules(ctx)


def test_concatenated_host_chains_keep_each_receipt_identity_provenance():
    rows=[{'device':1,'inode':2},{'device':1,'inode':3},{'device':1,'inode':4}]
    receipts={'A':{'rows':rows[:2],'boot_id_sha256':BOOT},'B':{'rows':rows[2:],'boot_id_sha256':BOOT}}
    copied=[]
    resolver={'inputs':{},'used':[],'copied':copied,'receipts':receipts,'operations':{}}
    value={'$concat':[{'$from':{'evidence':'A','pointer':'/rows'}},{'$from':{'evidence':'B','pointer':'/rows'}}]}
    resolved=b.resolve_hostops02(value,resolver,'/chain')
    ctx={'plan':{'chain':resolved,'evidence_boot_id_sha256':BOOT},'receipts':receipts,'copied':copied,
         'evidence_facts':[{'role':r,'complete':True} for r in receipts]}
    assert [r['evidence_role'] for r in b.sealed_metadata_provenance(ctx)]==['A','A','B']
    resolved[-1]['inode']=9
    with refused('SEALED_HOST_IDENTITY_NOT_FROM_PROVED_RECEIPT'):b.sealed_metadata_provenance(ctx)


def test_enable_mount_link_and_order_are_not_inferred(programs):
 ctx=capacity_load_ctx(programs,True)
 ctx['receipts']['LOAD']['effects']['load']['mount_receipt']['receipt_sha256']='a1'*32
 with refused('K6B_LOAD_MOUNT_LINK_INVALID'):b.capacity_switch_rules(ctx)
 ctx['receipts']['LOAD']['effects']['load']['mount_receipt']['receipt_sha256']='d1'*32
 ctx['receipts']['MOUNT']['clock']['utc_end']='2026-10-05T20:22:00+00:00'
 with refused('K6B_MOUNT_NOT_FINISHED_BEFORE_LOAD'):b.capacity_switch_rules(ctx)


def test_probe_unknown_step_is_not_load_or_identity(programs):
 ctx=ctx_of(programs,b.CAPACITY_PROBE_OPERATION);ctx['plan']['step']='OTHER'
 with refused('PROBE_STEP_INVALID'):b.capacity_probe_rules(ctx)
