"""A mechanical second list for K10's own part: generic operators applied to every line of code of the operation part,
one change per mutant. It is not written against the tests, so it finds what the hand-written list (mutants.py) did
not think of. Used by mutate.py with HOSTOPS_MUTATION_LIST=sweep (record MUTATION_SWEEP.json).

Operators, applied outside string literals, one occurrence at a time:
  ==  <->  !=        <=  ->  <        >=  ->  >        and  <->  or        is None  <->  is not None
  True  <->  False   a decimal integer n  ->  n+1      a whole line that is one need(...) or one other call  ->  removed
A row is (name, 'op', the whole line, the changed line); a line that does not occur exactly once in the built source
is left out, and a change that does not compile is recorded as not applicable by the run.
EQUIVALENT names the survivors that cannot change any result, with the reason; every other survivor is an error."""
import re

BEGIN='# ==== BEGIN OP_INSTALL_RELEASE (this operation only) ====\n'
END='# ==== END OP_INSTALL_RELEASE ====\n'
SWAPS=[('==','!=','eq'),('!=','==','ne'),('<=','<','le'),('>=','>','ge'),(' and ',' or ','and'),(' or ',' and ','or'),
       (' is not None',' is None','isnot'),(' is None',' is not None','isnone'),('True','False','true'),('False','True','false')]
NUMBER=re.compile(r'(?<![A-Za-z0-9_.\'%])(\d+)(?![A-Za-z0-9_.\'])')

def in_string(line,position):
    """True when position lies inside a quoted literal of the line (single quotes are the only ones the part uses in code)."""
    quote=None;index=0
    while index<position:
        char=line[index]
        if quote is None and char in '\'"':quote=char
        elif quote is not None and char=='\\':index+=1
        elif char==quote:quote=None
        index+=1
    return quote is not None

def code_lines(source):
    """(line number in the operation part, line) for every line of code: no comment-only line, no docstring line."""
    body=source[source.index(BEGIN)+len(BEGIN):source.index(END)];out=[];doc=False
    for number,line in enumerate(body.splitlines(True),1):
        stripped=line.strip()
        if doc:
            if '"""' in stripped:doc=False
            continue
        if stripped.startswith('"""'):
            if stripped.count('"""')==1:doc=True
            continue
        if not stripped or stripped.startswith('#'):continue
        out.append((number,line))
    return out

def rows(source):
    out=[];skipped=0
    for number,line in code_lines(source):
        if source.count(line)!=1:
            skipped+=1;continue
        code=line.split('   # ')[0] if '   # ' in line else line                          # a trailing comment is not code
        found=[]
        for old,new,label in SWAPS:
            start=0
            while True:
                position=code.find(old,start)
                if position<0:break
                start=position+len(old)
                if in_string(code,position):continue
                if old==' is None' and code[position:position+12]==' is not None':continue
                if old=='==' and position>0 and code[position-1] in '!<>=':continue
                if old in ('<=','>=') and code[position+2:position+3]=='=':continue
                found.append((label,position,code[:position]+new+code[position+len(old):]))
        for match in NUMBER.finditer(code):
            if in_string(code,match.start()) or code[max(0,match.start()-2):match.start()] in ('0o','0x'):continue
            found.append(('int',match.start(),code[:match.start()]+str(int(match.group(1))+1)+code[match.end():]))
        if re.fullmatch(r'\s+need\(.*\)\n',code) and code.count('need(')==1:
            found.append(('noneed',0,code[:len(code)-len(code.lstrip())]+'pass\n'))
        elif re.fullmatch(r'\s+[A-Za-z_][A-Za-z0-9_.]*\([^=]*\)\s*\n',code) and code.strip().count('(')==code.strip().count(')'):
            found.append(('nocall',0,code[:len(code)-len(code.lstrip())]+'pass\n'))                # a line that is one call and nothing else
        for index,(label,position,changed) in enumerate(found):
            out.append(('S_L%03d_%s_%02d'%(number,label,index),'op',line,changed+line[len(code):]))
    return out,skipped

# Survivors of the sweep that cannot change any result of this source, each with its reason.
EQUIVALENT={}
