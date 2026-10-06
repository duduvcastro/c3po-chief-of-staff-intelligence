"""pytest wiring of K10's tests: the frozen core's test directory (family, conformance, hostemu, oslevel) on sys.path."""
import os
import sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','..','core','tests'))
sys.path.insert(0,HERE)
