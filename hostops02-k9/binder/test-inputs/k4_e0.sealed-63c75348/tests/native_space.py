"""The 200 GiB floor of the K9 filesystem on a test machine. K4-E0 refuses before any creation unless the filesystem
that will hold days/ has 214748364800 bytes available. A workstation may have them; a CI runner usually does not.
Space() keeps the real os.fstatvfs and raises f_bavail to the floor ONLY when the real value is below it, and records
that it did (substituted), so a native run still makes every real creating call; test_native's real-space test runs
without it and asserts what the real figure implies. Nothing else of the os module is touched."""
import os
import types

FLOOR=214748364800

class Space:
    def __enter__(self):
        self.real=os.fstatvfs;self.substituted=False;real=self.real
        def fstatvfs(fd):
            numbers=real(fd)
            if numbers.f_bavail*numbers.f_frsize>=FLOOR:return numbers
            self.substituted=True
            return types.SimpleNamespace(f_bavail=-(-FLOOR//numbers.f_frsize),f_frsize=numbers.f_frsize,f_bfree=numbers.f_bfree,f_blocks=numbers.f_blocks)
        os.fstatvfs=fstatvfs;return self
    def __exit__(self,*exception):
        os.fstatvfs=self.real;return False
