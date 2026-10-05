"""pytest wiring of K6b's tests: the core's test directory (family, hostemu, conformance, oslevel) and this one on sys.path."""
import os
import sys
HERE=os.path.dirname(os.path.abspath(__file__))
# the core's tests directory: beside this operation, or where HOSTOPS02_TEST_CORE_TESTS says (the mutation harness runs a private copy of this directory)
sys.path.insert(0,os.environ.get('HOSTOPS02_TEST_CORE_TESTS') or os.path.join(HERE,'..','..','core-k6b','tests'))
sys.path.insert(0,HERE)
