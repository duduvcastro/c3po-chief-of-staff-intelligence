"""Mandatory external verifier binding; no module loader/default attestation.

REAL needs an already-loaded approved module. Its source pin originates in the
independently approved rule, not a caller's receipt/source Binding. This does not
sandbox hostile Python within an approved supervisor; physical namespace and
original authority authenticity remain the verifier/installer's own scope.
"""
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType,FunctionType
import finite_batch as c

@dataclass(frozen=True)
class Verifier:
    mode:str
    identity:str
    source_sha256:str
    callback:object
    module:object=None
    def validate(self,expected,mode):
        c.need(type(expected)is dict and set(expected)=={'identity','source_sha256'}
               and self.mode==mode and self.identity==expected['identity']
               and self.source_sha256==expected['source_sha256'] and c.pin(self.source_sha256)
               and callable(self.callback),'EXTERNAL_VERIFIER_UNBOUND')
        c.need(mode in {'REAL','FIXTURE'},'EXTERNAL_VERIFIER_MODE')
        if mode=='REAL':
            c.need(type(self.module)is ModuleType and type(self.callback)is FunctionType
                   and getattr(self.module,self.identity,None)is self.callback
                   and self.callback.__globals__ is self.module.__dict__, 'REAL_VERIFIER_LOADED_MODULE_REQUIRED')
            path=Path(getattr(self.module,'__file__',''))
            c.need(path.is_absolute() and path.is_file() and not path.is_symlink()
                   and c.sha(path.read_bytes())==self.source_sha256,'REAL_VERIFIER_SOURCE_PIN_CHANGED')
        return self
    def invoke(self,expected,mode,*args):
        self.validate(expected,mode)
        c.need(self.callback(*args)is None,'EXTERNAL_VERIFIER_BOOLEAN_IS_NOT_ATTESTATION')
        self.validate(expected,mode)
