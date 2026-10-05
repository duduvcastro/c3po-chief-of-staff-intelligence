"""Child interpreter for the native tests of the reader units: runs the source with its own, unmodified Native on a
private temporary tree, under the os-level record of the core's tests/oslevel.py, and dies at a named point.

usage: native_child.py <tree root> <fields json file> <death point>
Death points: after_link_<n> (after the n-th link, n = 1 ... 3), in_write_<n> (half of the n-th unit's bytes written).
The process ends by os._exit(137), as a killed process does: nothing is printed, no receipt exists, and what the tree
holds is what a later read would find. Never touches the real host: the only absolute path ever opened is the tree."""
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','..','core','tests'));sys.path.insert(0,HERE)
import family as f
import native_support
import ru

def dying(native,point):
    counts={'link':0,'write':0}
    class Dying(native):
        def write(self,fd,data):
            counts['write']+=1
            if point=='in_write_%d'%counts['write']:
                native.write(self,fd,data[:len(data)//2]);os._exit(137)
            return native.write(self,fd,data)
        def link(self,source,target,dir_fd):
            native.link(self,source,target,dir_fd);counts['link']+=1
            if point=='after_link_%d'%counts['link']:os._exit(137)
    return Dying()

def main():
    root,fields_path,point=sys.argv[1:4];k=ru.K()
    with open(fields_path,'rb') as stream:fields=json.loads(stream.read())
    docs=f.Docs(k,fields);old=os.umask(0o027)
    try:
        with native_support.Volume(root):receipt=docs.run(dying(k.m.Native,point))
    finally:os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'go16':docs.go16()},sort_keys=True)+'\n')

if __name__=='__main__':main()
