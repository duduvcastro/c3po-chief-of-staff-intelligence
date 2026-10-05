"""pytest wiring of K9W's tests: the frozen core's test directory (family, conformance, hostemu, oslevel) on sys.path.
The operation directory is a sibling of core/ (a symbolic link to the sealed core; nothing in it is edited)."""
import os
import sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.environ.get('HOSTOPS02_TEST_CORE_TESTS') or os.path.join(HERE,'..','..','core','tests'))
sys.path.insert(0,HERE)
