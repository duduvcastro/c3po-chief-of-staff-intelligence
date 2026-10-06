"""The delta of the HOSTOPS02 core against the sealed HOSTOPS01 parts, as files a reviewer reads. Offline.

  delta.py write <hostops01 candidate directory>   (re)writes DELTA/
  delta.py check <hostops01 candidate directory>   exit 1 unless DELTA/ holds exactly what would be written

DELTA/core.diff                  parts/core.py of HOSTOPS01 -> parts/core.py here (the whole file)
DELTA/files.create_file.diff     install_unit() of HOSTOPS01's op_install_units.py -> create_file() of parts/files.py
DELTA/files.create_directory.diff  create_directory() of HOSTOPS01's op_provision.py -> create_directory() of parts/files.py
DELTA/IDENTICAL.json             the functions and constants that are byte-identical, with the hash of their text on both sides
Nothing of HOSTOPS01 is modified or copied here: its files are read, and its seal is checked first.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
HOSTOPS01_PINS={'parts/core.py':'9a053347b0129c0ca4bc5973b8977422fafb014952d4c0f8c789fded46e73641',
                'parts/runner.py':'2afc002d1287de97ac77c1bd3815d839cfd46b64bac5e32ccb1b71c78ac84425',
                'parts/op_install_units.py':'5158c5cbdc4e6cb5b14690d3199e994e8d18bf05305097ba15674235f413a9c3',
                'parts/op_provision.py':'28e04b7de035306fdd414ecc366b61488ab3bb8cb4557955ab914ace6a23fe4d',
                'parts/layout.py':'ec5dc48aae4e751b206a5f6e400ee21c5d20bcf7aa30c66d979bb89571439eb6',
                'reviewed_base/dispatch_once.py':'8415e357e48e5662c959b4105acea19bc280cda10112b8370bafd27f7920c409',
                'reviewed_base/launcher_stdin.py':'2842444ec6e46f5e47cad87265927ea3a1a853f21fe72ec2459cf7ac31c3a08e',
                'reviewed_base/transport_once.py':'5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918'}
# (name here, file here) <- (name there, file there): the text of the definition must be equal byte for byte
IDENTICAL=[('trusted_executable','parts/runner.py','trusted_executable','parts/runner.py'),('binary','parts/runner.py','binary','parts/runner.py'),
           ('image_facts','parts/docker.py','image_facts','parts/runner.py'),('IMAGE_FORMAT','parts/docker.py','IMAGE_FORMAT','parts/runner.py'),
           ('REVISION_LABEL','parts/docker.py','REVISION_LABEL','parts/runner.py'),('REFERENCE','parts/docker.py','REFERENCE','parts/runner.py'),
           ('MAX_TAGS','parts/docker.py','MAX_TAGS','parts/runner.py'),
           ('remove_own_temporary','parts/files.py','remove_own_temporary','parts/op_install_units.py'),('number','parts/files.py','number','parts/op_install_units.py'),
           ('TEMPORARY','parts/files.py','TEMPORARY','parts/op_install_units.py'),
           ('world_writable_without_sticky','parts/parents.py','world_writable_without_sticky','parts/layout.py'),
           ('COMMAND_ENVIRONMENT','parts/runner.py','COMMAND_ENVIRONMENT','parts/runner.py'),('MAX_TOOL_TIMEOUTS','parts/runner.py','MAX_TOOL_TIMEOUTS','parts/runner.py')]
PAIRS=[('files.create_file.diff','install_unit','parts/op_install_units.py','create_file','parts/files.py'),
       ('files.create_directory.diff','create_directory','parts/op_provision.py','create_directory','parts/files.py')]

def sha(raw):return hashlib.sha256(raw).hexdigest()
def definition(text,name):
    """The source lines of one top-level function, class or assignment."""
    for node in ast.parse(text).body:
        names=[node.name] if isinstance(node,(ast.FunctionDef,ast.ClassDef)) else [target.id for target in getattr(node,'targets',[]) if isinstance(target,ast.Name)]
        if name in names:return ''.join(text.splitlines(True)[node.lineno-1:node.end_lineno])
    raise SystemExit('definition not found: '+name)
def unified(old,new,old_name,new_name):
    return ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),old_name,new_name))

def files(there):
    there=Path(there).resolve()
    for relative,pin in HOSTOPS01_PINS.items():
        if sha((there/relative).read_bytes())!=pin:raise SystemExit('HOSTOPS01_NOT_THE_SEALED_BYTES '+relative)
    def old(relative):return (there/relative).read_text(encoding='ascii')
    def new(relative):return (HERE/relative).read_text(encoding='ascii')
    out={'core.diff':unified(old('parts/core.py'),new('parts/core.py'),'hostops01/parts/core.py','hostops02/core/parts/core.py')}
    for name,old_function,old_file,new_function,new_file in PAIRS:
        out[name]=unified(definition(old(old_file),old_function),definition(new(new_file),new_function),
                          'hostops01/%s:%s'%(old_file,old_function),'hostops02/core/%s:%s'%(new_file,new_function))
    rows=[]
    for name,file,old_name,old_file in IDENTICAL:
        mine,theirs=definition(new(file),name),definition(old(old_file),old_name)
        rows.append({'here':'%s:%s'%(file,name),'hostops01':'%s:%s'%(old_file,old_name),'sha256_here':sha(mine.encode()),'sha256_hostops01':sha(theirs.encode()),
                     'identical':mine==theirs})
    for relative in ('reviewed_base/dispatch_once.py','reviewed_base/launcher_stdin.py','reviewed_base/transport_once.py'):
        rows.append({'here':relative,'hostops01':relative,'sha256_here':sha((HERE/relative).read_bytes()),'sha256_hostops01':HOSTOPS01_PINS[relative],
                     'identical':sha((HERE/relative).read_bytes())==HOSTOPS01_PINS[relative]})
    out['IDENTICAL.json']=json.dumps({'schema':'HOSTOPS02_CORE_DELTA_V1','hostops01_pins':HOSTOPS01_PINS,'rows':rows},indent=1,sort_keys=True)+'\n'
    return out

def main(arguments):
    if len(arguments)!=2 or arguments[0] not in ('write','check'):
        print(__doc__);return 2
    made=files(arguments[1]);target=HERE/'DELTA'
    if arguments[0]=='write':
        target.mkdir(exist_ok=True)
        for name,text in made.items():(target/name).write_text(text,encoding='ascii')
    different=sorted(name for name in made if not (target/name).is_file() or (target/name).read_text(encoding='ascii')!=made[name])
    rows=json.loads(made['IDENTICAL.json'])['rows'];unequal=[row['here'] for row in rows if not row['identical']]
    print('DELTA_OK' if not different and not unequal else 'DELTA_DIFFERS %s NOT_IDENTICAL %s'%(different,unequal))
    return 0 if not different and not unequal else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
