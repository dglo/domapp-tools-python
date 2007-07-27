#!/usr/bin/env python

# domapptest.py
# John Jacobsen, NPX Designs, Inc., john@mail.npxdesigns.com
# Started: Wed May  9 21:57:21 2007
from __future__ import generators
import time, threading, os, sys
from re import search, sub

from domapptools.dor import *
from domapptools.exc_string import exc_string
from domapptools.domapp import *
from domapptools.MiniDor import *
from domapptools.DeltaHit import *

from math import sqrt
import os.path
import optparse

class WriteTimeoutException(Exception):             pass
class RepeatedTestChangesStateException(Exception): pass

class DOMTest:
    STATE_ICEBOOT    = "ib"
    STATE_DOMAPP     = "da"
    STATE_CONFIGBOOT = "cb"
    STATE_ECHO       = "em"
    STATE_UNKNOWN    = "??"
    
    def __init__(self, card, wire, dom, dor, start=STATE_ICEBOOT, end=STATE_ICEBOOT, runLength=None):
        self.card       = card
        self.wire       = wire
        self.dom        = dom
        self.dor        = dor
        self.startState = start
        self.endState   = end

        self.runLength  = runLength
        self.debugMsgs  = []
        self.result     = None
        self.summary    = ""

    def appendMoni(self, domapp):
        m = getLastMoniMsgs(domapp)
        if m != []: self.debugMsgs.append(m)
        
    def changesState(self):
        return self.startState != self.endState
    
    def setRunLength(self, l):
        self.runLength = l

    def getDebugTxt(self):
        str = ""
        if self.debugMsgs:
            for m in self.debugMsgs:
                if m != "": str += "%s\n" % m
        return str

    def clearDebugTxt(self): self.debugMsgs = []
    
    def name(self):
        str = repr(self)
        m = search(r'\.(\S+) instance', str)
        if(m): return m.group(1)
        return str
    
    def run(self, fd): pass

class ConfigbootToIceboot(DOMTest):
    "Make sure transition from configboot to iceboot succeeds"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_CONFIGBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        ok, txt = self.dor.configbootToIceboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("Could not transition into iceboot")
            self.debugMsgs.append(txt)
        else:
            ok, txt = self.dor.isInIceboot2()
            if not ok:
                self.result = "FAIL"
                self.debugMsgs.append("check for iceboot prompt failed")
                self.debugMsgs.append(txt)
            else:
                self.result = "PASS"
                        
class DomappToIceboot(DOMTest):
    "Make sure (softboot) transition from domapp to iceboot succeeds"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        self.dor.softboot()
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"

class EchoToIceboot(DOMTest):
    "Make sure (softboot) transition from echo-mode to iceboot succeeds"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ECHO, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        self.dor.softboot()
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"
    
class IcebootToDomapp(DOMTest):
    "Make sure transition from iceboot to domapp succeeds"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_DOMAPP)
    def run(self, fd):
        ok, txt = self.dor.icebootToDomapp2()
        if not ok:        
            self.result = "FAIL"
            self.debugMsgs.append("could not transition into domapp")
            self.debugMsgs.append(txt)
        else:
            # FIXME - test w/ domapp message here
            self.result = "PASS"

class CheckIceboot(DOMTest):
    "Make sure I'm in iceboot when I think I should be"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"


class SoftbootCycle(DOMTest):
    """
    Verify softboot behavior, in particular the following sequence:
       iceboot -> domapp -> check domapp -> comm reset ->
       softboot -> comm reset -> check iceboot
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        # Verify iceboot
        self.result = "PASS"
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("first check for iceboot prompt failed")
            self.debugMsgs.append(txt)
            return

        # Transition to domapp
        ok, txt = self.dor.icebootToDomapp2()
        if not ok:        
            self.result = "FAIL"
            self.debugMsgs.append("could not transition into domapp")
            self.debugMsgs.append(txt)
            return

        # Check domapp by fetching release
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            domapp.getDomappVersion()
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())
            return

        # Collect driver/FPGA stats
        self.debugMsgs.append("Before first comm. reset:")
        self.debugMsgs.append(self.dor.commStats())
        self.debugMsgs.append(self.dor.fpgaRegs())
        # Issue comms reset
        self.dor.commReset()
        # Collect driver/FPGA stats
        self.debugMsgs.append("After first comm. reset, before softboot:")
        self.debugMsgs.append(self.dor.commStats())
        self.debugMsgs.append(self.dor.fpgaRegs())
        # Softboot DOM
        self.dor.softboot()
        # Collect driver/FPGA stats
        self.debugMsgs.append("After softboot, before 2nd comm. reset:")
        self.debugMsgs.append(self.dor.commStats())
        self.debugMsgs.append(self.dor.fpgaRegs())
        # Issue comms reset again
        self.dor.commReset()
        # Collect driver/FPGA stats
        self.debugMsgs.append("After 2nd comm. reset:")
        self.debugMsgs.append(self.dor.commStats())
        self.debugMsgs.append(self.dor.fpgaRegs())
        # Verify iceboot again
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("second check for iceboot prompt failed")
            self.debugMsgs.append(txt)
            return
        else:
            self.result = "PASS"
            

class IcebootToConfigboot(DOMTest):
    "Make sure transition from iceboot to configboot succeeds"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_CONFIGBOOT)
    def run(self, fd):
        ok, txt = self.dor.icebootToConfigboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("could not transition into configboot")
            self.debugMsgs.append(txt)
        else:
            ok, txt =  self.dor.isInConfigboot2()
            if not ok:
                self.result = "FAIL"
                self.debugMsgs.append("check for iceboot prompt failed")
                self.debugMsgs.append(txt)
            else:
                self.result = "PASS"

class CheckConfigboot(DOMTest):
    "Check that I'm really in configboot when I think I am"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_CONFIGBOOT, end=DOMTest.STATE_CONFIGBOOT)
    def run(self, fd):
        ok, txt = self.dor.isInConfigboot2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"

class IcebootToEcho(DOMTest):
    "Make sure transition from iceboot to echo-mode succeeds"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ECHO)
    def run(self, fd):
        ok, txt = self.dor.icebootToEcho2()
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("could not transition into echo-mode")
            self.debugMsgs.append(txt)
        else:
            self.result = "PASS"

class EchoTest(DOMTest):
    "Perform echo test of 100 variable-length random packets, when DOM is in echo mode"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ECHO, end=DOMTest.STATE_ECHO)
    def run(self, fd):
        numPackets    = 10
        maxPacketSize = 4092
        timeout       = 30*1000 # Generous 30-second timeout
        self.result   = "PASS"
        for p in xrange(0, numPackets):
            ok, txt = self.dor.echoRandomPacket2(maxPacketSize, timeout)
            if not ok:
                self.result = "FAIL"
                self.debugMsgs.append("echo of %dth packet failed" % p)
                self.debugMsgs.append(txt)
                return

class EchoCommResetTest(DOMTest):
    "Perform echo tests when DOM is in echo mode"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ECHO, end=DOMTest.STATE_ECHO)
    def run(self, fd):
        numPackets    = 10
        maxPacketSize = 4092
        timeout       = 30*1000 # Generous 30-second timeout
        self.result   = "PASS"
        
        for p in xrange(0, numPackets-1):
            ok, txt = self.dor.echoRandomPacket2(maxPacketSize, timeout)
            if not ok:
                self.result = "FAIL"
                self.debugMsgs.append("echo of %dth packet failed" % p)
                self.debugMsgs.append(txt)
                return
            else:
                # Do a comms reset between each:
                self.dor.commReset()

        # Do the last (n-1th) echo test
        ok, txt = self.dor.echoRandomPacket2(maxPacketSize, timeout)
        if not ok:
            self.result = "FAIL"
            self.debugMsgs.append("echo of %dth packet failed" % p)
            self.debugMsgs.append(txt)
            
############################## DOMAPP TEST BASE CLASSES ############################
            
class QuickDOMAppTest(DOMTest):
    "Short tests specific to domapp - no run length specified"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)
    
class DOMAppTest(DOMTest):
    "Variable duration tests specific to domapp - run length is specified"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP, runLength=10)
        
    def SNClockOk(self, clock, prevClock, bins, prevBins):
        DT = 65536
        if clock != prevClock + prevBins*DT: return False
        return True

    def checkSNdata(self, sndata, prevClock, prevBins):
        """
        Check sndata for correct time structure with respect to previous clock and # of bins
        read out previously; return updated clock, #bins values
        """
        if sndata      == None: return (prevClock, prevBins)
        if len(sndata) == 0:    return (prevClock, prevBins)
        if len(sndata) < 10:
            raise Exception("SN DATA CHECK: %d bytes" % len(sndata))
        bytes, fmtid, t5, t4, t3, t2, t1, t0 = unpack('>hh6B', sndata[0:10])
        clock  = ((((t5 << 8L | t4) << 8L | t3) << 8L | t2) << 8L | t1) << 8L | t0
        scalers = unpack('%dB' % (len(sndata) - 10), sndata[10:])
        bins    = len(scalers)
        if prevBins and not self.SNClockOk(clock, prevClock, bins, prevBins):
            raise Exception("CLOCK CHECK: %d %d %d->%d %x->%x" % (bytes, fmtid, prevBins,
                                                                  bins, prevClock, clock))
        return (clock, bins)

class DOMAppHVTest(DOMAppTest):
    "Subclass of DOMTest with an HV-setting method"
    def setHV(self, domapp, hv):
        HV_TOLERANCE = 20   # HV must be correct to 10 Volts (20 units)
        domapp.enableHV()
        domapp.setHV(hv*2)
        time.sleep(2)
        hvadc, hvdac = domapp.queryHV()
        self.debugMsgs.append("HV: read %d V (ADC) %d V (DAC)" % (hvadc/2,hvdac/2))
        if abs(hvadc-hv*2) > HV_TOLERANCE:
            raise Exception("HV deviates too much from set value!")
        
    def turnOffHV(self, domapp):
        domapp.setHV(0)
        domapp.disableHV()

####################### HELPER METHODS (move into domapp base classes?) ####################

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
        if moniType == 0xCB: # ASCII message
            yield monidata[10:moniLen]
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
    ret = []
    try:
        while True:
            monidata = domapp.getMonitorData()
            if len(monidata) == 0: break
            for msg in unpackMoni(monidata):
                ret.append(msg)
    except Exception, e:
        ret.append("GET MONI DATA FAILED: %s" % exc_string())
    return ret

################################### SPECIFIC TESTS ###############################

class GetDomappRelease(QuickDOMAppTest):
    "Make sure I can ask domapp for its release string"
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.summary = domapp.getDomappVersion()
            self.result = "PASS"
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())

class DOMIDTest(QuickDOMAppTest):
    "Make sure I can get DOM ID from domapp"
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.summary = domapp.getMainboardID()
            self.result = "PASS"
        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())


class SetFastMoniIvalTest(DOMAppTest):
    "Set fast monitoring interval and make sure rate of generated records is roughly correct"
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        self.result = "PASS"
        domapp.resetMonitorBuffer()
        setDefaultDACs(domapp)
        fastInterval        = 2 # Number of seconds delay between records
        tolerance           = 2 # Want to be within this many records of expected
        fastMoniRecordCount = 0
        domapp.setMonitoringIntervals(fastInt=fastInterval)
        expectedRecordCount = self.runLength/fastInterval
        t = MiniTimer(self.runLength*1000)
        while not t.expired():
            # Moni data
            mlist = getLastMoniMsgs(domapp)
            for m in mlist:
                s = re.search(r'^F (\d+) (\d+) (\d+) (\d+)$', m)
                if(s): fastMoniRecordCount += 1
                self.debugMsgs.append(m)
        if(abs(expectedRecordCount-fastMoniRecordCount) > tolerance):
            self.debugMsgs.append("Fast moni record rate mismatch: wanted %d, got %d (tolerance %d)"
                                  % (expectedRecordCount, fastMoniRecordCount, tolerance))
            self.result = "FAIL"
        
    
class SNDeltaSPEHitTest(DOMAppHVTest):
    "Collect both SPE and SN data, make sure there are no gaps in SN data"
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)        
        self.result = "PASS"
        NOMINAL_HV_VOLTS = 900 # Is this the best value?
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.selectMUX(255)
            domapp.setMonitoringIntervals()
            self.setHV(domapp, NOMINAL_HV_VOLTS)
            domapp.setPulser(mode=BEACON, rate=4)
            domapp.enableSN(6400, 0)
            domapp.setMonitoringIntervals()
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)            
            domapp.startRun()

            t = MiniTimer(self.runLength*1000)
            snTimer = MiniTimer(1000) # Collect SN data at 1 sec intervals
            nbDelta = 0
            prevBins, prevClock = None, None
            
            while not t.expired():

                # Moni data
                self.appendMoni(domapp)

                # Hit (delta compressed) data
                try:
                    hitdata = domapp.getWaveformData()
                    if len(hitdata) > 0:
                        nbDelta += len(hitdata)
                        hitBuf = DeltaHitBuf(hitdata) # Does basic integrity check
                except Exception, e:
                    self.result = "FAIL"
                    self.debugMsgs.append("GET WAVEFORM DATA FAILED: %s" % exc_string())
                    self.appendMoni(domapp)
                    break

                # SN data
                
                if snTimer.expired():
                    try:
                        sndata = domapp.getSupernovaData()
                        self.debugMsgs.append("Got %d sn bytes" % len(sndata))
                        self.debugMsgs.append("Delta hits: %d bytes total" % nbDelta)
                    except Exception, e:
                        self.result = "FAIL"
                        self.debugMsgs.append("GET SN DATA FAILED: %s" % exc_string())
                        self.appendMoni(domapp)
                        break

                    try:
                        prevClock, prevBins = self.checkSNdata(sndata, prevClock, prevBins)
                    except Exception, e:
                        self.result = "FAIL"
                        self.debugMsgs.append("SN data check failed: '%s'" % e)
                        self.appendMoni(domapp)
                        break
                    
                    # Reset timer for next time
                    snTimer = MiniTimer(1000)

            domapp.endRun()
            self.turnOffHV(domapp)

        except Exception, e:
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())
            try:
                self.turnOffHV(domapp)
                domapp.endRun()
            except:
                pass
            self.appendMoni(domapp)
            return

class PedestalStabilityTest(DOMAppHVTest):
    "Measure pedestal stability by taking an average over several tries"
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)        
        self.result = "PASS"
        NOMINAL_HV_VOLTS   = 800 # Is this the best value?
        ATWD_PEDS_PER_LOOP = 100 
        FADC_PEDS_PER_LOOP = 200 
        MAX_ALLOWED_RMS    = 1.0
        numloops           = 100
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.selectMUX(255)
            domapp.setMonitoringIntervals()

            ### Turn on HV
            self.setHV(domapp, NOMINAL_HV_VOLTS)
            
            ### Collect pedestals N times

            atwdSum   = [[[0. for samp in xrange(128)] for ch in xrange(4)] for ab in xrange(2)]
            atwdSumSq = [[[0. for samp in xrange(128)] for ch in xrange(4)] for ab in xrange(2)]
            # Wheeeee!
            fadcSum   = [0. for samp in xrange(256)]
            fadcSumSq = [0. for samp in xrange(256)]

            numloops = 0
            t = MiniTimer(self.runLength*1000)
            while not t.expired():
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
                numloops += 1

            if numloops < 1: raise Exception("No successful pedestal collections occurred!")
            
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
            self.turnOffHV(domapp)
            
            if maxrms > MAX_ALLOWED_RMS:
                raise Exception("Maximum allowed RMS (%2.3f) exceeeded (%2.3f)!" %\
                                (MAX_ALLOWED_RMS, maxrms))

        except Exception, e:
            try:
                self.turnOffHV(domapp)
            except:
                pass
            self.result = "FAIL"
            self.debugMsgs.append(exc_string())
            self.appendMoni(domapp)
            return

class DeltaCompressionBeaconTest(DOMAppTest):
    "Make sure delta-compressed beacons have all four ATWD channels read out"
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
            self.appendMoni(domapp)
            return

        # collect data
        t = MiniTimer(self.runLength * 1000)
        while not t.expired():
            self.appendMoni(domapp)

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
                self.appendMoni(domapp)
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
            self.appendMoni(domapp)
            
class SNTest(DOMAppTest):
    "Make sure no gaps are present in SN data"    
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
            self.appendMoni(domapp)
            return
            
        prevBins, prevClock = None, None

        for i in xrange(0,self.runLength):

            self.appendMoni(domapp)
            
            # Fetch supernova

            try:
                sndata = domapp.getSupernovaData()
            except Exception, e:
                self.result = "FAIL"
                self.debugMsgs.append("GET SN DATA FAILED: %s" % exc_string())
                self.appendMoni(domapp)
                break

            try:
                prevClock, prevBins = self.checkSNdata(sndata, prevClock, prevBins)
            except Exception, e:
                self.result = "FAIL"
                self.debugMsgs.append("SN data check failed: '%s'" % e)
                self.appendMoni(domapp)
                break

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
            self.appendMoni(domapp)

class TestNotFoundException(Exception): pass

class TestingSet:
    "Class for running multiple tests on a group of DOMs in parallel"
    def __init__(self, domDict, doOnly=False, stopOnFail=False):
        self.domDict      = domDict
        self.testList     = []
        self.durationDict = {}
        self.ntrialsDict  = {}
        self.dontSkipDict = {}     # Keep track of whether to really do this test
        self.doOnly       = doOnly # If true, use dontSkipDict to select tests; else do all tests
        self.threads      = {}
        self.numpassed    = 0
        self.numfailed    = 0
        self.numtests     = 0
        self.counterLock  = threading.Lock()
        self.stopOnFail   = stopOnFail

    def add(self, test):
        self.testList.append(test)
        self.ntrialsDict[test.__name__] = 1
        self.durationDict[test] = None

    def setDuration(self, testName, duration):
        found = False
        for t in self.testList:
            if t.__name__ == testName:
                self.durationDict[t] = duration
                found = True
        if not found: raise TestNotFoundException("test name %s not defined" % testName)

    def setCount(self, testName, count):
        found = False
        for t in self.testList:
            if t.__name__ == testName:
                self.ntrialsDict[testName]  = count
                self.dontSkipDict[testName] = True
                found = True
        if not found: raise TestNotFoundException("test name %s not defined" % testName)

    def cycle(self, testList, startState, doOnly, c, w, d):
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
                if not doneDict.has_key(test): doneDict[test] = 0
                # Use "test" if 
                # (1) test count hasn't surpassed specified count, and
                # (2) state doesn't change, and
                # (3) either we're doing all standard tests, or this test has been
                #     specified explicitly on the command line
                # otherwise use next state change
                if (doneDict[test] < self.ntrialsDict[test.__class__.__name__]) \
                       and test.startState == state:
                    nextTest = test
                    if test.endState == state and (not doOnly or self.dontSkipDict.has_key(test.__class__.__name__)):
                        allDone = False
                        allDoneThisState = False
                        break
                    else:
                        allDone = False
                        nextStateChangeTest = test
            if allDone: return
            elif allDoneThisState:
                nextTest = nextStateChangeTest
            state = nextTest.endState
            doneDict[nextTest] += 1
            yield nextTest

    def doAllTests(self, domid, c, w, d):
        startState = DOMTest.STATE_ICEBOOT
        testObjList = []
        dor = MiniDor(c, w, d)
        dor.open()
        for testName in self.testList:
            t = testName(c,w,d,dor)
            # Set duration which may have been set explicitly by user:
            if self.durationDict[testName]:
                t.setRunLength(self.durationDict[testName])
            testObjList.append(t)
            # FIXME - check to make sure tests for which ntrialsDict > 1 preserve state
            if self.ntrialsDict[t.__class__.__name__] > 1 and t.changesState():
                raise RepeatedTestChangesStateException("Test %s changes DOM state, "
                                                        % t.__class__.__name__ + "cannot be repeated.")
        for test in self.cycle(testObjList, startState, self.doOnly, c, w, d):
            test.run(dor.fd)
            if(test.startState != test.endState): # If state change, flush buffers etc. to get clean IO
                dor.close()
                dor.open()

            sf = False
            #### LOCK - have to protect shared counters, as well as TTY...
            self.counterLock.acquire()
            runLenStr = ""
            if test.runLength: runLenStr = "%d sec " % test.runLength
            print "%s%s%s %s->%s %s%s: %s %s" % (c,w,d, test.startState,
                                                      test.endState, runLenStr,
                                                      test.name(), test.result, test.summary)
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
            test.clearDebugTxt()
            self.counterLock.release()
            #### UNLOCK
            if sf: return # Quit upon first failure
            
    def runThread(self, domid):
        c, w, d = self.domDict[domid]
        try:
            self.doAllTests(domid, c,w,d)
        except KeyboardInterrupt, k:
            return
        except Exception, e:
            print "Test sequence aborted: %s" % exc_string()        
        
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

def getDomappToolsPythonVersion():
    f = open("/usr/local/share/domapp-tools-python-version")
    return sub(r'\n','', f.readline())

def main():
    p = optparse.OptionParser()
    p.add_option("-s", "--stop-fail",
                 action="store_true",
                 dest="stopFail",     help="Stop at first failure for each DOM")

    p.add_option("-V", "--hv-tests",
                 action="store_true",
                 dest="doHVTests",    help="Perform HV tests")

    p.add_option("-l", "--list-tests",
                 action="store_true",
                 dest="listTests",    help="List tests to be performed")

    p.add_option("-d", "--set-duration",
                 action="append",     type="string",    nargs=2,
                 dest="setDuration",  help="Set duration in secs of a test, " + \
                                           "e.g. '-d SNTest 1000' (repeatable)")

    p.add_option("-o", "--only-test",
                 action="store_true",
                 dest="doOnly",       help="Do same-state tests only when specified by -n option")
    
    p.add_option("-n", "--repeat-count",
                 action="append",     type="string",    nargs=2,
                 dest="repeatCount",  help="Set # of times to run a test, "   + \
                                            "e.g. '-n SNTest 5' (repeatable) " + \
                                            "(non-state-changing tests only!)")
    p.set_defaults(stopFail         = False,
                   doHVTests        = False,
                   setDuration      = None,
                   repeatCount      = None,
                   doOnly           = False,
                   listTests        = False)
    opt, args = p.parse_args()

    startState = DOMTest.STATE_ICEBOOT # FIXME: what if it's not?
    
    ListOfTests = [IcebootToConfigboot, CheckConfigboot, ConfigbootToIceboot,
                   CheckIceboot, SoftbootCycle, IcebootToDomapp, 
                   GetDomappRelease, DOMIDTest, DeltaCompressionBeaconTest,
                   SNTest, SetFastMoniIvalTest,
                   DomappToIceboot, IcebootToEcho, EchoTest, EchoCommResetTest, EchoToIceboot]

    if opt.doHVTests:
        ListOfTests.append(PedestalStabilityTest)
        ListOfTests.append(SNDeltaSPEHitTest)

    try:
        dor = Driver()
        dor.enable_blocking(0)
        domDict = dor.get_active_doms()
    except Exception, e:
        print "No driver present? ('%s')" % e
        raise SystemExit
    
    testSet = TestingSet(domDict, opt.doOnly, opt.stopFail)

    for t in ListOfTests:
        testSet.add(t)

    if opt.setDuration:
        for (testName, dur) in opt.setDuration:
            try:
                testSet.setDuration(testName, int(dur))
            except Exception, e:
                print "Could not set duration for %s to '%s' seconds: %s" % (testName, dur, e)
                raise SystemExit

    if opt.repeatCount:
        for (testName, count) in opt.repeatCount:
            try:
                testSet.setCount(testName, int(count))
            except Exception, e:
                print "Could not set repeat count for %s to '%s': %s" % (testName, count, e)
                raise SystemExit
            
    if opt.listTests:
        for t in ListOfTests:
            print t.__name__
            if t.__doc__:
                print '\t', t.__doc__
        raise SystemExit
    
    revTxt = "UNKNOWN/head"
    try:
        revTxt = getDomappToolsPythonVersion() # Can fail if not an official installation
    except:
        pass
    
    print "domapp-tools-python revision: %s" % revTxt
    print "dor-driver release: %s" % dor.release
    
    testSet.go()
    print testSet.summary()
    
    raise SystemExit

if __name__ == "__main__": main()
