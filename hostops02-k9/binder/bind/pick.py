"""pick.py <json file> <key>[.<key>...] : print one value of a saved step output, refusing anything that is not a plain token.
Used by RUNBOOK.md so that no hash, time or path is ever copied by hand. Never ends in a traceback."""
import json
import re
import sys

try:
    value = json.load(open(sys.argv[1], encoding='utf-8'))
    for part in sys.argv[2].split('.'):
        value = value[part]
except (IndexError, KeyError, OSError, TypeError, ValueError) as error:
    sys.stderr.write('pick: no value (%s)\n' % type(error).__name__)
    raise SystemExit(1)
if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_.:/+#@=-]{1,400}', value) is None:
    sys.stderr.write('pick: %s is not a plain token\n' % sys.argv[2])
    raise SystemExit(1)
print(value)
