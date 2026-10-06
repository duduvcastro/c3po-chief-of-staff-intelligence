"""Original pytest invocation plus read-only collection receipt. Never changes tests/items/reports."""
import json,os,sys
from pathlib import Path
import pytest
class Collection:
 def __init__(self):self.cases=[]
 def pytest_collection_finish(self,session):
  for item in session.items:
   parts=item.nodeid.split('::');file=parts[0].removesuffix('.py').replace('/','.')
   self.cases.append([file+'.'+'.'.join(parts[1:-1]) if len(parts)>2 else file,parts[-1]])
collector=Collection()
output=Path(sys.argv[1]);args=sys.argv[2:]
status=pytest.main(args,plugins=[collector])
fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
try:os.write(fd,(json.dumps({'cases':collector.cases,'pytest_returncode':int(status)},sort_keys=True)+'\n').encode())
finally:os.close(fd)
raise SystemExit(status)
