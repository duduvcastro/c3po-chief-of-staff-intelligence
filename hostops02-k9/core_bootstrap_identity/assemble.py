"""Offline deterministic assembly of ONE hostops02 operation from the frozen core. No host, no network, no credential, no launch.

  assemble.py <operation directory>           (re)writes <operation directory>/build/
  assemble.py --check <operation directory>   exit 1 unless build/ holds exactly the bytes that would be written
  assemble.py --core                          verifies the frozen core and prints its generation hash

The operation directory holds two files written by the operation's author (CORE.md, "How an operation plugs in"):
  spec.py   NAME, MODULE, STEM, PARTS, HEADER, unbound_plan(module)
  op.py     the operation's own part
and everything in build/ is a function of those two files and of this core:
  build/<MODULE>.py        the ONE payload source: header + seal + shared parts + the operation's part, in a fixed order
  build/dispatch_once.py   reviewed_base/dispatch_once.py with the family's table of literal substitutions
  build/launcher_stdin.py  reviewed_base/launcher_stdin.py with five literal substitutions (the hostops01 launcher, byte for byte)
  build/transport_once.py  reviewed_base/transport_once.py, byte-identical
  build/*.UNBOUND.json, build/FINAL_PAYLOAD.UNBOUND.py   the unbound templates and the stdin bytes built from them
  build/DISPATCH_SCOPE_DELTA.diff, build/LAUNCHER_DELTA.diff, build/ASSEMBLY.json
Frozen core: every shared part and every reviewed base file is pinned below by SHA-256, and the SHA-256 of THIS file
is written into every source as CORE_SHA256 (it enters each signed scope and each receipt). A change to a part, to a
base file or to this file is therefore a new core generation with new payload hashes; a source assembled earlier
keeps its bytes because nothing it was built from can change under it. No output depends on where a directory lies.
"""
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE/'reviewed_base'
# ---- PINS BEGIN (written by seal.py: every file that determines payload bytes) ----
PINS={
      'parts/claim.py':'c98e36f93acde05e6426737eac0a9a10204c7b5743b0539203bc812000347147',
      'parts/core.py':'958c28f1fb3dd88d8c608101a87688cce136544b95df31b4f2df7a7c51e29fa7',
      'parts/docker.py':'3d22e8ad6577b3391bff6a43e815fb7bdb9487dafb07733eb2bb8eaa8b910ccb',
      'parts/parents.py':'3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b',
      'parts/runner.py':'2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7',
      'reviewed_base/dispatch_once.py':'8415e357e48e5662c959b4105acea19bc280cda10112b8370bafd27f7920c409',
      'reviewed_base/launcher_stdin.py':'2842444ec6e46f5e47cad87265927ea3a1a853f21fe72ec2459cf7ac31c3a08e',
      'reviewed_base/transport_once.py':'5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918',
}
# ---- PINS END ----
PART_ORDER=('core','runner','docker','parents','claim')
REQUIRES={'docker':('runner',)}
REMOTE_COMMAND='sudo -n /usr/bin/python3 -I -B -'
FOOTER=("\nif __name__=='__main__':\n"
        "    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')\n")
GENERATED=('dispatch_once.py','launcher_stdin.py','transport_once.py','DISPATCH_SCOPE_DELTA.diff','LAUNCHER_DELTA.diff','REQUEST.UNBOUND.json',
           'AUTHORITY.UNBOUND.json','GO.UNBOUND.json','DISPATCH.UNBOUND.json','PUBLICATION_PROOF.UNBOUND.json','FINAL_PAYLOAD.UNBOUND.py','ASSEMBLY.json')
MAX_SOURCE_BYTES=1024*1024
MAX_UNBOUND_REQUEST_BYTES=40000          # the bound request must stay below the 65536 bytes of a signed document

class Refused(SystemExit):pass
def refuse(code):raise Refused('ASSEMBLY_REFUSED '+code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def date_literal(dates):
    """The date set of one source as the literal its dispatcher carries (a test evaluates it and compares)."""
    return '('+','.join(repr(day) for day in dates)+(',' if len(dates)==1 else '')+')'

def pinned(relative):
    raw=(HERE/relative).read_bytes()
    if PINS.get(relative)!=sha(raw):refuse('CORE_CHANGED '+relative)
    return raw
def reviewed(name):return pinned('reviewed_base/'+name)
def part(name):return pinned('parts/'+name+'.py').decode('ascii')
def core_sha256():
    """The generation of the frozen core: the hash of this file, which pins every other byte-determining file."""
    for relative in sorted(PINS):pinned(relative)
    if sorted(PINS)!=sorted(['parts/'+name+'.py' for name in PART_ORDER]+['reviewed_base/'+name for name in ('dispatch_once.py','launcher_stdin.py','transport_once.py')]):
        refuse('CORE_PINS_INCOMPLETE')
    return sha(Path(__file__).resolve().read_bytes())


# ---------------------------------------------------------------- the operation's two files
SPEC_NAMES=('NAME','MODULE','STEM','PARTS','HEADER','unbound_plan')
def load_spec(directory):
    directory=Path(directory).resolve();path=directory/'spec.py'
    if not path.is_file() or not (directory/'op.py').is_file():refuse('OPERATION_DIRECTORY needs spec.py and op.py')
    module_spec=importlib.util.spec_from_file_location('_hostops02_spec_'+sha(str(directory).encode())[:12],path)
    spec=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(spec)
    for name in SPEC_NAMES:
        if not hasattr(spec,name):refuse('SPEC_MISSING '+name)
    if not (type(spec.NAME) is str and re.fullmatch('[a-z][a-z0-9_]{1,30}',spec.NAME)):refuse('SPEC_NAME')
    if not (type(spec.MODULE) is str and re.fullmatch('[a-z][a-z0-9_]{1,40}',spec.MODULE)
            and spec.MODULE not in ('dispatch_once','launcher_stdin','transport_once','spec','op')):refuse('SPEC_MODULE')
    if not (type(spec.STEM) is str and re.fullmatch('HOSTOPS02_[A-Z][A-Z0-9_]{1,40}',spec.STEM)):refuse('SPEC_STEM')
    parts=spec.PARTS
    if not (type(parts) is list and parts and parts[0]=='core' and parts==[name for name in PART_ORDER if name in parts]
            and all(needed in parts for name in parts for needed in REQUIRES.get(name,()))):refuse('SPEC_PARTS')
    header=spec.HEADER
    if not (type(header) is str and header.startswith('"""') and header.endswith('"""\n') and header.count('"""')==2
            and header.isascii() and 'No action on import.' in header):refuse('SPEC_HEADER')
    spec.DIRECTORY=directory;return spec

def shared_blocks(spec):
    """What the frozen core gives a source: the header, the seal, each carried part between its two marker lines."""
    seal=("# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====\n"
          "CORE_SHA256=%r\nCORE_PARTS=%r\n# ==== END SEAL ====\n")%(core_sha256(),{name:PINS['parts/'+name+'.py'] for name in spec.PARTS})
    out=[spec.HEADER,seal]
    for name in spec.PARTS:
        out.append('# ==== BEGIN %s (shared part, byte-identical in every source that carries it) ====\n'%name.upper()
                   +part(name).rstrip('\n')+'\n# ==== END %s ====\n'%name.upper())
    return out

def own_text(spec):
    """The operation's own part, as its author wrote it."""
    try:own=(spec.DIRECTORY/'op.py').read_text(encoding='ascii')
    except UnicodeDecodeError:refuse('OPERATION_PART_NOT_ASCII')
    if '# ==== ' in own:refuse('OPERATION_PART_CARRIES_A_MARKER')
    return own

def source_bytes(spec):
    """header, the seal, each part between its two marker lines, the operation's part, the footer."""
    out=shared_blocks(spec);own=own_text(spec)
    label='OP_'+spec.NAME.upper()
    out.append('# ==== BEGIN %s (this operation only) ====\n'%label+own.rstrip('\n')+'\n# ==== END %s ====\n'%label)
    return ('\n'.join(out)+FOOTER).encode('ascii')

def load(spec,raw,label=''):
    """Import the assembled source in a private module object (no action on import)."""
    name='_hostops02_'+spec.MODULE+'_'+label+sha(raw)[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled %s.py>'%spec.MODULE
    sys.modules[name]=module                                    # dataclasses resolves the module of a class by name
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__)
    return module


# ---------------------------------------------------------------- the rules every source must meet (CORE.md, "Rules")
OS_OF={'core':{'O_DIRECTORY','O_NOFOLLOW','O_NONBLOCK','O_RDONLY','close','fstat','fstatvfs','getegid','geteuid','open','read','scandir','stat'},
       'runner':{'killpg','set_blocking','write'},'docker':set(),'parents':set(),
       'claim':{'O_CLOEXEC','O_CREAT','O_EXCL','O_WRONLY','fsync','write'}}
IMPORTS_OF={'core':{'dataclasses','datetime','errno','hashlib','json','os','pathlib','re','stat','time'},'runner':{'selectors','signal','subprocess'},
            'docker':set(),'parents':set(),'claim':set()}
OPERATION_IMPORTS={'base64'}                       # what an operation's own part may import beyond its parts
SUBPROCESS={'DEVNULL','PIPE','Popen','TimeoutExpired'}
FORBIDDEN_NAMES={'eval','exec','compile','__import__','open','input','breakpoint','print','shutil','socket','ctypes','globals','locals','vars','setattr','delattr'}
WRITE_CALLS=('mkdir','create','write','fsync','link','unlink','umask')
READ_VERBS=('--version','show','is-enabled','is-active','list-timers','cat')
OWN_MODULES_FORBIDDEN={'subprocess','selectors','signal','fcntl','time'}     # the operation's own part reaches the host through `host` and the parts only
RUN_WORDS_FORBIDDEN=('-v','--volume','--mount','--device','--cap-add')    # prefixes of a fixed word of an attached run (binds are given at call time)
TOOLS={'docker','systemctl'}
REQUIRED=('OPERATION','PHASE','REQUEST_SCHEMA','AUTHORITY_SCHEMA','GO_SCHEMA','RECEIPT_SCHEMA','PLAN_SCHEMA','SOURCE_NAME','WRITES_ALLOWED',
          'ACTIVATION_ALLOWED','DATE_CLASS','DATES','EVIDENCE_REQUIRED','EVIDENCE_OPERATIONS','MAX_GATE_SPAN_SECONDS','COMPLETE_OUTCOME',
          'PARTIAL_OUTCOME','REFUSED_OUTCOME','REDUCED_OUTCOME','ESCAPED_OUTCOME','PLAN_KEYS','SCOPE_STATEMENT','SCOPE','SCOPE_SHA256',
          'REDUCTIONS','Native','validate_plan','effects_of','success_of','perform')

def bindings(tree):
    """(names bound, names whose attribute or item is stored or deleted) at the top level of a module: outside every
    function and class body, inside if, for, while, with and try."""
    bound=set();stored=set()
    def target(node):
        if isinstance(node,ast.Name):bound.add(node.id)
        elif isinstance(node,(ast.Tuple,ast.List)):
            for item in node.elts:target(item)
        elif isinstance(node,ast.Starred):target(node.value)
        elif isinstance(node,(ast.Attribute,ast.Subscript)):
            while isinstance(node,(ast.Attribute,ast.Subscript)):node=node.value
            if isinstance(node,ast.Name):stored.add(node.id)
    def walk(body):
        for node in body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)):bound.add(node.name)
            elif isinstance(node,(ast.Assign,ast.Delete)):
                for item in node.targets:target(item)
            elif isinstance(node,(ast.AugAssign,ast.AnnAssign)):target(node.target)
            elif isinstance(node,(ast.Import,ast.ImportFrom)):bound.update((alias.asname or alias.name).split('.')[0] for alias in node.names)
            else:
                if isinstance(node,ast.For):target(node.target)
                for item in getattr(node,'items',None) or []:
                    if item.optional_vars is not None:target(item.optional_vars)
                for handler in getattr(node,'handlers',None) or []:
                    if handler.name:bound.add(handler.name)
                    walk(handler.body)
                for field in ('body','orelse','finalbody'):
                    if isinstance(getattr(node,field,None),list):walk(getattr(node,field))
    walk(tree.body);return bound,stored

def constants(module,names):
    """The data the named module members hold, as text: what must be the same with and without an operation part."""
    def plain(value):
        if value is None or type(value) in (bool,int,float,str,bytes):return repr(value)
        if type(value) in (tuple,list):return [type(value).__name__]+[plain(item) for item in value]
        if type(value) in (set,frozenset):return [type(value).__name__]+sorted(repr(plain(item)) for item in value)
        if type(value) is dict:return ['dict']+sorted([repr(plain(key)),plain(item)] for key,item in value.items())
        return '<%s>'%type(value).__name__
    return {name:plain(getattr(module,name,None)) for name in sorted(names) if not callable(getattr(module,name,None)) and type(getattr(module,name,None)).__name__!='module'}

def lint(spec,raw,module):
    """Returns the list of broken rules (empty when the source may be assembled). By syntax tree and by the loaded
    module, never by text search."""
    broken=[];m=module;parts=spec.PARTS
    def rule(ok,text):
        if not ok:broken.append(text)
    try:tree=ast.parse(raw.decode('ascii'),feature_version=(3,7));own=ast.parse(own_text(spec),feature_version=(3,7))
    except SyntaxError as error:return ['the source is not Python 3.7 syntax: %s'%error.msg]
    # Frozen means the names too: the operation's own part is the last text of the one module, so a name it bound again
    # would change what the carried parts do while their bytes stay the sealed ones.
    shared_text='\n'.join(shared_blocks(spec)[1:]);shared,_=bindings(ast.parse(shared_text));bound,stored=bindings(own)
    rule(not bound&shared,'the operation part binds names of the frozen core again: %s'%sorted(bound&shared))
    rule(not stored&shared,'the operation part stores into objects of the frozen core: %s'%sorted(stored&shared))
    reference=load(spec,shared_text.encode('ascii'),'core_only_')
    changed=sorted(name for name,value in constants(reference,shared).items() if constants(m,[name]).get(name)!=value)
    rule(not changed,'constants of the frozen core differ once the operation part is loaded: %s'%changed)
    # The operation's own part makes no system call and starts no process of its own: everything goes through `host`
    # and the functions of the carried parts. Of the os module it may name the open flags.
    named=[node for node in ast.walk(own) if isinstance(node,ast.Name)];flags=[node for node in ast.walk(own) if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='os']
    rule(not {node.id for node in named}&OWN_MODULES_FORBIDDEN,'the operation part names a module it must not use itself: %s'%sorted({node.id for node in named}&OWN_MODULES_FORBIDDEN))
    rule(all(node.attr.startswith('O_') for node in flags) and len([node for node in named if node.id=='os'])==len(flags),
         'the operation part uses the os module for more than open flags: %s'%sorted({node.attr for node in flags if not node.attr.startswith('O_')}))
    rule('through' not in {node.arg for node in ast.walk(own) if isinstance(node,ast.keyword)},'the operation part starts a command as if it were a helper of the core (through=)')
    imports=set();attributes=set();names=set();process=set();keywords=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports|={alias.name for alias in node.names}
        elif isinstance(node,ast.ImportFrom):imports.add(node.module)
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='os':attributes.add(node.attr)
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='subprocess':process.add(node.attr)
        elif isinstance(node,ast.Name):names.add(node.id)
        elif isinstance(node,ast.keyword):keywords.add(node.arg)
        rule(not isinstance(node,(ast.AsyncFunctionDef,ast.AsyncFor,ast.AsyncWith,ast.Await,ast.Global,ast.NamedExpr)),'async code, a global statement or an assignment expression')
        rule(not (isinstance(node,ast.arguments) and getattr(node,'posonlyargs',[])),'positional-only parameters')
    allowed_imports=set().union(*(IMPORTS_OF[name] for name in parts));allowed_os=set().union(*(OS_OF[name] for name in parts))
    rule(imports-allowed_imports<=OPERATION_IMPORTS,'imports outside the standard-library set of the carried parts: %s'%sorted(imports-allowed_imports-OPERATION_IMPORTS))
    rule(attributes<=allowed_os,'os members outside those of the carried parts: %s'%sorted(attributes-allowed_os))
    rule(not names&FORBIDDEN_NAMES,'forbidden names: %s'%sorted(names&FORBIDDEN_NAMES))
    rule('shell' not in keywords and 'preexec_fn' not in keywords and process<=(SUBPROCESS if 'runner' in parts else set()),'subprocess use outside the runner')
    for name in REQUIRED:rule(hasattr(m,name),'the operation part does not define '+name)
    if broken:return broken
    writes,activation=m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED
    rule(type(writes) is bool and type(activation) is bool and (writes or not activation),'WRITES_ALLOWED and ACTIVATION_ALLOWED are booleans, and only a writing source may switch a unit')
    rule(m.SOURCE_NAME==spec.MODULE+'.py','SOURCE_NAME is not <MODULE>.py')
    rule(m.DATE_CLASS in m.DATE_SETS and m.DATES==m.DATE_SETS[m.DATE_CLASS] and (m.DATE_CLASS=='READ')==(not writes),
         'DATES is not DATE_SETS[DATE_CLASS], or the class does not fit the writes flag (READ for a reading source, WRITE_* for a writing one)')
    rule(type(m.MAX_GATE_SPAN_SECONDS) is int and 0<m.MAX_GATE_SPAN_SECONDS<=(900 if writes else 3600),'MAX_GATE_SPAN_SECONDS above 900 (write) or 3600 (read)')
    doc=('WRITE_' if writes else 'READONLY_')+spec.STEM
    rule((m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA)==(doc+'_REQUEST_V1',doc+'_AUTHORITY_V1',doc+'_GO_V1',doc+'_RECEIPT_V1',spec.STEM+'_PLAN_V1'),
         'schema names are not %s_{REQUEST,AUTHORITY,GO,RECEIPT}_V1 and %s_PLAN_V1'%(doc,spec.STEM))
    rule(type(m.OPERATION) is str and re.fullmatch(('GO_WRITE_' if writes else 'GO_READONLY_')+'HOSTOPS02_[A-Z][A-Z0-9_]{1,50}_[0-9]{2}',m.OPERATION) is not None,
         'OPERATION is not GO_WRITE_HOSTOPS02_<NAME>_<NN> (GO_READONLY_... for a reading source)')
    rule(type(m.PHASE) is str and re.fullmatch(('WRITE_' if writes else 'READONLY_')+'[A-Z][A-Z0-9_]{1,70}',m.PHASE) is not None,'PHASE does not begin with WRITE_ or READONLY_ as the writes flag says')
    for name in ('COMPLETE_OUTCOME','PARTIAL_OUTCOME','REFUSED_OUTCOME','REDUCED_OUTCOME','ESCAPED_OUTCOME'):
        rule(type(getattr(m,name)) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',getattr(m,name)) is not None,name+' is not a constant code')
    rule(m.REFUSED_OUTCOME!=m.COMPLETE_OUTCOME and m.PARTIAL_OUTCOME!=m.COMPLETE_OUTCOME and m.ESCAPED_OUTCOME!=m.COMPLETE_OUTCOME
         and m.REDUCED_OUTCOME!=m.COMPLETE_OUTCOME,'the success outcome is also the name of another outcome')
    rule(type(m.EVIDENCE_REQUIRED) is bool and type(m.EVIDENCE_OPERATIONS) is tuple and all(type(item) is str for item in m.EVIDENCE_OPERATIONS)
         and (m.EVIDENCE_REQUIRED or not m.EVIDENCE_OPERATIONS),'EVIDENCE_REQUIRED / EVIDENCE_OPERATIONS')
    rule(type(m.PLAN_KEYS) is frozenset and not m.PLAN_KEYS&m.PLAN_COMMON_KEYS and all(type(key) is str for key in m.PLAN_KEYS),'PLAN_KEYS overlaps the common plan keys')
    scope=m.SCOPE
    rule(type(scope) is dict and scope.get('operation')==m.OPERATION and scope.get('dates')==list(m.DATES) and scope.get('statement')==m.SCOPE_STATEMENT
         and scope.get('core_sha256')==m.CORE_SHA256 and type(scope.get('never')) is list and type(scope.get('limits')) is dict
         and scope['limits'].get('max_seconds')==m.MAX_SECONDS and scope['limits'].get('max_gate_span_seconds')==m.MAX_GATE_SPAN_SECONDS
         and scope['limits'].get('receipt_bytes')==m.RECEIPT_LIMIT and scope.get('activation_allowed') is activation and scope.get('writes_allowed') is writes,
         'SCOPE lacks operation, dates, statement, core_sha256, writes_allowed, activation_allowed, never, or limits{max_seconds,max_gate_span_seconds,receipt_bytes}')
    try:rule(m.SCOPE_SHA256==sha(canonical(scope)),'SCOPE_SHA256 is not the hash of SCOPE')
    except (TypeError,ValueError):rule(False,'SCOPE is not canonical JSON')
    rule(type(m.SCOPE_STATEMENT) is str and 0<len(m.SCOPE_STATEMENT)<=4000,'SCOPE_STATEMENT')
    rule(type(m.REDUCTIONS) is list and all(type(item) is tuple and len(item)==2 and type(item[0]) is str and callable(item[1]) for item in m.REDUCTIONS),'REDUCTIONS is not a list of (name, function)')
    commands=getattr(m,'COMMANDS',None)
    rule((commands is not None)==('runner' in parts),'COMMANDS exists exactly when the runner is carried')
    if commands is not None:
        binaries=getattr(m,'BINARIES',None)
        rule(type(binaries) is dict and set(binaries)<=TOOLS and all(type(paths) is list and paths and all(type(path) is str and re.fullmatch('(/[a-z]+)+/'+tool,path) for path in paths)
                                                                      for tool,paths in binaries.items()),
             'BINARIES names a tool other than docker and systemctl, or a path that is not an absolute path of that tool')
        rule(hasattr(m,'BINARIES') and scope.get('commands') is commands and scope.get('binaries') is m.BINARIES and scope.get('command_classes') is m.COMMAND_CLASSES
             and scope.get('command_environment') is m.COMMAND_ENVIRONMENT and scope.get('command_variables') is m.COMMAND_VARIABLES,
             'SCOPE does not carry commands, binaries, command_classes, command_environment and command_variables (the objects themselves)')
        for name,row in sorted(commands.items()):
            ok=(type(row) is dict and set(row)==set(m.ROW_KEYS) and row['tool'] in getattr(m,'BINARIES',{}) and row['class'] in m.COMMAND_CLASSES
                and row['kind'] in m.COMMAND_KINDS and type(row['stdin']) is bool and type(row['argv']) is list and type(row['tail']) is list
                and row['argv'] and all(type(word) is str and word for word in row['argv']+row['tail']) and (row['middle'] is None or type(row['middle']) is str))
            rule(ok,'COMMANDS[%r] is not a command_row()'%name)
            if not ok:continue
            words=row['argv']+row['tail']
            rule(row['kind']!='EFFECT' or writes,'COMMANDS[%r] is an EFFECT in a source that does not write'%name)
            if row['tool']=='systemctl':
                rule((row['kind']=='READ') if row['argv'][0] in READ_VERBS else (activation and row['kind']=='EFFECT'),
                     'COMMANDS[%r]: a reading systemctl verb is kind READ; a verb that changes something needs ACTIVATION_ALLOWED and kind EFFECT'%name)
            if row['tool']=='docker':
                verb=row['argv'][:2] if row['argv'][0] in ('image','container') else row['argv'][:1]
                reading=verb in (['image','inspect'],['container','inspect'],['ps'],['info'],['version'],['image','ls']) or (verb==['compose'] and row['tail'][:1]==['config'])
                rule(reading==(row['kind']=='READ'),'COMMANDS[%r]: kind %s does not fit the docker verb'%(name,row['kind']))
                rule(row['argv'][0]!='exec','COMMANDS[%r]: docker exec is not used by this core'%name)
                rule(not reading or verb==['compose'] or '--format' in row['argv'],'COMMANDS[%r]: a docker read fixes its --format (the default output of inspect holds the environment)'%name)
                if verb==['run']:
                    rule(row['argv'][:2]==['run','--rm'] and '--pull' in row['argv'] and row['argv'][row['argv'].index('--pull')+1:][:1]==['never']
                         and '--privileged' not in words and '-d' not in words and '--detach' not in words and not [word for word in words if word.startswith(RUN_WORDS_FORBIDDEN)],
                         'COMMANDS[%r]: an attached run starts with run --rm, never pulls, is not privileged or detached, adds no device or capability, and takes its binds at call time (no -v, no fixed --mount)'%name)
            rule(row['kind']!='CONTAINER' or (row['tool']=='docker' and row['argv'][:1]==['run']),'COMMANDS[%r]: a CONTAINER row is an attached docker run'%name)
            rule('Env' not in ''.join(words),'COMMANDS[%r] names the environment of a container in a fixed template'%name)
            rule(row['argv'][-1]!='--format' or (name=='container_environment' and row['argv']==['container','inspect','--format'] and not row['tail']),
                 'COMMANDS[%r]: a template given at call time exists only for container_environment (built by environment_format)'%name)
    native=m.Native
    if not writes:
        rule('files' not in parts and not [name for name in dir(native) if name in WRITE_CALLS],'a reading source carries the files part or a Native that can create, write or remove')
    return broken


# ---------------------------------------------------------------- dispatcher and launcher: the hostops01 deltas, unchanged
def dispatcher_bytes(spec,module):
    """The reviewed dispatcher with literals replaced. No line is added or removed."""
    text=reviewed('dispatch_once.py').decode();m=spec.MODULE;writes=module.WRITES_ALLOWED
    def sub(old,new,count=1):
        nonlocal text
        if text.count(old)!=count:refuse('DISPATCH_ANCHOR '+old)
        text=text.replace(old,new)
    sub('import hostfacts_readonly\nfrom hostfacts_readonly import','import %s\nfrom %s import'%(m,m))
    sub("'hostfacts_readonly.py')","'%s.py')"%m)
    sub('hostfacts_readonly.authenticate(',m+'.authenticate(')
    sub('pins=hostfacts_readonly.Pins(','pins=%s.Pins('%m)
    sub("'SUPERVISOR_HOSTFACTS_DISPATCH_AUTHORIZATION_V1'","'%s_DISPATCH_AUTHORIZATION_V1'"%spec.STEM)
    sub("'GO_READONLY_SUPERVISOR_HOSTFACTS_01'","'%s'"%module.OPERATION,2)
    sub("start.date().isoformat()=='2026-10-02'","start.date().isoformat() in "+date_literal(module.DATES))
    sub("'READONLY_SUPERVISOR_HOSTFACTS_REQUEST_V1'","'%s'"%module.REQUEST_SCHEMA)
    sub("'READONLY_SUPERVISOR_HOSTFACTS_AUTHORITY_V1'","'%s'"%module.AUTHORITY_SCHEMA)
    sub("'READONLY_SUPERVISOR_HOSTFACTS_GO_V1'","'%s'"%module.GO_SCHEMA)
    sub("and request.get('status')=='BOUND' and request.get('executor_uid')==0\n",
        "and request.get('status')=='BOUND' and request.get('executor_uid')==0 and request.get('date')==start.date().isoformat()\n")
    sub("go.get('phase')=='READONLY_HOSTFACTS'","go.get('phase')=='%s'"%module.PHASE)
    if writes:
        sub("go.get('writes_allowed') is False","go.get('writes_allowed') is True")
        sub("authority.get('writes_allowed') is False and request.get('writes_allowed') is False,'READONLY_SCOPE')",
            "authority.get('writes_allowed') is True and request.get('writes_allowed') is True,'WRITE_SCOPE')")
    sub("'SUPERVISOR_HOSTFACTS_GO_CLAIM_V1'","'%s_GO_CLAIM_V1'"%spec.STEM)
    sub("'SUPERVISOR_HOSTFACTS_DISPATCH_INTENT_V1'","'%s_DISPATCH_INTENT_V1'"%spec.STEM,2)
    sub("'SUPERVISOR_HOSTFACTS_INTENT_PUBLICATION_V1'","'%s_INTENT_PUBLICATION_V1'"%spec.STEM)
    sub("'READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1'","'%s'"%module.RECEIPT_SCHEMA)
    if 'HOSTFACTS' in text or 'hostfacts' in text:refuse('DISPATCH_RESIDUE')
    compile(text,'dispatch_once.py','exec')
    return text.encode()

def launcher_bytes():
    """The reviewed launcher with five lines replaced. The payload is entered through run(); the exit code is 3 while
    run() executes, so an exception that escapes it is filed UNCERTAIN by the unchanged transport, never as a refusal."""
    text=reviewed('launcher_stdin.py').decode()
    def sub(old,new):
        nonlocal text
        if text.count(old)!=1:refuse('LAUNCHER_ANCHOR '+old)
        text=text.replace(old,new)
    sub("module=types.ModuleType('_pinned_supervisor_hostfacts')","module=types.ModuleType('_pinned_hostops')")
    sub("exec(compile(raw['source'],'<pinned-supervisor-hostfacts>','exec'),module.__dict__)",
        "exec(compile(raw['source'],'<pinned-hostops>','exec'),module.__dict__)")
    sub("    result=module.observe(raw['request'],raw['authority'],raw['go'],pins=module.Pins(**PINS),",
        "    exit_code=3;result=module.run(raw['request'],raw['authority'],raw['go'],pins=module.Pins(**PINS),")
    sub("    exit_code=0 if result.get('status')=='METADATA_ONLY_REQUIRES_REVIEW' else 2",
        "    exit_code={'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(result.get('status'),2)")
    sub("    result={'schema':'READONLY_SUPERVISOR_HOSTFACTS_STDIN_RESULT_V1','status':'REFUSED','code':code,'source_mutation':False}",
        "    result={'schema':'HOSTOPS_STDIN_RESULT_V1','status':'REFUSED' if exit_code==1 else 'RUN_RAISED_STATE_UNKNOWN','code':code}")
    compile(text,'launcher_stdin.py','exec')
    return text.encode()

def launcher_module(raw):
    module=type(sys)('_hostops02_launcher');exec(compile(raw,'launcher_stdin.py','exec'),module.__dict__);return module

def unbound_documents(spec,module,source,runtime,launcher):
    """REQUEST, AUTHORITY, GO, DISPATCH and PUBLICATION_PROOF templates and the exact stdin payload built from them.
    Windows, date, host binding, owner, decisions, effects, target, key and known-hosts references, command pin,
    claim root and every observed identity are null; status is UNBOUND; execution_authorized is false. The five blob
    references of the dispatch template carry the hash of the unbound bytes and a null path."""
    plan={'schema':module.PLAN_SCHEMA,'status':'UNBOUND','phase':module.PHASE,'scope':module.SCOPE,
          'window':{'not_before':None,'expires_at':None},'host_binding_sha256':None,'max_seconds':module.MAX_SECONDS}
    own=spec.unbound_plan(module)
    if not (type(own) is dict and set(own)==set(module.PLAN_KEYS)):refuse('UNBOUND_PLAN_KEYS: unbound_plan() must return exactly PLAN_KEYS')
    plan.update(own)
    request={'schema':module.REQUEST_SCHEMA,'status':'UNBOUND','operation':module.OPERATION,'phase':module.PHASE,'date':None,
             'not_before':None,'not_after':None,'host_binding_sha256':None,'payload_sha256':sha(source),
             'scope_sha256':module.SCOPE_SHA256,'executor_uid':0,'max_seconds':module.MAX_SECONDS,
             'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':module.ACTIVATION_ALLOWED,'evidence':[],'plan':plan}
    request_raw=canonical(request)
    if len(request_raw)>MAX_UNBOUND_REQUEST_BYTES:refuse('UNBOUND_REQUEST_TOO_LARGE %d bytes'%len(request_raw))
    authority={'schema':module.AUTHORITY_SCHEMA,'status':'UNBOUND','operation':module.OPERATION,'phase':module.PHASE,'owner':None,
               'decision':None,'execution_authorized':False,'request_sha256':sha(request_raw),'payload_sha256':sha(source),
               'effects':None,'host_binding_sha256':None,'not_before':None,'not_after':None,
               'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':module.ACTIVATION_ALLOWED,'owner_evidence':None}
    authority_raw=canonical(authority)
    go={'schema':module.GO_SCHEMA,'status':'UNBOUND','operation':module.OPERATION,'phase':module.PHASE,'owner':None,'action':None,
        'execution_authorized':False,'request_sha256':sha(request_raw),'authority_sha256':sha(authority_raw),
        'payload_sha256':sha(source),'effects':None,'host_binding_sha256':None,'not_before':None,'not_after':None,
        'writes_allowed':module.WRITES_ALLOWED,'activation_allowed':module.ACTIVATION_ALLOWED,
        'claim_root_identity':{'path':None,'device':None,'inode':None},
        'transport_binding':{'target':None,'remote_command':REMOTE_COMMAND,'command_sha256':None,'runtime_sha256':runtime},
        'scope_statement':module.SCOPE_STATEMENT,
        'success_criterion':module.COMPLETE_OUTCOME if getattr(spec,'SUCCESS_IN_TEMPLATE',True) else None}   # null when it follows a signed mode
    go_raw=canonical(go)
    payload=launcher_module(launcher).build(source,request_raw,authority_raw,go_raw,expected_payload_sha256=sha(source),
        expected_request_sha256=sha(request_raw),expected_authority_sha256=sha(authority_raw),expected_go_sha256=sha(go_raw))
    def item(raw):return {'path':None,'sha256':sha(raw)}
    config={'schema':spec.STEM+'_DISPATCH_AUTHORIZATION_V1','status':'UNBOUND','decision':'UNBOUND','operation':module.OPERATION,
            'single_use':True,'retry':False,'owner':None,'authorization_ref':None,'executor_uid':0,'not_before':None,'not_after':None,
            'latest_start':None,'watchdog_seconds':80,'finalize_local_receipts_after_window':True,'runtime_sha256':runtime,
            'source':item(source),'request':item(request_raw),'authority':item(authority_raw),'go':item(go_raw),
            'payload':item(payload),'host_binding_sha256':None,'target':None,
            'remote_command':REMOTE_COMMAND,'command_sha256':None,'ssh_key':{'path':None,'sha256':None},
            'known_hosts':{'path':None,'sha256':None},'attempt_directory':None,
            'local_root_identity':{'path':None,'device':None,'inode':None}}
    config_raw=canonical(config)
    proof={'schema':spec.STEM+'_INTENT_PUBLICATION_V1','status':'UNBOUND','owner':None,'publication_ref':None,
           'go_sha256':sha(go_raw),'config_sha256':sha(config_raw),'intent_sha256':None,'published_at':None}
    return {'REQUEST.UNBOUND.json':request_raw,'AUTHORITY.UNBOUND.json':authority_raw,'GO.UNBOUND.json':go_raw,
            'DISPATCH.UNBOUND.json':config_raw,'PUBLICATION_PROOF.UNBOUND.json':canonical(proof),'FINAL_PAYLOAD.UNBOUND.py':payload}

def diff(old,new,old_name,new_name):
    return ''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),old_name,new_name)).encode()

def build(directory):
    """{file name: bytes} of build/ for one operation directory. Pure: nothing is written."""
    spec=load_spec(directory);source=source_bytes(spec)
    if len(source)>MAX_SOURCE_BYTES:refuse('SOURCE_TOO_LARGE')
    compile(source,spec.MODULE+'.py','exec');module=load(spec,source)
    broken=lint(spec,source,module)
    if broken:refuse('RULES\n  - '+'\n  - '.join(broken))
    launcher=launcher_bytes();transport=reviewed('transport_once.py');dispatcher=dispatcher_bytes(spec,module)
    runtime={'dispatch_once.py':sha(dispatcher),'transport_once.py':sha(transport),'launcher_stdin.py':sha(launcher),spec.MODULE+'.py':sha(source)}
    files={spec.MODULE+'.py':source,'dispatch_once.py':dispatcher,'launcher_stdin.py':launcher,'transport_once.py':transport,
           'DISPATCH_SCOPE_DELTA.diff':diff(reviewed('dispatch_once.py'),dispatcher,'reviewed_supervisor_hostfacts/dispatch_once.py','hostops02/%s/dispatch_once.py'%spec.NAME),
           'LAUNCHER_DELTA.diff':diff(reviewed('launcher_stdin.py'),launcher,'reviewed_supervisor_hostfacts/launcher_stdin.py','hostops02/launcher_stdin.py')}
    files.update(unbound_documents(spec,module,source,runtime,launcher))
    base=reviewed('dispatch_once.py').decode().splitlines();new=dispatcher.decode().splitlines()
    report={'schema':'HOSTOPS02_ASSEMBLY_V1','name':spec.NAME,'module':spec.MODULE,'parts':list(spec.PARTS),'core_sha256':core_sha256(),
            'core_parts':{name:PINS['parts/'+name+'.py'] for name in spec.PARTS},'operation_part_sha256':sha((spec.DIRECTORY/'op.py').read_bytes()),
            'spec_sha256':sha((spec.DIRECTORY/'spec.py').read_bytes()),'operation':module.OPERATION,'writes_allowed':module.WRITES_ALLOWED,
            'activation_allowed':module.ACTIVATION_ALLOWED,'date_class':module.DATE_CLASS,'dates':list(module.DATES),
            'scope_sha256':module.SCOPE_SHA256,'source_sha256':sha(source),'source_bytes':len(source),
            'dispatcher_sha256':sha(dispatcher),'dispatcher_changed_lines':[index+1 for index,(a,b) in enumerate(zip(base,new)) if a!=b],
            'dispatcher_line_count_equal':len(base)==len(new),'launcher_sha256':sha(launcher),'transport_sha256':sha(transport),
            'final_payload_sha256':sha(files['FINAL_PAYLOAD.UNBOUND.py']),'final_payload_bytes':len(files['FINAL_PAYLOAD.UNBOUND.py']),
            'unbound_request_bytes':len(files['REQUEST.UNBOUND.json'])}
    files['ASSEMBLY.json']=(json.dumps(report,indent=1,sort_keys=True)+'\n').encode()
    return files

def main(arguments):
    if arguments==['--core']:
        print(core_sha256());return 0
    check=arguments[:1]==['--check'];rest=arguments[1:] if check else arguments
    if len(rest)!=1:
        print(__doc__);return 2
    directory=Path(rest[0]).resolve();files=build(directory);target=directory/'build'
    if check:
        found={path.name:path.read_bytes() for path in target.iterdir() if path.is_file()} if target.is_dir() else {}
        different=sorted(name for name in set(files)|set(found) if files.get(name)!=found.get(name))
        print('BUILD_EQUAL' if not different else 'BUILD_DIFFERS '+' '.join(different));return 0 if not different else 1
    target.mkdir(exist_ok=True)
    for path in target.iterdir():
        if path.is_file() and path.name not in files:path.unlink()            # a file of an earlier module name
    for name,raw in files.items():(target/name).write_bytes(raw)
    sys.stdout.write(files['ASSEMBLY.json'].decode());return 0

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
