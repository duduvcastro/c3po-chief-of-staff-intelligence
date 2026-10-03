"""The two stand-ins of the Linux proof of C3, standard library only: a DNS server that answers the provider's name with
one address of the runner, and a TLS server on that address with a certificate of a throwaway authority. They exist so
that the probe's container, started with the source's own argv on the network bridge, reaches a server INSIDE the
runner and never the provider. Both bind the address they are given (the gateway of the network bridge on the
runner) and record what they saw: the DNS server each question (name and type), the TLS server each connection (the
server name the client sent, whether the handshake completed, the TLS version and cipher name the server negotiated, the
application bytes that arrived after it).

DnsStub modes: 'answer' (the provider's name has one A record, the given address; AAAA has none), 'nxdomain' (the
provider's name does not exist). Every other name does not exist in both modes.
TlsStub modes: 'good' (a leaf for the provider's name), 'other_name' (a leaf for another name, same authority),
'hang' (accepts and never answers), 'closed' (nothing listens: the port is refused).
Nothing here is part of the sealed source; the tests of linux_root (tests/test_linux_root.py) run both on 127.0.0.1."""
import socket
import ssl
import struct
import threading
import time

PROVIDER='socket.massive.com'
TYPE_A,TYPE_AAAA,CLASS_IN=1,28,1

def question_of(packet):
    """(identifier, flags, name, type, class, end of the question) of a query of one question; None for anything else."""
    if len(packet)<12:return None
    identifier,flags,questions=struct.unpack('!HHH',packet[:6])
    if flags&0x8000 or questions!=1:return None
    labels=[];index=12
    while True:
        if index>=len(packet):return None
        size=packet[index];index+=1
        if size==0:break
        if size>63 or index+size>len(packet):return None
        labels.append(packet[index:index+size].decode('ascii','replace').lower());index+=size
    if index+4>len(packet):return None
    kind,klass=struct.unpack('!HH',packet[index:index+4])
    return identifier,flags,'.'.join(labels),kind,klass,index+4

def response(packet,address,mode,name=PROVIDER):
    """The answer to one query: an A record of address for the provider's name in mode 'answer', no record for its
    other types, and NXDOMAIN for the provider's name in mode 'nxdomain' and for every other name."""
    found=question_of(packet)
    if found is None:return None
    identifier,flags,asked,kind,klass,end=found
    exists=asked==name and mode=='answer'
    answers=[struct.pack('!HHHIH',0xC00C,TYPE_A,CLASS_IN,5,4)+socket.inet_aton(address)] if exists and kind==TYPE_A and klass==CLASS_IN else []
    header=struct.pack('!HHHHHH',identifier,0x8000|0x0400|(flags&0x0100)|0x0080|(0 if exists else 3),1,len(answers),0,0)
    return header+packet[12:end]+b''.join(answers)

class DnsStub:
    def __init__(self,address,port=53,mode='answer'):
        self.address,self.mode,self.questions=address,mode,[]
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.socket.bind((address,port));self.port=self.socket.getsockname()[1]
        self.socket.settimeout(0.2);self.stopped=False
        self.thread=threading.Thread(target=self.serve);self.thread.daemon=True;self.thread.start()
    def serve(self):
        while not self.stopped:
            try:packet,client=self.socket.recvfrom(4096)
            except socket.timeout:continue
            except OSError:return
            found=question_of(packet)
            if found is not None:self.questions.append({'name':found[2],'type':found[3],'mode':self.mode})
            answer=response(packet,self.address,self.mode)
            if answer is not None:
                try:self.socket.sendto(answer,client)
                except OSError:pass
    def close(self):
        self.stopped=True;self.thread.join(2)
        try:self.socket.close()
        except OSError:pass

class TlsStub:
    def __init__(self,address,port,certificates,mode='good'):
        self.address,self.port,self.certificates=address,port,certificates;self.connections=[];self.listener=None;self.stopped=False
        self.contexts={}
        for name in ('leaf','other'):
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificates[name],certificates[name+'_key'])
            context.sni_callback=self.server_name;self.contexts[name]=context
        self.current={};self.set_mode(mode)
    def server_name(self,connection,name,context):self.current['server_name']=name
    def set_mode(self,mode):
        self.mode=mode
        if mode=='closed':
            self.stop_listener()
            return
        if self.listener is None:
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind((self.address,self.port));listener.listen(8);listener.settimeout(0.2);self.listener=listener
            thread=threading.Thread(target=self.serve,args=(listener,));thread.daemon=True;thread.start();self.thread=thread
    def serve(self,listener):
        while not self.stopped and self.listener is listener:
            try:connection,_=listener.accept()
            except socket.timeout:continue
            except OSError:return
            self.current={'mode':self.mode,'server_name':None,'handshake':False,'application_bytes':None,'version':None,'cipher':None}
            self.connections.append(self.current)
            try:
                if self.mode=='hang':
                    time.sleep(8);connection.close();continue
                connection.settimeout(5)
                try:tls=self.contexts['other' if self.mode=='other_name' else 'leaf'].wrap_socket(connection,server_side=True)
                except (ssl.SSLError,OSError):connection.close();continue
                self.current.update(handshake=True,version=tls.version(),cipher=(tls.cipher() or (None,))[0]);received=0
                try:
                    while True:
                        block=tls.recv(4096)
                        if not block:break
                        received+=len(block)
                except (ssl.SSLError,OSError):pass
                self.current['application_bytes']=received;tls.close()
            except Exception:
                try:connection.close()
                except OSError:pass
    def stop_listener(self):
        # On Linux close() does not wake a thread blocked in accept(), and the kernel keeps the socket listening until
        # that call returns: shut the listener down first and wait for the serving thread, so 'closed' is refused.
        listener,self.listener=self.listener,None
        if listener is None:return
        try:listener.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        listener.close()
        thread=getattr(self,'thread',None)
        if thread is not None:thread.join(2)
    def close(self):
        self.stopped=True;self.stop_listener()
