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

DEFAULT_TIMEOUT = 10000


CSPAT = """(?msx)\
/dev/dhc(\d)w(\d)d(\w)\s*
RX:\s*(\d+)B,\s*MSGS=(\d+)\s*NINQ=(\d+)\s*PKTS=(\d+)\s*ACKS=(\d+)\s*
\s*BADPKT=(\d+)\s*BADHDR=(\d+)\s*BADSEQ=(\d+)\s*NCTRL=(\d+)\s*NCI=(\d+)\s*NIC=(\d+)\s*
TX:\s*(\d+)B,\s*MSGS=(\d+)\s*NOUTQ=(\d+)\s*RESENT=(\d+)\s*PKTS=(\d+)\s*ACKS=(\d+)\s*
NACKQ=(\d+)\s*NRETXB=(\d+)\s*RETXB_BYTES=(\d+)\s*NRETXQ=(\d+)\s*NCTRL=(\d+)\s*NCI=(\d+)\s*NIC=(\d+)\s*
NCONNECTS=(\d+)\s*NHDWRTIMEOUTS=(\d+)\s*OPEN=(\S+)\s*CONNECTED=(\S+)\s*
RXFIFO=(.+?)\ TXFIFO=(.+?)\ DOM_RXFIFO=(\S+)"""


class InvalidComstatException(Exception):
    pass


class CommStats:
    """
    Class to parse and store comstat values and to highlight changes in same
    
    >>> cstxt = '''
    ... /dev/dhc1w0dA
    ... RX: 4569685B, MSGS=283621 NINQ=0 PKTS=512429 ACKS=151303
    ... BADPKT=65535 BADHDR=0 BADSEQ=124 NCTRL=0 NCI=87266 NIC=120555
    ... TX: 39226409B, MSGS=95085 NOUTQ=0 RESENT=10955 PKTS=445981 ACKS=283865
    ... NACKQ=0 NRETXB=0 RETXB_BYTES=0 NRETXQ=0 NCTRL=0 NCI=889993 NIC=10140
    ...
    ... NCONNECTS=0 NHDWRTIMEOUTS=0 OPEN=true CONNECTED=true
    ... RXFIFO=empty TXFIFO=almost empty,empty DOM_RXFIFO=notfull'''
    >>> cs2txt = '''\
    ... /dev/dhc2w2dB
    ... RX: 6375556B, MSGS=357989 NINQ=0 PKTS=462676 ACKS=82745
    ... BADPKT=328 BADHDR=0 BADSEQ=0 NCTRL=0 NCI=78259 NIC=78421
    ... TX: 9673282B, MSGS=69570 NOUTQ=0 RESENT=7 PKTS=440842 ACKS=358089
    ... NACKQ=0 NRETXB=0 RETXB_BYTES=0 NRETXQ=0 NCTRL=0 NCI=782590 NIC=56413
    ...
    ... NCONNECTS=0 NHDWRTIMEOUTS=0 OPEN=true CONNECTED=true
    ... RXFIFO=empty TXFIFO=almost empty,empty DOM_RXFIFO=notfull'''
    >>> cs2 = CommStats(cs2txt)
    >>> cs = CommStats(cstxt)
    >>> cs.card, cs.pair, cs.dom
    (1, 0, 'A')
    >>> cs.rxbytes, cs.rxmsgs, cs.inq, cs.rxpkts, cs.rxacks
    (4569685L, 283621L, 0, 512429L, 151303L)
    >>> cs.badpkt, cs.badhdr, cs.badseq, cs.rxctrl, cs.rxci, cs.rxic
    (65535, 0, 124, 0, 87266L, 120555L)
    >>> cs.txbytes, cs.txmsgs, cs.outq, cs.resent, cs.txpkts, cs.txacks
    (39226409L, 95085L, 0, 10955, 445981L, 283865L)
    >>> cs.nackq, cs.nretxb, cs.retxb_bytes, cs.nretxq, cs.nctrl, cs.txci, cs.txic
    (0, 0, 0, 0, 0, 889993L, 10140L)
    >>> cs.nconnects, cs.hwtimeouts, cs.open, cs.connected
    (0, 0, True, True)
    >>> cs.rxfifo, cs.txfifo, cs.dom_rxfifo
    ('empty', 'almost empty,empty', 'notfull')
    >>> cs-cs
    {}
    >>> from copy import deepcopy
    >>> cs1 = deepcopy(cs)
    >>> cs1.rxbytes += 239
    >>> cs1-cs
    {'rxbytes': 239L}
    >>> cs1.rxpkts += 3
    >>> (cs1-cs)['rxpkts']
    3L
    >>> cs1.rxfifo = "not empty"
    >>> (cs1-cs)['rxfifo']
    'empty -> not empty'
    """
    def __init__(self, txt):
        if txt is None:
            raise InvalidComstatException('No string argument supplied!')
        m = search(CSPAT, txt)
        if not m:
            raise InvalidComstatException('Invalid comstats text!  "%s"' % txt)
        groups = list(m.groups())
        self.card = int(groups.pop(0))
        self.pair = int(groups.pop(0))
        self.dom = groups.pop(0)
        self.rxbytes = long(groups.pop(0))
        self.rxmsgs = long(groups.pop(0))
        self.inq = int(groups.pop(0))
        self.rxpkts = long(groups.pop(0))
        self.rxacks = long(groups.pop(0))
        self.badpkt = int(groups.pop(0))
        self.badhdr = int(groups.pop(0))
        self.badseq = int(groups.pop(0))
        self.rxctrl = int(groups.pop(0))
        self.rxci = long(groups.pop(0))
        self.rxic = long(groups.pop(0))
        self.txbytes = long(groups.pop(0))
        self.txmsgs = long(groups.pop(0))
        self.outq = int(groups.pop(0))
        self.resent = int(groups.pop(0))
        self.txpkts = long(groups.pop(0))
        self.txacks = long(groups.pop(0))
        self.nackq = int(groups.pop(0))
        self.nretxb = int(groups.pop(0))
        self.retxb_bytes = int(groups.pop(0))
        self.nretxq = int(groups.pop(0))
        self.nctrl = int(groups.pop(0))
        self.txci = long(groups.pop(0))
        self.txic = long(groups.pop(0))
        self.nconnects = int(groups.pop(0))
        self.hwtimeouts = int(groups.pop(0))
        self.open = (groups.pop(0)=='true') and True or False
        self.connected = (groups.pop(0)=='true') and True or False
        self.rxfifo = groups.pop(0)
        self.txfifo = groups.pop(0)
        self.dom_rxfifo = groups.pop(0)
        
    def __sub__(self, cs):
        ret = {}
        keys = self.__dict__.keys()
        keys.sort()
        for key in keys:
            s, c = self.__dict__[key], cs.__dict__[key]
            if s != c:
                if type(s) in (int, long) and type(c) in (int, long):
                    ret[key] = int(s-c)
                else:
                    ret[key] = "%s -> %s" % (c, s)
        return ret
    
                
class MiniDor:
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

    def iceboot_get_buffer_dump(self):
        self.writeTimeout(self.fd,
                          '0 30 0 ?DO $80000000 i 4 * + @ . drop LOOP\r\n')
        return self.readExpect(self.fd, '>')

    def get_fpga_versions(self):
        self.writeTimeout(self.fd, 'fpga-versions\r\n')
        return self.readExpect(self.fd, '>')
        
    def icebootReset(self):
        pat = """(?mx)
                 ^        # newline
                 \        # single space
                 Iceboot
                 \        # single space
                 \(.+?\)  # something in parens
                 \ build\ # ' build '
                 (\d+)    # actual version number
                 \.{5}    # five dots
                 \s+>     # whitespace and prompt
                 """
        self.writeTimeout(self.fd, 'reboot\r\n')
        txt = self.readExpect(self.fd, pat)
        version = int(search(pat, txt).group(1))
        return txt, version    

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
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()

