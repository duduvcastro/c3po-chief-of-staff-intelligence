"""Static pins of the K12 families (deselected in the mutation runs, like every test named "static"): the common block
of op.py is BLOCK of ../common_block.py and the same bytes in each sibling family present beside this one; the shared
test files are the same bytes in each sibling present. A private copy (a mutation run) has no siblings: then only the
block's own markers are checked."""
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
FAMILY=HERE.parent
ROOT=FAMILY.parent
FAMILIES=('k12_window','k12_collect','k12_preflight')
BEGIN='# ---- K12 COMMON BEGIN (written by ../common_block.py; the same bytes in k12_window, k12_collect, k12_preflight) ----\n'
END='# ---- K12 COMMON END ----\n'
SHARED=('k12emu.py','native_k12.py','native_support.py','request_document.py')

def block(path):
    text=path.read_text(encoding='ascii');assert text.count(BEGIN)==1 and text.count(END)==1
    return text.split(BEGIN,1)[1].split(END,1)[0]

def test_static_the_common_block_is_the_shared_one():
    own=block(FAMILY/'op.py');tool=ROOT/'common_block.py'
    if tool.is_file():
        spec=importlib.util.spec_from_file_location('_k12_common_block',tool);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        assert own==module.BLOCK and module.BEGIN==BEGIN and module.END==END
    for name in FAMILIES:
        other=ROOT/name/'op.py'
        if other.is_file():assert block(other)==own,name

def test_static_the_shared_test_files_are_the_same_bytes_in_each_family():
    for name in FAMILIES:
        for item in SHARED:
            other=ROOT/name/'tests'/item
            if other.is_file():assert other.read_bytes()==(HERE/item).read_bytes(),(name,item)
