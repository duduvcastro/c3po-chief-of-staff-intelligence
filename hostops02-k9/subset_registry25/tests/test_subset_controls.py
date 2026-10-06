"""Controles locais da provaSUBSET; copias privadas, nenhum prepare/GO/host."""
from pathlib import Path
import importlib.util,sys
import pytest
PACKAGE=Path(__file__).resolve().parent.parent

def helper():
    spec=importlib.util.spec_from_file_location('_subset_controls_helper',PACKAGE/'prove_subset_registry25.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def clone(tmp_path):
    package=tmp_path/'package';(package/'selector').mkdir(mode=0o700,parents=True)
    for name in ('bind_once.py','ACCEPTED_SEALS.json'):
        (package/'selector'/name).write_bytes((PACKAGE/'selector'/name).read_bytes());(package/'selector'/name).chmod(0o600)
    return package

@pytest.mark.parametrize('name,code',[('bind_once.py','BINDER_EXTERNAL_PIN'),('ACCEPTED_SEALS.json','REGISTRY_EXTERNAL_PIN')])
def test_source_and_registry_tampering_refuse_before_compiling_or_selecting(tmp_path,name,code):
    h=helper();p=clone(tmp_path);file=p/'selector'/name;file.write_bytes(file.read_bytes()+b'\nSYNTHETIC_MUTATION\n')
    with pytest.raises(h.ProofRefused,match='^'+code+'$'):h.load_binder(p)

def test_binder_identity_uses_retained_pinned_buffers_after_disk_tamper(tmp_path):
    h=helper();p=clone(tmp_path);m,rows=h.load_binder(p)
    (p/'selector/ACCEPTED_SEALS.json').write_bytes(b'{}\n');(p/'selector/bind_once.py').write_bytes(b'SYNTHETIC_INVALID_CODE!\n')
    identity,seen=m.binder_identity()
    assert identity=={'binder_sha256':h.SOURCE_SHA256,'accepted_seals_sha256':h.REGISTRY_SHA256}
    assert seen==rows and len(seen)==25

def test_full_real_registry_has_exact_three_unique_subset_families_and_cores(tmp_path):
    h=helper();m,rows=h.load_binder(clone(tmp_path));selected,cores=h.subset_rows(m,rows)
    assert len(rows)==25 and len(selected)==len(cores)==3
    assert {row['family'] for row,_ in selected}=={row[0] for row in h.SUBSET}
    assert set(cores)=={'core_bootstrap_identity','core_k3k9','core_k3'}

@pytest.mark.parametrize('change',['absent','duplicate'])
def test_real_lookup_refuses_missing_or_ambiguous_BOOT_row_DTO(tmp_path,change):
    h=helper();m,rows=h.load_binder(clone(tmp_path));boot=next(row for row in rows if row['family']==h.SUBSET[0][0])
    dto=[r for r in rows if r is not boot] if change=='absent' else rows+[boot]
    with pytest.raises(m.Refused,match='^FAMILY_SEAL_NOT_ACCEPTED$'):m.accepted_seal(dto,h.SUBSET[0][2])

def test_proof_refuses_output_inside_input_before_creating_it(tmp_path,monkeypatch):
    h=helper();p=clone(tmp_path);out=p/'must-not-exist'
    monkeypatch.setattr(sys,'argv',['prove_subset_registry25.py','--python',sys.executable,'--package',str(p),'--evidence-out',str(out)])
    with pytest.raises(h.ProofRefused,match='^OUTPUT_INSIDE_INPUT$'):h.main()
    assert not out.exists()
