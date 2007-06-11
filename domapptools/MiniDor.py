#!/usr/bin/env python

# MiniDor.py
# John Jacobsen, NPX Designs, Inc., jacobsen\@npxdesigns.com
# Started: Thu May 31 20:19:00 2007

import os.path, os
from exc_string import exc_string
from minitimer import *
from re import search

EAGAIN   = 11    

class ExpectStringNotFoundException(Exception): pass

class MiniDor:
    def __init__(self, card=0, wire=0, dom='A'):
        self.card = card; self.wire=wire; self.dom=dom
        self.devFileName = os.path.join("/", "dev", "dhc%dw%dd%s" % (self.card, self.wire, self.dom))
        self.expectTimeout = 5000
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

    def fpgaRegs(self):
        f = file(os.path.join(self.cardpath(), "fpga"),"r")
        return f.read()
    
    def softboot(self):
        f = file(os.path.join(self.dompath(), "softboot"),"w")
        f.write("reset\n")
        f.close()

    def commReset(self):
        f = file(os.path.join(self.dompath(), "is-communicating"),"w")
        f.write("reset\n")
        f.close()

    def readExpect(self, file, expectStr, timeoutMsec=5000):
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

            if search(expectStr, contents):
                # break #<-- put this back to simulate failure
                return True
            time.sleep(0.10)
        raise ExpectStringNotFoundException("Expected string '%s' did not arrive in %d msec:\n%s" \
                                            % (expectStr, timeoutMsec, contents))

    def writeTimeout(self, fd, msg, timeoutMsec):
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

    def se(self, send, recv, timeout):
        "Send text, wait for recv text in timeout msec"
        try:
            self.writeTimeout(self.fd, send, timeout)
            self.readExpect(self.fd, recv, timeout)
        except Exception, e:
            return (False, exc_string())
        return (True, "")

    # Versions which return both success and error message
    def isInIceboot2(self):         return self.se("\r\n", ">", 3000)
    def isInConfigboot2(self):      return self.se("\r\n", "#", 3000)
    def configbootToIceboot2(self): return self.se("r",    ">", 5000)
    def icebootToConfigboot2(self): return self.se("boot-serial reboot\r\n", "#", 5000)
    def icebootToDomapp2(self):
        ok, txt = self.se("domapp\r\n", "domapp", 5000)
        if ok: time.sleep(5)
        return (ok, txt)

    def isInIceboot(self):         return self.isInIceboot2()[0]
    def isInConfigboot(self):      return self.isInConfigboot2()[0]
    def configbootToIceboot(self): return self.configbootToIceboot2[0]
    def icebootToConfigboot(self): return self.icebootToConfigboot2[0]
    def icebootToDomapp(self):     return self.icebootToDomapp[0]

def main():
    dom00a = MiniDor(0,0,'A')
    dom00a.open()
    dom00a.close()

if __name__ == "__main__": main()

