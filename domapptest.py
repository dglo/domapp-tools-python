#!/usr/bin/env python

# domapptest.py
# John Jacobsen, NPX Designs, Inc., jacobsen\@npxdesigns.com
# Started: Wed May  9 21:57:21 2007

from __future__ import generators
import time, threading, os, sys
from re import search, sub
from domapptools.dor import *
from domapptools.exc_string import exc_string
from domapptools.domapp import *
from math import sqrt
import os.path
import optparse

def SNClockOk(clock, prevClock, bins, prevBins):
    DT = 65536
    if clock != prevClock + prevBins*DT: return False
    return True

class ExpectStringNotFoundException(Exception): pass
class WriteTimeoutException(Exception):         pass

EAGAIN   = 11    

class MalformedDeltaCompressedHitBuffer(Exception): pass

class DeltaHit:
    def __init__(self, hitbuf):
        self.words   = unpack('<2i', hitbuf[0:8])
        iscompressed = (self.words[0] & 0x80000000) >> 31
        if not iscompressed:
            raise MalformedDeltaCompressedHitBuffer("no compression bit found")
        self.hitsize = self.words[0] & 0x7FF
        self.natwdch = (self.words[0] & 0x3000) >> 12
        self.trigger = (self.words[0] & 0x7ffe0000) >> 18
        self.atwd_avail = ((self.words[0] & 0x4000) != 0)
        self.atwd_chip  = (self.words[0] & 0x0800) >> 11
        self.fadc_avail = ((self.words[0] & 0x8000) != 0)
        if self.trigger & 0x01: self.is_spe    = True
        else:                   self.is_spe    = False
        if self.trigger & 0x02: self.is_mpe    = True
        else:                   self.is_mpe    = False
        if self.trigger & 0x04: self.is_beacon = True
        else:                   self.is_beacon = False

    def __repr__(self):
        return """
W0 0x%08x W1 0x%08x
Hit size = %4d     ATWD avail   = %4d     FADC avail = %4d
A/B      = %4d     ATWD#        = %4d     Trigger word = 0x%04x
"""                         % (self.words[0], self.words[1], self.hitsize,
                               self.atwd_avail, self.fadc_avail,
                               self.atwd_chip, self.natwdch, self.trigger)

class DeltaHitBuf:
    def __init__(self, hitdata):
        if len(hitdata) < 8: raise MalformedDeltaCompressedHitBuffer()
        junk, nb   = unpack('>HH', hitdata[0:4])
        junk, tmsb = unpack('>HH', hitdata[4:8])
        nb -= 8
        # print "len %d tmsb %d" % (nb, tmsb)
        if nb <= 0: raise MalformedDeltaCompressedHitBuffer()
        self.payload = hitdata[8:]
        
    def next(self):
        rest = self.payload
        while(len(rest) > 8):
            words = unpack('<2i', rest[0:8])
            hitsize = words[0] & 0x7FF
            yield DeltaHit(rest[0:hitsize])
            rest = rest[hitsize:]

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
    
    def dompath(self):
        return os.path.join("/", "proc", "driver", "domhub",
                            "card%d" % self.card,
                            "pair%d" % self.wire,
                            "dom%s"  % self.dom)
    
    def softboot(self):
        f = file(os.path.join(self.dompath(), "softboot"),"w")
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
    
    def isInIceboot(self):         return self.se("\r\n", ">", 3000)
    def isInConfigboot(self):      return self.se("\r\n", "#", 3000)
    def configbootToIceboot(self): return self.se("r",    ">", 5000)
    def icebootToConfigboot(self): return self.se("boot-serial reboot\r\n", "#", 5000)            
    def icebootToDomapp(self):
        ok, txt = self.se("domapp\r\n", "domapp", 5000)
        if ok: time.sleep(3)
        return (ok, txt)

class DOMTest:
    STATE_ICEBOOT    = "ib"
    STATE_DOMAPP     = "da"
    STATE_CONFIGBOOT = "cb"
    STATE_ECHO       = "em"
    STATE_UNKNOWN    = "??"
    
    def __init__(self, card, wire, dom, dor, start=STATE_ICEBOOT, end=STATE_ICEBOOT):
        self.card       = card
        self.wire       = wire
        self.dom        = dom
        self.dor        = dor
        self.startState = start
        self.endState   = end

        self.runLength  = 10
        self.debugMsgs  = []
        self.result     = None
        self.summary    = ""
        
    def setRunLength(self, l): self.runLength = l

    def getDebugTxt(self):
        str = ""
        if self.debugMsgs:
            for m in self.debugMsgs:
                if m != "": str += "%s\n" % m
        return str
    
    def name(self):
        str = repr(self)
        m = search(r'\.(\S+) instance', str)
        if(m): return m.group(1)
        return str
    
    def run(self, fd): pass

class ConfigbootToIceboot(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_CONFIGBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        ok, txt = self.dor.configbootToIceboot()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("Could not transition into iceboot")
            self.debugMsgs.append(txt)
        else:
            ok, txt = self.dor.isInIceboot()
            if not ok:
                self.result = "FAIL"
                self.debugMsgs.append("check for iceboot prompt failed")
                self.debugMsgs.append(txt)
            else:
                self.result = "PASS"
                        
class DomappToIceboot(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        self.dor.softboot()
        ok, txt = self.dor.isInIceboot()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"

class IcebootToDomapp(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_DOMAPP)
    def run(self, fd):
        ok, txt = self.dor.icebootToDomapp()
        if not ok:        
            self.result = "FAIL"
            self.debugMsgs.append("could not transition into domapp")
            self.debugMsgs.append(txt)
        else:
            # FIXME - test w/ domapp message here
            self.result = "PASS"

class CheckIceboot(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        ok, txt = self.dor.isInIceboot()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"
            
class IcebootToConfigboot(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_CONFIGBOOT)
    def run(self, fd):
        ok, txt = self.dor.icebootToConfigboot()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("could not transition into configboot")
            self.debugMsgs.append(txt)
        else:
            ok, txt =  self.dor.isInConfigboot()
            if not ok:
                self.result = "FAIL"
                self.debugMsgs.append("check for iceboot prompt failed")
                self.debugMsgs.append(txt)
            else:
                self.result = "PASS"

class CheckConfigboot(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_CONFIGBOOT, end=DOMTest.STATE_CONFIGBOOT)
    def run(self, fd):
        ok, txt = self.dor.isInConfigboot()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"

class GetDomappRelease(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.summary = domapp.getDomappVersion()
            self.result = "PASS"
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())

class DOMIDTest(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.summary = domapp.getMainboardID()
            self.result = "PASS"
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())

def setDAC(domapp, dac, val): domapp.writeDAC(dac, val)
def setDefaultDACs(domapp):
    setDAC(domapp, DAC_ATWD0_TRIGGER_BIAS, 850)
    setDAC(domapp, DAC_ATWD1_TRIGGER_BIAS, 850)
    setDAC(domapp, DAC_ATWD0_RAMP_RATE, 350)
    setDAC(domapp, DAC_ATWD1_RAMP_RATE, 350)
    setDAC(domapp, DAC_ATWD0_RAMP_TOP, 2300)
    setDAC(domapp, DAC_ATWD1_RAMP_TOP, 2300)
    setDAC(domapp, DAC_ATWD_ANALOG_REF, 2250)
    setDAC(domapp, DAC_PMT_FE_PEDESTAL, 2130)
    setDAC(domapp, DAC_SINGLE_SPE_THRESH, 560)
    setDAC(domapp, DAC_MULTIPLE_SPE_THRESH, 650)
    setDAC(domapp, DAC_FADC_REF, 800)
    setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 80)

def unpackMoni(monidata):
    while monidata and len(monidata)>=4:
        moniLen, moniType = unpack('>hh', monidata[0:4])
        if moniType == 0xCB:
            msg = monidata[10:moniLen]
            yield msg
        if moniType == 0xCA:
            kind,    = unpack('b', monidata[10])
            subkind, = unpack('b', monidata[11])
            if kind == 2 and subkind == 0x10:
                txt = "ENABLE HV"
            elif kind == 2 and subkind == 0x12:
                txt = "ENABLE HV"
            elif kind == 2 and subkind == 0x0E:
                val, = unpack('>h', monidata[12:14])
                txt = "SET HV(%d)" % val
            elif kind == 2 and subkind == 0x0D:
                dac, val = unpack('>bxh', monidata[12:16])
                txt = "SET DAC(%d<-%d)" % (dac,val)
            elif kind == 2 and subkind == 0x2D:
                mode, = unpack('b', monidata[12])
                txt = "SET LC MODE(%d)" % mode
            elif kind == 2 and subkind == 0x2F:
                w = unpack('>LLLL', monidata[12:28])
                txt = "SET LC WIN(%d %d %d %d)" % w
            else:
                txt = "0x%0x-0x%0x" % (kind,subkind)
            yield "[STATE CHANGE %s]" % txt
        monidata = monidata[moniLen:]

def getLastMoniMsgs(domapp):
    """
    Drain buffered monitoring messages - return concatenated
    as big ASCII string
    """
    ret = ""
    try:
        while True:
            monidata = domapp.getMonitorData()
            if len(monidata) == 0: break
            for msg in unpackMoni(monidata): ret += msg + "\n"
    except Exception, e:
        ret +=("GET MONI DATA FAILED: %s" % exc_string())
    return ret

class PedestalStabilityTest(DOMTest):
    "Measure pedestal stability by taking an average over several tries"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)
        
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)        
        self.result = "PASS"
        NOMINAL_HV_VOLTS   = 800 # Is this the best value?
        ATWD_PEDS_PER_LOOP = 100 
        FADC_PEDS_PER_LOOP = 200 
        MAX_ALLOWED_RMS    = 1.0
        HV_TOLERANCE       = 20   # HV must be correct to 10 Volts (20 units)
        numloops           = 100
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.selectMUX(255)
            domapp.setMonitoringIntervals()

            ### Turn on HV
            domapp.enableHV()
            domapp.setHV(NOMINAL_HV_VOLTS*2)
            time.sleep(2)
            hvadc, hvdac = domapp.queryHV()
            self.debugMsgs.append("HV: read %d V (ADC) %d V (DAC)" % (hvadc/2,hvdac/2))
            if abs(hvadc-NOMINAL_HV_VOLTS*2) > HV_TOLERANCE:
                raise Exception("HV deviates too much from set value!")
            
            ### Collect pedestals N times

            atwdSum   = [[[0. for samp in xrange(128)] for ch in xrange(4)] for ab in xrange(2)]
            atwdSumSq = [[[0. for samp in xrange(128)] for ch in xrange(4)] for ab in xrange(2)]
            # Wheeeee!
            fadcSum   = [0. for samp in xrange(256)]
            fadcSumSq = [0. for samp in xrange(256)]

            for loop in xrange(numloops):
                # Do the collection
                domapp.collectPedestals(ATWD_PEDS_PER_LOOP,
                                        ATWD_PEDS_PER_LOOP,
                                        FADC_PEDS_PER_LOOP)
                # Check number of forced triggers
                buf = domapp.getNumPedestals()
                atwd0, atwd1, fadc = unpack('>LLL', buf)
                self.debugMsgs.append("Collected %d %d %d pedestals" % (atwd0, atwd1, fadc))
                if(atwd0 != ATWD_PEDS_PER_LOOP or
                   atwd1 != ATWD_PEDS_PER_LOOP or
                   fadc != FADC_PEDS_PER_LOOP): raise Exception("Pedestal collection shortfall!")

                # Read out pedestal sums
                buf = domapp.getPedestalAverages()
                self.debugMsgs.append("Got %d bytes of pedestal averages" % len(buf))
                
                # Tally sums for RMS
                # ...not the most efficient impl., but relatively clear:
                for ab in xrange(2):
                    for ch in xrange(4):
                        for samp in xrange(128):
                            idx = (ab*4 + ch)*128 + samp
                            val, = unpack('>h', buf[idx*2:idx*2+2])
                            # self.debugMsgs.append("ATWD[%d][%d][%d] = %2.3f" % (ab,ch,samp,val))
                            atwdSum[ab][ch][samp]   += float(val)
                            atwdSumSq[ab][ch][samp] += float(val)**2

                for samp in xrange(256):
                    idx = 8*128 + samp
                    val, = unpack('>H', buf[idx*2:idx*2+2])
                    fadcSum[samp]   += float(val)
                    fadcSumSq[samp] += float(val)**2
                    
            # Compute final RMS
            maxrms = 0.
            for ab in xrange(2):
                for ch in xrange(4):
                    for samp in xrange(128):
                        rms = sqrt((atwdSumSq[ab][ch][samp]/float(numloops)) -\
                                   ((atwdSum[ab][ch][samp]/float(numloops))**2))
                        self.debugMsgs.append("ATWD rms[%d][%d][%d] = %2.3f" % (ab,ch,samp,rms))
                        if rms > maxrms: maxrms = rms
            for samp in xrange(256):
                rms = sqrt(fadcSumSq[samp]/float(numloops) -\
                           (fadcSum[samp]/float(numloops))**2)
                self.debugMsgs.append("FADC rms[%d] = %2.3f" % (samp, rms))
                if rms > maxrms: maxrms = rms

            ### Turn off HV
            domapp.setHV(0)
            domapp.disableHV()

            if maxrms > MAX_ALLOWED_RMS:
                raise Exception("Maximum allowed RMS (%2.3f) exceeeded (%2.3f)!" %\
                                (MAX_ALLOWED_RMS, maxrms))

        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())
            self.debugMsgs.append(getLastMoniMsgs(domapp))
            return
        
class DeltaCompressionBeaconTest(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)

    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        self.result = "PASS"
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.setPulser(mode=BEACON, rate=100)
            domapp.selectMUX(255)
            domapp.setMonitoringIntervals()
            # Set delta compression format
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)
            domapp.startRun()
        # fixme - collect moni for ALL failures
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())
            self.debugMsgs.append(getLastMoniMsgs(domapp))
            return

        # collect data
        t = MiniTimer(5000)
        while not t.expired():
            self.debugMsgs.append(getLastMoniMsgs(domapp))

            # Fetch hit data
            good = True
            try:
                hitdata = domapp.getWaveformData()
                if len(hitdata) > 0:
                    hitBuf = DeltaHitBuf(hitdata)
                    for hit in hitBuf.next():
                        if hit.is_beacon and hit.natwdch < 3:
                            self.debugMsgs.append("Beacon hit has insufficient readouts!!!")
                            self.debugMsgs.append(`hit`)
                            good = False
                            break
            except Exception, e:
                self.result = "FAIL"
                self.debugMsgs.append("GET WAVEFORM DATA FAILED: %s" % exc_string())
                self.debugMsgs.append(getLastMoniMsgs(domapp))
                break
            
            if not good:
                self.result = "FAIL"
                break

        # end run
        try:
            domapp.endRun()
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append("END RUN FAILED: %s" % exc_string())
            self.debugMsgs.append(getLastMoniMsgs(domapp))
            
class SNTest(DOMTest):
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor, start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)

    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        self.result = "PASS"
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.setPulser(mode=FE_PULSER, rate=100)
            domapp.selectMUX(255)
            domapp.setEngFormat(0, 4*(2,), (32, 0, 0, 0))
            domapp.enableSN(6400, 0)
            domapp.setMonitoringIntervals()
            domapp.startRun()
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())
            self.debugMsgs.append(getLastMoniMsgs(domapp))
            return
            
        prevBins, prevClock = None, None

        for i in xrange(0,self.runLength):

            self.debugMsgs.append(getLastMoniMsgs(domapp))
            
            # Fetch supernova

            try:
                sndata = domapp.getSupernovaData()
            except Exception, e:
                self.result = "FAIL"
                self.debugMsgs.append("GET SN DATA FAILED: %s" % exc_string())
                self.debugMsgs.append(getLastMoniMsgs(domapp))
                break

            if sndata      == None: continue
            if len(sndata) == 0:    continue
            if len(sndata) < 10:
                self.result = "FAIL"
                self.debugMsgs.append("SN DATA CHECK: %d bytes" % len(sndata))
                break
            bytes, fmtid, t5, t4, t3, t2, t1, t0 = unpack('>hh6B', sndata[0:10])
            clock  = ((((t5 << 8L | t4) << 8L | t3) << 8L | t2) << 8L | t1) << 8L | t0
            scalers = unpack('%dB' % (len(sndata) - 10), sndata[10:])
            bins    = len(scalers)

            if prevBins and not SNClockOk(clock, prevClock, bins, prevBins):
                self.result = "FAIL"
                self.debugMsgs.append("CLOCK CHECK: %d %d %d %d->%d %x->%x" % (i, bytes, fmtid, prevBins,
                                                                               bins, prevClock, clock))
                self.debugMsgs.append(getLastMoniMsgs(domapp))
                break
            
            prevClock = clock
            prevBins  = bins

            try:
                time.sleep(1)
            except:
                try: domapp.endRun()
                except: pass
                raise SystemExit
            
        try:
            domapp.endRun()
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append("END RUN FAILED: %s" % exc_string())
            self.debugMsgs.append(getLastMoniMsgs(domapp))

class TestingSet:
    "Class for running multiple tests on a group of DOMs in parallel"
    def __init__(self, domDict, testNameList, stopOnFail=False):
        self.domDict     = domDict
        self.testList    = testNameList
        self.threads     = {}
        self.numpassed   = 0
        self.numfailed   = 0
        self.numtests    = 0
        self.counterLock = threading.Lock()
        self.stopOnFail  = stopOnFail
        
    def cycle(self, testList, startState, c, w, d):
        """
        Cycle through all tests, visiting first all the ones in the current state, then
        moving on to another state, and so on until all in-state and state-change tests
        have completed
        """
        
        state = startState
        doneDict = {}
        while True:
            allDone = True
            allDoneThisState = True
            nextTest = None
            nextStateChangeTest = None
            for test in testList:
                if (test not in doneDict or not doneDict[test]) and test.startState == state:
                    allDone = False
                    nextTest = test
                    if test.endState == state:
                        allDoneThisState = False
                        break
                    else:
                        nextStateChangeTest = test
            if allDone: return
            elif allDoneThisState:
                nextTest = nextStateChangeTest
            state = nextTest.endState
            doneDict[nextTest] = True
            yield nextTest

    def doAllTests(self, domid, c, w, d):
        startState = DOMTest.STATE_ICEBOOT
        testObjList = []
        dor = MiniDor(c, w, d)
        dor.open()
        for testName in self.testList:
            testObjList.append(testName(c, w, d, dor))
        for test in self.cycle(testObjList, startState, c, w, d):
            test.run(dor.fd)
            if(test.startState != test.endState): # If state change, flush buffers etc. to get clean IO
                dor.close()
                dor.open()

            sf = False
            #### LOCK - have to protect shared counters, as well as TTY...
            self.counterLock.acquire()
            print "%s%s%s %s->%s %s: %s %s" % (c,w,d, test.startState,
                                                     test.endState, test.name(), test.result, test.summary)
            if test.result == "PASS":
                self.numpassed += 1
            else:
                self.numfailed += 1
                dbg = test.getDebugTxt()
                print "################################################"
                if len(dbg) > 0: print test.getDebugTxt()
                print "################################################"
                if self.stopOnFail: sf = True
            self.numtests += 1
            self.counterLock.release()
            #### UNLOCK
            if sf: return # Quit upon first failure
            
    def runThread(self, domid):
        c, w, d = self.domDict[domid]
        self.doAllTests(domid, c,w,d)
        
    def go(self): 
        for dom in self.domDict:
            self.threads[dom] = threading.Thread(target=self.runThread, args=(dom, ))
            self.threads[dom].start()
        for dom in self.domDict:
            try:
                self.threads[dom].join()
            except KeyboardException:
                raise SystemExit
            except Exception, e:
                print exc_string()
                raise SystemExit
        
    def summary(self):
        "show summary of results"
        return "Passed tests: %d   Failed tests: %d   Total: %d" % (self.numpassed,
                                                                    self.numfailed,
                                                                    self.numtests)

# FIXME - updated for new pythonic package distribution def getDomappToolsVersion():
#    f = open("/usr/local/share/domapp-tools-version")
#    return sub(r'\n','', f.readline())

def main():
    p = optparse.OptionParser()

    p.add_option("-s", "--stop-fail",
                 action="store_true",
                 dest="stopFail",     help="Stop at first failure for each DOM")

    p.add_option("-V", "--hv-tests",
                 action="store_true",
                 dest="doHVTests",    help="Perform HV tests")

    p.set_defaults(stopFail         = False,
                   doHVTests        = False)
    opt, args = p.parse_args()

    # print "domapp-tools revision: %s" % getDomappToolsVersion()
    
    dor = Driver()
    print "dor-driver release: %s" % dor.release
    dor.enable_blocking(0)
    domDict = dor.get_active_doms()
    
    startState = DOMTest.STATE_ICEBOOT # FIXME: what if it's not?
    
    ListOfTests = [IcebootToConfigboot, CheckConfigboot, ConfigbootToIceboot,
                   CheckIceboot, IcebootToDomapp, 
                   GetDomappRelease, DOMIDTest, DeltaCompressionBeaconTest,
                   SNTest, 
                   DomappToIceboot]

    if opt.doHVTests:
        ListOfTests.append(PedestalStabilityTest)
    
    testSet = TestingSet(domDict, ListOfTests, opt.stopFail)
    testSet.go()
    print testSet.summary()
    
    raise SystemExit

if __name__ == "__main__": main()
