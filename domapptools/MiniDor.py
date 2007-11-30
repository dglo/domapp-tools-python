#!/usr/bin/env python

# MiniDor.py
# John Jacobsen, NPX Designs, Inc., jacobsen\@npxdesigns.com
# Started: Thu May 31 20:19:00 2007

import os.path, os
from stat import *
from exc_string import exc_string
from minitimer import *
from re import search, S, sub
from random import *
from struct import pack

EAGAIN   = 11    

class ExpectStringNotFoundException(Exception): pass
class WriteTimeoutException(Exception): pass
class DomappFileNotFoundException(Exception): pass

class MiniDor:
    DEFAULT_TIMEOUT = 10000
    def __init__(self, card=0, wire=0, dom='A'):
        self.card = card; self.wire=wire; self.dom=dom
        self.devFileName = os.path.join("/", "dev", "dhc%dw%dd%s" % (self.card, self.wire, self.dom))
        self.blockSize     = 4092
        self.domapp        = None
        
    def open(self):
        self.fd = os.open(self.devFileName, os.O_RDWR)
    
    def close(self):
        os.close(self.fd)
    
    def cardpath(self):
        return os.path.join("/", "proc", "driver", "domhub",
                            "card%d" % self.card)

    def dompath(self):
        return os.path.join("/", "proc", "driver", "domhub",
                            "card%d" % self.card,
                            "pair%d" % self.wire,
                            "dom%s"  % self.dom)

    def commStats(self):
        f = file(os.path.join(self.dompath(), "comstat"),"r")
        return f.read()

    def commStatReset(self):
        f = file(os.path.join(self.dompath(), "comstat"),"w")
        f.write("reset\n")
        f.close()

    def fpgaRegs(self):
        f = file(os.path.join(self.cardpath(), "fpga"),"r")
        return f.read()
    
    def softboot(self):
        f = file(os.path.join(self.dompath(), "softboot"),"w")
        f.write("reset\n")
        f.close()
        time.sleep(2) # Wait for FPGA to **start** reloading - assume user will re-open dev file

    def commReset(self):
        f = file(os.path.join(self.dompath(), "is-communicating"),"w")
        f.write("reset\n")
        f.close()

    def readTimeout(self, file, timeoutMsec=DEFAULT_TIMEOUT):
        "Read one message from dev file"
        t = MiniTimer(timeoutMsec)
        while not t.expired():
            try:
                contents = os.read(self.fd, self.blockSize)
                return contents
            except OSError, e:
                if e.errno == EAGAIN: time.sleep(0.01) # Nothing available
                else: raise
            except Exception: raise
        raise ExpectStringNotFoundException("Data from DOM not arrive in %d msec:\n" % timeoutMsec)

    def readExpect(self, file, expectStr, timeoutMsec=DEFAULT_TIMEOUT):
        "Read from dev file until expected string arrives - throw exception if it doesn't"
        contents = ""
        t = MiniTimer(timeoutMsec)
        while not t.expired():
            try:
                contents += os.read(self.fd, self.blockSize)
            except OSError, e:
                if e.errno == EAGAIN: time.sleep(0.01) # Nothing available
                else: raise
            except Exception: raise

            if search(expectStr, contents, S):
                # break #<-- put this back to simulate failure
                return contents
            time.sleep(0.10)
        raise ExpectStringNotFoundException("Expected string '%s' did not arrive in %d msec: got '%s'" \
                                            % (expectStr, timeoutMsec,
                                               sub('\r',' ', sub('\n', ' ', contents))))
    
    def writeTimeout(self, fd, msg, timeoutMsec=DEFAULT_TIMEOUT):
        nb0   = len(msg)
        t = MiniTimer(timeoutMsec)
        while not t.expired():
            try:
                nb = os.write(self.fd, msg)
                if nb==len(msg): return
                msg = msg[nb:]
            except OSError, e:
                if e.errno == EAGAIN: time.sleep(0.01)
                else: raise
            except Exception: raise
        raise WriteTimeoutException("Failed to write %d bytes to fd %d" % (nb0, fd))

    def echo(self, send, timeout=DEFAULT_TIMEOUT):
        "Send text, read it back, compare it, timeout msec"
        try:
            self.writeTimeout(self.fd, send, timeout)
            reply = self.readTimeout(self.fd, timeout)
            if(send != reply):
                return (False, "Reply (%d bytes) did NOT match sent data (%d bytes)" % (len(send), len(reply)))
        except Exception, e:
            return (False, exc_string())
        return (True, "")

    def se1(self, send, recv, timeout=DEFAULT_TIMEOUT):
        "Send and expect, but use exception handling"
        self.writeTimeout(self.fd, send, timeout)
        return self.readExpect(self.fd, recv, timeout)
        
    def se(self, send, recv, timeout=DEFAULT_TIMEOUT):
        "Send text, wait for recv text in timeout msec"
        try:
            self.writeTimeout(self.fd, send, timeout)
            self.readExpect(self.fd, recv, timeout)
        except Exception, e:
            return (False, exc_string())
        return (True, "")

    # Versions which return both success and error message
    fpgaReloadSleepTime = 8
    def isInIceboot2(self):         return self.se("\r\n", ">")
    def isInConfigboot2(self):      return self.se("\r\n", "#")
    def configbootToIceboot2(self): return self.se("r",    ">")
    def icebootToConfigboot2(self): return self.se("boot-serial reboot\r\n", "#")
    def icebootToDomapp2(self):     return self.se("domapp\r\n", "DOMAPP READY")
    def icebootToEcho2(self):
        ok, txt = self.se("echo-mode\r\n", "echo-mode")
        if ok: time.sleep(MiniDor.fpgaReloadSleepTime)
        return (ok, txt)
    def echoRandomPacket2(self, maxlen, timeout=DEFAULT_TIMEOUT):
        p = ""
        l = randint(1,maxlen)
        for i in xrange(0,l):
            p += pack("B", randint(0,255))
        return self.echo(p, timeout) # Give extra time in case of crappy comms
    
    def sendFile(self, fname, timeout=DEFAULT_TIMEOUT):
        "Dump file 'fname' to DOM"
        f = open(fname)
        while(True):
            buf = f.read(1000)
            if len(buf) == 0: break
            try:
                self.writeTimeout(self.fd, buf, timeout)
            except WriteTimoutException, t:
                return False
        f.close()
        return True
            
    def uploadDomapp2(self, domappFile):
        """
        Transition from iceboot to domapp by uploading 'domappFile',
        uncompressing it and executing from iceboot.  Load domapp FPGA first.
        """
        if not os.path.exists(domappFile): raise DomappFileNotFoundException(domappFile)
        size = os.stat(domappFile)[ST_SIZE]
        if size <= 0: return (False, "size error: %s %d bytes" % (domappFile, size))
        # Load domapp FPGA
        ok, txt = self.se("s\" domapp.sbi.gz\" find if fpga-gz endif\r\n", ">")
        if not ok: return (False, "%s\nFPGA reload failed!" % txt)
        # Prepare iceboot to receive file
        ok, txt = self.se("%d read-bin\r\n" % size, "read-bin")
        if not ok: return (False, "%s\nread-bin failed!" % txt)
        # Send file data
        if not self.sendFile(domappFile): return (False, "send file failed!")
        # See if iceboot is still ok
        ok, txt = self.se("\r\n", ">")
        if not ok: return (False, "%s\ndidn't get iceboot prompt!" % txt)
        # Exec the new domapp program
        ok, txt = self.se("gunzip exec\r\n", "READY")
        if not ok: return (False, "%s\ndidn't get READY!" % txt)
        return (True, "")
    
    def isInIceboot(self):         return self.isInIceboot2()[0]
    def isInConfigboot(self):      return self.isInConfigboot2()[0]
    def configbootToIceboot(self): return self.configbootToIceboot2()[0]
    def icebootToConfigboot(self): return self.icebootToConfigboot2()[0]
    def icebootToDomapp(self):     return self.icebootToDomapp2()[0]
    def icebootToEcho(self):       return self.icebootToEcho2()[0]
    
def main():
    dom00a = MiniDor(0,0,'A')
    dom00a.open()
    dom00a.close()

if __name__ == "__main__": main()

