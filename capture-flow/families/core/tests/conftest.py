"""pytest wiring of the core's tests: this directory on sys.path, nothing else."""
import os
import sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
