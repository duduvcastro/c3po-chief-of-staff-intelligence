"""pytest wiring of K12p's tests: the frozen core's test directory (family, conformance, hostemu, oslevel) on sys.path.
The operation directory is a sibling of core/ (core/ is a symbolic link to the sealed core; nothing in it is edited)."""
import os
import sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','..','core','tests'))
sys.path.insert(0,HERE)
