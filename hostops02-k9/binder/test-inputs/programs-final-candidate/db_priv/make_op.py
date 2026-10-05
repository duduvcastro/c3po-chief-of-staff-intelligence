"""Writes op.py of DBR from three readable pieces: op_head.py.txt, snippet.py (the pinned snippet, carried verbatim as
a raw string constant DBR_SNIPPET) and op_tail.py.txt. Offline; run by the author after any change to one of them.
tests/test_dbr.py checks that op.py is exactly this composition."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def compose():
    snippet=(HERE/'snippet.py').read_text(encoding='ascii')
    assert "'''" not in snippet and '# ==== ' not in snippet and snippet.endswith('\n')
    return ((HERE/'op_head.py.txt').read_text(encoding='ascii')+"DBR_SNIPPET=r'''"+snippet+"'''.encode('ascii')\n"
            +(HERE/'op_tail.py.txt').read_text(encoding='ascii'))
if __name__=='__main__':(HERE/'op.py').write_text(compose(),encoding='ascii');print('OP_WRITTEN')
