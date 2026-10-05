"""pytest wiring of the K9R tests: the core's test directory (family, hostemu, conformance, oslevel) and this one on sys.path."""
import os
import sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','..','core','tests'))
sys.path.insert(0,HERE)
