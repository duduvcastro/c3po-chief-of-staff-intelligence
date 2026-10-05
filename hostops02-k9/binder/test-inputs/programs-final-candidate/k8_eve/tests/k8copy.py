"""The one function K8 copies from the frozen core, and the mechanical rule that makes the copy.

The core's create_file (parts/files.py) admits a final name only of the grammar FILE_NAME, which has no '='. Every name
the capacity loader reads has one ('session=<day>.json', 'session=<day>.admission.json', ...: r2d2_v2_capacity_wiring.py
reads them by those fixed names), so create_file cannot deliver them, and the core is frozen. K8's own part therefore
carries k8_create_file: the core's create_file with exactly three changes, made by derived() below and nothing else:
  1. its name and its docstring;
  2. the request check calls k8_named_in (K8's name rule: 'session=<date>...' names, see op.py) instead of named_in;
  3. nine local names renamed (entry, failed, withdrawn, temp, flags, info, named, written, size get the prefix 'k8'),
     so that each line of the copy is text of its own and the core's mutants of create_file can be applied to it.
tests/test_k8_copy.py compares the function in build/k8_eve.py with derived(core files.py) byte for byte, and
mutation/mutants.py ports the core's create_file mutants through port()."""
import re

RENAMES=('entry','failed','withdrawn','temp','flags','info','named','written','size')
CORE_DOC=('    """One file: exclusive temporary, unbuffered writes, fsync, exact metadata, link to the final name, fsync of the\n'
          '    directory, removal of the temporary. Returns the ledger row. Nothing is repaired and nothing raises past here.\n'
          '    The caller has set the umask so that mode survives it (0077 for 0600, 0022 for 0644) and has proved the final\n'
          '    name absent; a name that appears afterwards is left alone (a link never replaces anything)."""\n')
K8_DOC=('    """The core\'s create_file (parts/files.py of generation 4c24c5cf...) for the capacity loader\'s names, which hold\n'
        '    an \'=\' that the core\'s FILE_NAME refuses. Derived mechanically (tests/k8copy.py): this docstring, k8_named_in for\n'
        '    named_in, and nine local names prefixed k8. Same states, codes, calls and order as the core\'s function."""\n')

def source_of(text,name):
    """The text of one top-level function: from its 'def' line to the next top-level statement, without the blank
    lines that separate the two."""
    start=text.index('\ndef '+name+'(')+1
    match=re.search(r'\n(?=\S)',text[start:])
    return (text[start:start+match.start()+1] if match else text[start:]).rstrip()+'\n'

def rename(text):
    for word in RENAMES:text=re.sub(r'\b%s\b'%word,'k8'+word,text)
    return text

def derived(files_text):
    body=source_of(files_text,'create_file')
    assert body.count(CORE_DOC)==1 and body.count('named_in(path,directory)')==1
    body=body.replace('def create_file(','def k8_create_file(',1).replace(CORE_DOC,K8_DOC,1).replace('named_in(path,directory)','k8_named_in(path,directory)',1)
    return rename(body)

def port(anchor):
    """A core mutant's anchor or replacement as it reads in the copy."""
    return rename(anchor.replace('named_in(path,directory)','k8_named_in(path,directory)'))
