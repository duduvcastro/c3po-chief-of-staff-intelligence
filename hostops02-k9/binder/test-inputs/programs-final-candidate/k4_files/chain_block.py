"""The compiled blocks of op.py, written and checked by command (never typed): the seven chain documents and the
capacity day's manifest writer (mode WRITER).

  chain_block.py check [CHAIN_ROOT]   exit 0 and CHAIN_BLOCK_EQUAL when the block between the two marker lines of op.py
                                      is exactly what the seven files under CHAIN_ROOT give, CHAIN_BLOCK_DIFFERS otherwise
  chain_block.py write [CHAIN_ROOT]   (author only) rewrites that block of op.py from the files

CHAIN_ROOT defaults to $HOSTOPS02_ACTB_DIRECTORY, else W/fable-actb03-20261004 with W the directory two levels above
this file (the signed Act B chain: act_a/ holds the three Act A signatures,
chain/ the Act B document and the three B approvals; DURABLE_SHA256SUMS.20261004T171741Z names every hash). The
labels, the order and the delivered file names are those of the documents tool (CHAIN in capacity_day_documents.py)
and of the Act B tools (CHAIN_NAMES in tools/actb03_lib.py). The writer block: its decoded bytes must hash to
WRITER_SHA256, the hash the capacity-day README names for manifest_writer.py; when $HOSTOPS02_OPSART_DIRECTORY names a
checkout of that repository, the block is also rebuilt from c3po/deployment/capacity-day/manifest_writer.py and the
README there must name the same hash (`write` requires it). Offline; reads only; writes op.py only with `write`."""
import base64
import hashlib
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
import os
DEFAULT=Path(os.environ.get('HOSTOPS02_ACTB_DIRECTORY') or HERE.parent.parent/'fable-actb03-20261004')
BEGIN='# ---- CHAIN BLOCK BEGIN (written by chain_block.py from the signed chain; never edited by hand) ----\n'
END='# ---- CHAIN BLOCK END ----\n'
CHAIN=(('CODEX','act_a','CODEX_ORDEM_EPOCA_03_SIGNATURE.rev2.json'),('FABLE','act_a','FABLE_ORDEM_EPOCA_03_SIGNATURE.rev2.json'),
       ('DUDU','act_a','DUDU_ORDEM_EPOCA_03_SIGNATURE.rev2.json'),('ACT_B','chain','ADENDO_EPOCA_03.md'),
       ('B_CODEX','chain','B_CODEX_ADENDO_EPOCA_03.md'),('B_FABLE','chain','B_FABLE_ADENDO_EPOCA_03.md'),
       ('B_DUDU','chain','B_DUDU_ADENDO_EPOCA_03.md'))
WIDTH=96
WRITER_SHA256='aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387'     # capacity-day README, "The script hash"
OPSART=os.environ.get('HOSTOPS02_OPSART_DIRECTORY')
WRITER_FILE=Path(OPSART)/'c3po'/'deployment'/'capacity-day'/'manifest_writer.py' if OPSART else None
WRITER_README=WRITER_FILE.parent/'README.md' if OPSART else None
WBEGIN='# ---- WRITER BLOCK BEGIN (written by chain_block.py from the reviewed manifest_writer.py; never edited by hand) ----\n'
WEND='# ---- WRITER BLOCK END ----\n'

def compiled_writer(text):
    """The writer block as it stands in op.py, decoded (raises unless its bytes hash to WRITER_SHA256)."""
    head,rest=text.split(WBEGIN,1);block,_=rest.split(WEND,1);scope={}
    exec(compile(block,'<writer block>','exec'),scope);digest,size,encoded=scope['K4_WRITER']
    raw=base64.b64decode(encoded,validate=True)
    if not (digest==WRITER_SHA256==hashlib.sha256(raw).hexdigest() and size==len(raw)):raise SystemExit('WRITER_BLOCK_NOT_THE_README_HASH')
    return WBEGIN+block+WEND

def writer_block(text):
    if not OPSART:return compiled_writer(text)
    raw=WRITER_FILE.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=WRITER_SHA256 or digest not in WRITER_README.read_text():raise SystemExit('WRITER_NOT_THE_README_HASH')
    encoded=base64.b64encode(raw).decode('ascii');pieces=[encoded[index:index+WIDTH] for index in range(0,len(encoded),WIDTH)]
    return WBEGIN+'K4_WRITER=(%r,%d,\n    (' % (digest,len(raw))+'\n     '.join("'%s'"%piece for piece in pieces)+'))\n'+WEND

def block(root):
    lines=[BEGIN,'K4_CHAIN_DOCUMENTS=(\n']
    for label,folder,name in CHAIN:
        raw=(root/folder/name).read_bytes();encoded=base64.b64encode(raw).decode('ascii')
        lines.append("    (%r,%r,%r,%d,\n"%(label,name,hashlib.sha256(raw).hexdigest(),len(raw)))
        pieces=[encoded[index:index+WIDTH] for index in range(0,len(encoded),WIDTH)]
        lines.append('     (')
        lines.append('\n      '.join("'%s'"%piece for piece in pieces))
        lines.append(')),\n')
    lines.append(')\n');lines.append(END)
    return ''.join(lines)

def current():
    text=(HERE/'op.py').read_text(encoding='ascii')
    head,rest=text.split(BEGIN,1);_,tail=rest.split(END,1)
    return text,head,tail

def replaced(text,begin,end,block):
    head,rest=text.split(begin,1);_,tail=rest.split(end,1);return head+block+tail

def main(argv):
    mode=argv[0] if argv else '';root=Path(argv[1]) if len(argv)>1 else DEFAULT
    if mode not in ('check','write') or len(argv)>2:
        print(__doc__);return 2
    text,head,tail=current()
    if mode=='write' and not OPSART:raise SystemExit('write needs HOSTOPS02_OPSART_DIRECTORY')
    wanted=replaced(head+block(root)+tail,WBEGIN,WEND,writer_block(text))
    if mode=='check':
        print('CHAIN_BLOCK_EQUAL' if wanted==text else 'CHAIN_BLOCK_DIFFERS');return 0 if wanted==text else 1
    (HERE/'op.py').write_text(wanted,encoding='ascii');print('CHAIN_BLOCK_WRITTEN');return 0

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
