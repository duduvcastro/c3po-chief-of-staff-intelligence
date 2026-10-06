# Own primitive set for the bootstrap claim; no unlink, mkdir, rename, chmod, chown or truncate.
class NativeClaim:
    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)
    def write(self,fd,data):return os.write(fd,data)
    def fsync(self,fd):os.fsync(fd)
