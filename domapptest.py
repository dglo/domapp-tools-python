#!/usr/bin/env python

# domapptest.py
# John Jacobsen, NPX Designs, Inc., john@mail.npxdesigns.com
# Started: Wed May  9 21:57:21 2007
from __future__ import generators
import time, threading, os, sys
from datetime import datetime

from re import search, sub
from pprint import PrettyPrinter

from domapptools.dor import *
from domapptools.exc_string import exc_string
from domapptools.domapp import *
from domapptools.MiniDor import *
from domapptools.DeltaHit import *
from domapptools.EngHit import *
from domapptools.decode_dom_buffer import decode_dom_buffer

from os.path import exists
from math import sqrt
import os.path
import optparse

class WriteTimeoutException(Exception):
    pass


class RepeatedTestChangesStateException(Exception):
    pass


class UnsupportedTestException(Exception):
    pass


class TestNotHVTestException(Exception):
    pass


class TestNotFoundException(Exception):
    pass


class DOMTest(object):
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
        self.uploadFileName  = None
        self.syncWithPartner = False
        self.startEvent      = None
        self.finishEvent     = None
        self.reset()

    def reset(self):
        self.debugMsgs  = []
        self.result     = "PASS"
        self.summary    = ""

    def appendMoni(self, domapp):
        m = getLastMoniMsgs(domapp)
        if m != []:
            self.debugMsgs.append(m)
        
    def changesState(self):
        return self.startState != self.endState

    def requiresSync(self):
        return self.syncWithPartner

    def setStartEvent(self, e):
        self.startEvent = e

    def setFinishEvent(self, e):
        self.finishEvent = e        

    def setUploadFileName(self, f):
        self.uploadFileName = f
    
    def setRunLength(self, l):
        self.runLength = l

    def getDebugTxt(self):
        str = ""
        if self.debugMsgs:
            for m in self.debugMsgs:
                if type(m) == type([]):
                    for i in m:
                        if i != "": str += "%s\n" % i
                elif m != "":
                    str += "%s\n" % m
        return str

    def clearDebugTxt(self): self.debugMsgs = []
    
    def run(self, fd):
        pass

    def fail(self, str):
        self.debugMsgs.append(str)
        if self.result != "FAIL":
            self.result = "FAIL"
            self.summary = str


class ConfigbootToIceboot(DOMTest):
    """
    Make sure transition from configboot to iceboot succeeds
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_CONFIGBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        ok, txt = self.dor.configbootToIceboot2()
        if not ok:
            self.fail("Could not transition into iceboot")
            self.debugMsgs.append(txt)
        else:
            ok, txt = self.dor.isInIceboot2()
            if not ok:
                self.fail("check for iceboot prompt failed")
                self.debugMsgs.append(txt)


class DomappToIceboot(DOMTest):
    """
    Make sure (softboot) transition from domapp to iceboot succeeds
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        self.dor.softboot()
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.fail("check for iceboot prompt failed")
            self.debugMsgs.append(txt)


class EchoToIceboot(DOMTest):
    """
    Make sure (softboot) transition from echo-mode to iceboot succeeds
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ECHO, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        self.dor.softboot()
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.fail("check for iceboot prompt failed")
            self.debugMsgs.append(txt)
    

class IcebootToDomapp(DOMTest):
    """
    Make sure transition from iceboot to domapp succeeds
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_DOMAPP)
    def run(self, fd):
        if self.uploadFileName: 
            ok, txt = self.dor.uploadDomapp2(self.uploadFileName)
        else:
            ok, txt = self.dor.icebootToDomapp2()
        if not ok:        
            self.fail("could not transition into domapp")
            self.debugMsgs.append(txt)
        else:
            # FIXME - test w/ domapp message here
            pass


iceboot_versions = {}


class IcebootSelfReset(DOMTest):
    """
    Try 'reset' command inside Iceboot to get 'Iceboot (...) build...'
    information, like 'versions' command does.
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ICEBOOT)

    def run(self, fd):
        try:
            cs0 = CommStats(self.dor.commStats())
            txt, version = self.dor.icebootReset()
        except ExpectStringNotFoundException, e:
            discard = self.dor.fpgaRegs()
            cs1 = CommStats(self.dor.commStats())
            self.fail('Did not get expected data back from Iceboot!')
            self.debugMsgs.append(str(e))
            self.debugMsgs.append(exc_string())
            pp = PrettyPrinter(indent=4)
            self.debugMsgs.append('\nDifference in commstats:\n%s\n' % pp.pformat(cs1-cs0))
            try:
                txt = self.dor.iceboot_get_buffer_dump()
                buffer = decode_dom_buffer(txt)
                self.debugMsgs.append('\nDOM transmit buffer:\n%s\n' % buffer)
            except Exception, e:
                self.debugMsgs.append(str(e))
            return
        cwd = "%s%s%s" % (self.card, self.wire, self.dom)
        global iceboot_versions
        if cwd not in iceboot_versions:
            iceboot_versions[cwd] = version
        else:
            if iceboot_versions[cwd] != version:
                self.fail('Version from Iceboot not correct!')
                self.debugMsgs.append("Expected '%s', got '%s'" % \
                                      (iceboot_versions[cwd], version))
        self.summary = version
        
    
class CheckIceboot(DOMTest):
    """
    Make sure I'm in iceboot when I think I should be
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ICEBOOT)
    def run(self, fd):
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.fail("check for iceboot prompt failed")
            self.debugMsgs.append(txt)


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
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.fail("first check for iceboot prompt failed")
            self.debugMsgs.append(txt)
            return

        # Transition to domapp
        ok, txt = self.dor.icebootToDomapp2()
        if not ok:
            self.fail("could not transition into domapp")
            self.debugMsgs.append(txt)
            return

        # Check domapp by fetching release
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            domapp.getDomappVersion()
        except Exception, e:
            self.fail(exc_string())
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
            self.fail("second check for iceboot prompt failed")
            self.debugMsgs.append(txt)
            return


class ATWDDeadtimeTest(DOMTest):
    """
    Test ATWD deadtime in the case where SLC is selected.  See
    https://bugs.icecube.wisc.edu/view.php?id=4925.  This test is in
    Forth/Iceboot because it's a simple adaptation of Thorsten's test
    (see Mantis issue notes).
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ICEBOOT)

    def run(self, fd):
        self.dor.writeTimeout(fd,r"""\
             s" domapp.sbi.gz" find if gunzip fpga endif
             \ --Set frontend pulser and discriminator
             9 1000 writeDAC
             11 1000 writeDAC
             \ -- enable rate meter to test discriminator and ATWD dead time
             $301 $90000480 !
             \ -- enable calibration pulser at ~610Hz
             $0a001002 $90000460 !
             \ -- check we [have] discriminator counts
             $90000484 @ . drop
             \ -- enable DAQ(one ATWD! [else you get ping-pong]; LC enabled)
             $00010003 $90000410 !
             \ -- enable trigger
             $1 $90000400 !
             \ -- check LBM pointer
             $90000424 @ . drop
             \ DONE
             """.replace('\n','\r\n'))
        txt1 = self.dor.readExpect(fd, 'DONE.+?>')
        
        time.sleep(4) # wait a bit [>3 seconds] and read ATWD dead
                      # time (should be ~107500; ~ 4point4 us per aborted launch)

        self.dor.writeTimeout(fd,"$90000490 @ . drop\r\n")
        txt2 = self.dor.readExpect(fd, '\d+\s*>')
        match = search("(\d+)\s*>", txt2)
        assert match
        deadtime = int(match.group(1))
        MAX_DEADTIME = 120000
        if deadtime >= MAX_DEADTIME:
            self.fail("ATWD deadtime too high (got %d, wanted < %d)" %\
                      (deadtime, MAX_DEADTIME))
            self.debugMsgs.append(txt1+txt2)
        self.dor.softboot()
        ok, txt = self.dor.isInIceboot2()
        if not ok:
            self.fail("Softboot transition after test failed!")
            self.debugMsgs.append(txt)
                        
    
class IcebootToConfigboot(DOMTest):
    """
    Make sure transition from iceboot to configboot succeeds
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_CONFIGBOOT)
    def run(self, fd):
        ok, txt = self.dor.icebootToConfigboot2()
        if not ok:
            self.fail("could not transition into configboot")
            self.debugMsgs.append(txt)
        else:
            ok, txt =  self.dor.isInConfigboot2()
            if not ok:
                self.fail("check for iceboot prompt failed")
                self.debugMsgs.append(txt)


class CheckConfigboot(DOMTest):
    """
    Check that I'm really in configboot when I think I am
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_CONFIGBOOT, end=DOMTest.STATE_CONFIGBOOT)
    def run(self, fd):
        ok, txt = self.dor.isInConfigboot2()
        if not ok:
            self.fail("check for iceboot prompt failed")
            self.debugMsgs.append(txt)


class IcebootToEcho(DOMTest):
    """
    Make sure transition from iceboot to echo-mode succeeds
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ICEBOOT, end=DOMTest.STATE_ECHO)
    def run(self, fd):
        ok, txt = self.dor.icebootToEcho2()
        if not ok:
            self.fail("could not transition into echo-mode")
            self.debugMsgs.append(txt)

class EchoTest(DOMTest):
    """
    Perform echo test of 100 variable-length random packets, when DOM is in echo mode
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ECHO, end=DOMTest.STATE_ECHO)
    def run(self, fd):
        numPackets    = 10
        maxPacketSize = 4092
        timeout       = 30*1000 # Generous 30-second timeout
        for p in xrange(0, numPackets):
            ok, txt = self.dor.echoRandomPacket2(maxPacketSize, timeout)
            if not ok:
                self.fail("echo of %dth packet failed" % p)
                self.debugMsgs.append(txt)
                return

class EchoCommResetTest(DOMTest):
    """
    Perform echo tests when DOM is in echo mode, doing a comm reset between each
    """
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_ECHO, end=DOMTest.STATE_ECHO)
    def run(self, fd):
        numPackets    = 10
        maxPacketSize = 4092
        timeout       = 30*1000 # Generous 30-second timeout
        
        for p in xrange(0, numPackets-1):
            ok, txt = self.dor.echoRandomPacket2(maxPacketSize, timeout)
            if not ok:
                self.fail("echo of %dth packet failed" % p)
                self.debugMsgs.append(txt)
                return
            else:
                # Do a comms reset between each:
                self.dor.commReset()

        # Do the last (n-1th) echo test
        ok, txt = self.dor.echoRandomPacket2(maxPacketSize, timeout)
        if not ok:
            self.fail("echo of %dth packet failed" % p)
            self.debugMsgs.append(txt)
            
############################## DOMAPP TEST BASE CLASSES ############################
            
class SimpleDomAppTest(DOMTest):
    "Short tests specific to domapp - no run length specified"
    def __init__(self, card, wire, dom, dor):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP)
    
class DOMAppTest(DOMTest):
    "Variable duration tests specific to domapp - run length is specified"
    def __init__(self, card, wire, dom, dor, runLength=10):
        DOMTest.__init__(self, card, wire, dom, dor,
                         start=DOMTest.STATE_DOMAPP, end=DOMTest.STATE_DOMAPP,
                         runLength=runLength)
        
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

    def _setHV(self, domapp, hv):
        """
        Only DOMAppHVTests can turn on HV, but all tests can turn it off
        """
        if not isinstance(self, DOMAppHVTest) and hv > 0:
            raise TestNotHVTestException("Test %s cannot set voltage other than 0" % \
                                         self.__class__.__name__)
        HV_TOLERANCE = 20   # HV must be correct to 10 Volts (20 units)
        HV_TIMEOUT   = 30
        domapp.enableHV()
        domapp.setHV(hv*2)
        t = MiniTimer(HV_TIMEOUT * 1000)
        while not t.expired():
            time.sleep(1)
            hvadc, hvdac = domapp.queryHV()
            self.debugMsgs.append("HV: read %d V (ADC) %d V (DAC)" % (hvadc/2,hvdac/2))
            if abs(hvadc-hv*2) <= HV_TOLERANCE: return
        raise Exception("HV deviates too much from set value (got %s, wanted %s)!" % (hvadc, hv*2))
    
    def turnOffHV(self, domapp):
        """
        Every test must be able to turn off HV, but only DOMAppHVTests can turn it on
        """
        self._setHV(domapp, 0)
        domapp.disableHV()

class DOMAppHVTest(DOMAppTest):
    "Subclass of DOMTest with an HV-setting method"
    nominalHVVolts = 900 # Is this the best value?
    def setHV(self, domapp, hv):
        """
        Only DOMAppHVTests can turn on HV, but all tests can turn it off
        """
        self._setHV(domapp, hv)
        
class ChargeStampHistoTest(DOMAppHVTest):
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            doATWD = False
            if self.__class__.__name__ == "ATWDHistoTest": doATWD = True
            elif self.__class__.__name__ != "FADCHistoTest":
                raise UnsupportedTestException("%s not known!" % \
                                               self.__class__.__name__)

            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.selectMUX(255)
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)
            self.setHV(domapp, DOMAppHVTest.nominalHVVolts)
            domapp.writeDAC(DAC_SINGLE_SPE_THRESH, 550)
            domapp.setTriggerMode(2)
            domapp.setLC(mode=0)
            domapp.setPulser(mode=BEACON, rate=4)

            domapp.collectPedestals(100, 100, 200)

            if doATWD:
                domapp.configureChargeStamp("atwd", channelSel=None) # Select 'AUTO' mode
                domapp.setChargeStampHistograms(2, 1000)
            else:
                domapp.configureChargeStamp("fadc")
                domapp.setChargeStampHistograms(2, 10)

            domapp.startRun()

            domapp.setMonitoringIntervals(hwInt=1, fastInt=1)

            # Require records present, and nonzero values in the records, for
            # FADC or, if ATWD, for at least one channel per chip.
            gotATWDRec = {}
            gotFADCRec = False
            gotATWDCounts = {}
            gotFADCCounts = False
            t = MiniTimer(self.runLength*1000)
            while not t.expired():
                hitdata = domapp.getWaveformData()
                if len(hitdata) > 0:
                    hitBuf = DeltaHitBuf(hitdata) # Does basic integrity check

                mlist = getLastMoniMsgs(domapp)
                for m in mlist:
                    if doATWD:
                        s1 = search('ATWD CS (\S+) (\d+)--(\d+) entries: (.+)', m)
                        if s1:
                            chip    = s1.group(1)
                            chan    = int(s1.group(2))
                            entries = s1.group(3)
                            rest    = s1.group(4)
                            gotATWDRec[chip, chan] = True
                            for x in map(int, rest.split()):
                                if x > 0: gotATWDCounts[chip] = True
                    else:
                        s1 = search('FADC CS--(\d+) entries: (.+)', m)
                        if s1:
                            entries = s1.group(1)
                            rest    = s1.group(2)
                            for x in map(int, rest.split()):
                                if x > 0: gotFADCCounts = True
                            gotFADCRec = True
                    self.debugMsgs.append(m)

            ### End condition: go back to FADC mode
            domapp.configureChargeStamp("fadc")
            domapp.setChargeStampHistograms(0, 1)

            domapp.endRun()
            
            ### Make sure I have records for each type
            if doATWD:
                for chip in ['A','B']:
                    for chan in range(0,2):
                        if not gotATWDRec.has_key((chip, chan)) \
                               or not gotATWDRec[chip, chan]:
                            self.fail("No ATWD charge stamp histograms found for chip %s, chan %d!" \
                                      % (chip, chan))
                            self.appendMoni(domapp)
                    if not gotATWDCounts.has_key(chip):
                        self.fail("No nonzero ATWD charge stamp histogram entries found for chip %s!" % chip)
                        self.appendMoni(domapp)
            else:
                if not gotFADCRec:
                    self.fail("No FADC charge stamp histograms found!")
                    self.appendMoni(domapp)
                if not gotFADCCounts:
                    self.fail("No nonzero FADC charge stamp histogram entries found!")
                    self.appendMoni(domapp)

        except:
            try:
                self.fail(exc_string())
                self.appendMoni(domapp)
                domapp.endRun()
            except:
                pass


class FADCHistoTest(ChargeStampHistoTest):
    """
    Histogram FADC (in-ice) chargestamps.  Require nonzero entries for some
    bins in each histogram.
    """
    pass


class ATWDHistoTest(ChargeStampHistoTest):
    """
    Histogram ATWD (IceTop) chargestamps.  Require nonzero entries for some
    bins in each histogram.
    """
    pass

class GetIntervalTest(DOMAppTest):
    """
    Get Interval Test -> Get one interval of data from the dom
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)

        domapp.setMonitoringIntervals(0, 0, 0)
        domapp.resetMonitorBuffer()
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        setDefaultDACs(domapp)
        setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 1000)
        setDAC(domapp, DAC_SINGLE_SPE_THRESH, 600)
        domapp.setTriggerMode(2)
        domapp.setPulser(mode=BEACON, rate=200)        

        # Test 1: SN disabled
        domapp.disableSN()
        domapp.startRun()
        try:
            domapp.setMonitoringIntervals(hwInt=1, fastInt=1)
                
            try:
                result_dict = domapp.getInterval()
                # test that getinterval returned the expected
                # number of moni and supernova packets
                if (result_dict['moni_count']!=1):
                    self.fail("Expected 1 moni message got %d for c/p/d: %s/%s/%s" % \
                              result_dict['moni_count'],
                              result_dict['card'],
                              result_dict['pair'],
                              result_dict['dom'])

                if (result_dict['sn_count']!=0):
                    self.fail("Expected 0 sn messages got %d for c/p/d: %s/%s/%s" % \
                              result_dict['sn_count'],
                              result_dict['card'],
                              result_dict['pair'],
                              result_dict['dom'])
                return 
            except Exception, e:
                print "fail: ", e
                self.fail(exc_string())
        finally:
            domapp.endRun()

        domapp.setMonitoringIntervals(0, 0, 0)
        domapp.resetMonitorBuffer()
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        setDefaultDACs(domapp)
        setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 1000)
        setDAC(domapp, DAC_SINGLE_SPE_THRESH, 600)
        domapp.setTriggerMode(2)
        domapp.setPulser(mode=BEACON, rate=200)

        # Test 2: SN enabled
        domapp.enableSN(6400, 0)
        domapp.startRun()
        try:
            domapp.setMonitoringIntervals(hwInt=1, fastInt=1)
                
            try:
                result_dict = domapp.getInterval()

                # test that getinterval returned the expected
                # number of moni and supernova packets
                if (result_dict['moni_count']!=1):
                    self.fail("Expected 1 moni message got %d for c/p/d: %s/%s/%s" % \
                              result_dict['moni_count'],
                              result_dict['card'],
                              result_dict['pair'],
                              result_dict['dom'])

                if (result_dict['sn_count']!=1):
                    self.fail("Expected 1 sn message got %d for c/p/d: %s/%s/%s" % \
                              result_dict['sn_count'],
                              result_dict['card'],
                              result_dict['pair'],
                              result_dict['dom'])
                return 
            except Exception, e:
                print "fail: ", e
                self.fail(exc_string())
        finally:
            domapp.endRun()
            

class FlasherTest(DOMAppTest):
    def __init__(self, card, wire, dom, dor, abSelect='A'):
        DOMAppTest.__init__(self, card, wire, dom, dor)
        self.abSelect = abSelect

    def junkDomappHits(self, domapp, msec=1000):
        t = MiniTimer(msec)
        while not t.expired():
            domapp.getWaveformData()
            
    def runLoop(self, domapp):
        t = MiniTimer(self.runLength*1000)
        gotData = False
        nhits = 0
        hitOk = True
        while hitOk and not t.expired():
            try:
                hitdata = domapp.getWaveformData()
            except Exception, e:
                self.fail(exc_string())
                self.appendMoni(domapp)
                break
            
            if len(hitdata) > 0:
                gotData = True
                hitBuf = EngHitBuf(hitdata)
                for hit in hitBuf.next():
                    nhits += 1
                    if hit.trigSource != 3:
                        self.fail("Bad trigger type (%d) in flasher hit!"
                                  % hit.trigSource)
                        self.appendMoni(domapp)
                        self.debugMsgs.append(hit)
                        hitOk = False
                        break
                    if not hit.fbRunInProgress:
                        self.fail("Hit indicates flasher run is not in progress!!!")
                        self.appendMoni(domapp)
                        self.debugMsgs.append(hit)
                        hitOk = False
                        break
                    if len(hit.atwd[3]) != 128:
                        self.fail("Insufficient channels (%d) in ATWD3"
                                  % len(hit.atwd[3]))
                        self.appendMoni(domapp)
                        self.debugMsgs.append(hit)
                        hitOk = False
                        break
                    min    = None
                    max    = None
                    top    = 750
                    bot    = 500
                    minTOT = 5
                    start  = None
                    end    = None
                    for i in range(0, len(hit.atwd[3])):
                        s = hit.atwd[3][i]
                        if start is None:
                            if s < bot: start = i
                        else:
                            if s > top: end = i
                        if min is None or s < min: min = s
                        if max is None or s > max: max = s
                    badLEDpulse = True
                    if start is None:
                        self.fail("Pulse never went below %d" % bot)
                    elif end is None:
                        self.fail("Pulse never returned above %d" % top)
                    elif end-start < minTOT:
                        self.fail("Start and end range of pulse (%d, %d) < %d" % (start, end, minTOT))
                    else:
                        badLEDpulse = False
                    if badLEDpulse:
                        self.appendMoni(domapp)
                        self.debugMsgs.append(hit)
                        hitOk = False
                        break
        return gotData, nhits
        
    def run(self, fd):
        if self.dom != self.abSelect: return # Automatically pass
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.turnOffHV(domapp)
            time.sleep(2) # Wait for HV to 'cool down'
            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            setDAC(domapp, DAC_FLASHER_REF, 450)
            domapp.collectPedestals(100, 100, 200)
            domapp.setTriggerMode(3)
            domapp.setEngFormat(0, 4*(2,), (128, 0, 0, 128))
            domapp.setCompressionMode(0)
            domapp.setDataFormat(0)
            domapp.selectMUX(3)
            rate = 100
            domapp.startFBRun(127, 50, 0, 1, rate)
            domapp.setMonitoringIntervals(hwInt=5, fastInt=1)

            try:
                for i in range(4):
                    gotData, nhits = self.runLoop(domapp)
                    if not gotData: self.fail("Did not get any hit data from DOM!")
                    if nhits < 1:
                        self.fail("Didn't get any hits!")
                    rate /= 2
                    domapp.changeFBParams(127, 50, 0, 1, rate)
                    self.junkDomappHits(domapp, msec=1000)
            finally:
                domapp.endRun()
        except Exception, e:
            self.fail(exc_string())
            self.appendMoni(domapp)

class FlasherATest(FlasherTest):
    """
    Test flashers on A DOMs
    """
    def __init__(self, card, wire, dom, dor):
        FlasherTest.__init__(self, card, wire, dom, dor, 'A')

class FlasherBTest(FlasherTest):
    """
    Test flashers on B DOMs
    """
    def __init__(self, card, wire, dom, dor):
        FlasherTest.__init__(self, card, wire, dom, dor, 'B')


####################### HELPER METHODS (move into domapp base classes?) ####################


def setDAC(domapp, dac, val):
    domapp.writeDAC(dac, val)


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
        if moniType == 0xC8:
            vals = unpack('>bx27HLL', monidata[10:74])
            vals = [str(i) for i in vals]
            txt = " ".join(vals)
            yield "[HW EVT %s]" % txt
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
    Drain buffered monitoring messages - return list of string representations
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


class GetDomappRelease(SimpleDomAppTest):
    """
    Ask domapp for its release string
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.summary = domapp.getDomappVersion()
        except Exception, e:
            self.fail(exc_string())


class LBMBufferSizeTest(SimpleDomAppTest):
    """
    Make sure LBM buffer size message works
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            depth = domapp.get_lbm_buffer_depth()
            assert(depth==1<<24)
            domapp.set_lbm_buffer_depth(21)
            depth = domapp.get_lbm_buffer_depth()
            assert(depth==1<<21)
            domapp.set_lbm_buffer_depth(24)
            depth = domapp.get_lbm_buffer_depth()
            assert(depth==1<<24)
        except Exception, e:
            self.fail(exc_string())

            
class DomappUnitTests(SimpleDomAppTest):
    """
    Run on-board unit tests
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            domapp.unitTests()
        except Exception, e:
            self.appendMoni(domapp)
            self.fail(exc_string())
            
    
class DOMIDTest(SimpleDomAppTest):
    """
    Get DOM ID from domapp
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.summary = domapp.getMainboardID()
        except Exception, e:
            self.fail(exc_string())


class IdleCounterTest(DOMAppTest):
    """
    Test idle counters in monitoring stream
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.selectMUX(255)
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)
            domapp.setTriggerMode(2)
            domapp.setPulser(mode=FE_PULSER, rate=200)
            domapp.setLC(mode=0)
            domapp.startRun()
            domapp.setMonitoringIntervals(hwInt=1, fastInt=1)
            t = MiniTimer(self.runLength*1000)
            while not t.expired():
                # Get (and toss) hit data
                hitdata = domapp.getWaveformData()
                self.appendMoni(domapp)
            domapp.endRun()
            try:
                (msgs, loops) = domapp.getMessageStats()
                if loops == 0:
                    self.fail("msgs=%d, loops=%d: bad values!" % (msgs, loops))
                    self.appendMoni(domapp)
                else:
                    self.summary = "%d messages, %d loops: %2.4f%% idle" % \
                                   (msgs, loops, 100.0-100.*(float(msgs)/float(loops)))
            except MalformedMessageStatsException, e:
                self.fail("Bad return value trying to get message stats - old domapp?")
                self.appendMoni(domapp)

        except Exception, e:
            self.fail(exc_string())
            self.appendMoni(domapp)            
            try: domapp.endRun()
            except: pass
        

class ScalerDeadtimePulserTest(DOMAppTest):
    """
    Set fast moni interval, enable pulser and look for nonzero
    scaler deadtime values
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        numZeroRecs = 0
        try:
            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 1000)
            setDAC(domapp, DAC_SINGLE_SPE_THRESH, 600)
            domapp.setTriggerMode(2)
            domapp.setPulser(mode=FE_PULSER, rate=100)
            domapp.setCompressionMode(0)            
            domapp.startRun()
            domapp.setMonitoringIntervals(hwInt=5, fastInt=1)
        except Exception, e:
            self.fail(exc_string())
            self.appendMoni(domapp)
            return

        t = MiniTimer(self.runLength*1000)
        while not t.expired():
            mlist = getLastMoniMsgs(domapp)
            for m in mlist:
                s1 = search(r'^F (\d+) (\d+) (\d+) (\d+)$', m)
                if s1:
                    deadtime = int(s1.group(4))
                    if(deadtime <= 0):
                        numZeroRecs += 1
                        if numZeroRecs > 1:
                            self.fail("Too many bad scaler deadtime values! (%d)" % numZeroRecs)
                self.debugMsgs.append(m)
        try:
            domapp.endRun()
        except Exception, e:
            self.fail(exc_string())
            self.appendMoni(domapp)
                                              

class MessageSizePulserTest(DOMAppTest):
    """
    Run pulser at a high rate and make sure you have messages > 3000 bytes
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        maxMsgSize = 0
        try:
            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 1000)
            setDAC(domapp, DAC_SINGLE_SPE_THRESH, 600)
            domapp.setTriggerMode(2)
            domapp.setPulser(mode=FE_PULSER, rate=8000)
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)
            domapp.setLC(mode=0) # Make sure no LC is required
            domapp.startRun()
            domapp.setMonitoringIntervals(hwInt=5, fastInt=1)

            t = MiniTimer(self.runLength*1000)
            while not t.expired():
                self.appendMoni(domapp)
                hitdata = domapp.getWaveformData()
                if len(hitdata) > maxMsgSize:
                    maxMsgSize = len(hitdata)
                    self.debugMsgs.append("Got new max (%d byte) data payload" % maxMsgSize)

            domapp.endRun()
        except Exception, e:
            self.fail(exc_string())
            try:
                domapp.endRun()
            except:
                self.appendMoni(exc_string())
            self.appendMoni(domapp)

        domapp.setPulser(mode=BEACON) # Turn pulser off 

        if maxMsgSize < 3000: self.fail("Maximum message size (%d bytes) too small!"
                                         % maxMsgSize)


class SPEScalerNotZeroTest(DOMAppHVTest):
    """
    Read out scalers and make sure, after the first readout, that
    at least the SPE scaler values are nonzero
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.selectMUX(255)
            self.setHV(domapp, DOMAppHVTest.nominalHVVolts)
            domapp.setPulser(mode=BEACON, rate=4)
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)
            domapp.setLC(mode=0)
            domapp.startRun()            
            domapp.setMonitoringIntervals(hwInt=1, fastInt=1)
            t = MiniTimer(self.runLength*1000)
            fastVirgin  = True
            HWVirgin    = True
            gotMoniFast = False
            gotMoniHW   = False
            ok      = True
            while ok and not t.expired():
                mlist = getLastMoniMsgs(domapp)
                for m in mlist:
                    self.debugMsgs.append(m)
                    s1 = search(r'^F (\d+) (\d+) (\d+) (\d+)$', m)
                    s2 = search(r'^\[HW EVT .+? (\d+) (\d+)\]', m)
                    if s1:
                        gotMoniFast = True
                        if fastVirgin: fastVirgin = False # Skip first record which might be smaller or zero
                        else:
                            fSPE = int(s1.group(1))
                            if fSPE < 1:
                                self.fail("Insufficient 'fast' SPE scaler value (%d counts)" % fSPE)
                                ok = False
                                break
                    if s2:
                        gotMoniHW = True
                        if HWVirgin: HWVirgin = False
                        else:
                            hwSPE = int(s2.group(1))
                            if hwSPE < 1:
                                self.fail("Insufficient 'HW' SPE scaler value (%d counts)" % hwSPE)
                                ok = False
                                break
                            
            if not gotMoniFast:
                self.fail("Got no 'fast' monitoring records in run!")
                self.appendMoni(domapp)
            if not gotMoniHW:
                self.fail("Got no 'HW' monitoring records in run!")
                self.appendMoni(domapp)
                
            domapp.endRun()
            self.turnOffHV(domapp)
   
        except Exception, e:
            self.fail(exc_string())
            try:
                self.turnOffHV(domapp)
                domapp.endRun()
            except:
                pass
            self.appendMoni(domapp)
            return

        
class FastMoniTestHV(DOMAppHVTest):
    """
    Set fast monitoring interval and make sure rate of generated records
    is roughly correct; check that SPE and MPE scalers match those in
    so-called 'Hardware State Events'
    """
    # FIXME: clean up (simplify) exception handling below - some cases not
    #        caught correctly
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        numZeroRecs         = 0
        fastInterval        = 2 # Number of seconds delay between records
        tolerance           = 4 # Want to be within this many records of expected
        fastMoniRecordCount = 0
        hwMoniRecordCount   = 0
        expectedRecordCount = self.runLength/fastInterval
        hitsMonitored       = 0
        hitsReadOut         = 0
        try:
            domapp.setMonitoringIntervals(0, 0, 0)
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.setPulser(mode=BEACON, rate=4)
            self.setHV(domapp, DOMAppHVTest.nominalHVVolts)
            domapp.writeDAC(DAC_SINGLE_SPE_THRESH, 550)
            domapp.selectMUX(255)
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)            
            domapp.startRun()
            domapp.setMonitoringIntervals(hwInt=fastInterval, fastInt=fastInterval)
        except Exception, e:
            self.fail(exc_string())
            try:
                self.turnOffHV(domapp)
            except:
                pass
            self.appendMoni(domapp)
            return

        def countDeltaHits(): # Mini functionlette to count compressed hits
            ret = 0
            hitdata = domapp.getWaveformData()
            if len(hitdata) > 0:
                hitBuf = DeltaHitBuf(hitdata) # Does basic integrity check
                for hit in hitBuf.next():
                    ret += 1
            return ret
        
        t = MiniTimer(self.runLength*1000)
        while not t.expired():
            # Get hit data, to cause hit counters to fill
            try:
                hitsReadOut += countDeltaHits()
            except Exception, e:
                self.fail("GET WAVEFORM DATA FAILED: %s" % exc_string())
                self.appendMoni(domapp)
                break                                                                                                                                                
            # Moni data
            mlist = getLastMoniMsgs(domapp)
            # Make sure 'fast' records are present and agree with
            # 'hw' moni events.
            fSPE     = None
            fMPE     = None
            hwSPE    = None
            hwMPE    = None
            gotF     = False
            gotHW    = False
            for m in mlist:
                s1 = search(r'^F (\d+) (\d+) (\d+) (\d+)$', m)
                s2 = search(r'^\[HW EVT .+? (\d+) (\d+)\]', m)
                if s1:
                    gotF = True
                    fastMoniRecordCount += 1
                    fSPE  = s1.group(1)
                    fMPE  = s1.group(2)
                    hitsMonitored += int(s1.group(3))
                    fHits = int(s1.group(3))
                    deadtime = int(s1.group(4))
                    if deadtime <= 0:
                        numZeroRecs += 1
                        if numZeroRecs > 1:
                            self.fail("Too many bad scaler deadtime values! (%d)" % numZeroRecs)
                if s2:
                    gotHW = True
                    hwMoniRecordCount += 1
                    hwSPE = s2.group(1)
                    hwMPE = s2.group(2)
                self.debugMsgs.append(m)
                if gotF and gotHW:
                    gotF = False
                    gotHW = False
                    if(hwSPE != fSPE):
                        self.fail("ERROR: SPE values missing or disagree (%s %s)!" % (fSPE, hwSPE))
                    elif(not hwMPE or hwMPE != fMPE):
                        self.fail("ERROR: MPE values missing or disagree (%s %s)!" % (fMPE, hwMPE))
            
        if(abs(expectedRecordCount-fastMoniRecordCount) > tolerance):
            self.fail("Fast moni record rate mismatch: wanted %d, got %d (tolerance %d)"
                      % (expectedRecordCount, fastMoniRecordCount, tolerance))
        if(hwMoniRecordCount == 0): # Make sure we had SOMETHING to compare to
            self.fail("ERROR: NO HW monitoring records available!")

        try:
            domapp.endRun()
            self.turnOffHV(domapp)
        except Exception, e:
            self.fail(exc_string())
            try:
                self.turnOffHV(domapp)
                domapp.endRun()
            except:
                pass
            self.appendMoni(domapp)
            return

        # Make sure hits read out equals hits monitored; first, get last monis
        try:
            hitsReadOut += countDeltaHits()
        except Exception, e:
            self.fail("GET WAVEFORM DATA FAILED: %s" % exc_string())
            self.appendMoni(domapp)
            return

        time.sleep(fastInterval+1) # Make sure we get our last moni events!
        
        mlist = getLastMoniMsgs(domapp)
        for m in mlist:
            s1 = search(r'^F \d+ \d+ (\d+) \d+$', m)
            if s1:
                hitsMonitored += int(s1.group(1))
                            
        if hitsReadOut != hitsMonitored:
            self.fail("Total hits monitored (%d) doesn't equal total hits read out (%d)"
                      % (hitsMonitored, hitsReadOut))


class SLCOnlyTest(DOMAppTest):
    """
    Parent class for SLCOnlyPulserTest and SLCOnlyHVTest, which does the test
    either with pulser or with HV on/SPEs
    """
    def run(self, fd, doHV=False):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.selectMUX(255)
            if doHV:
                self.setHV(domapp, DOMAppHVTest.nominalHVVolts)
                domapp.setPulser(mode=BEACON, rate=4)
            else:
                domapp.setPulser(mode=FE_PULSER, rate=10)
            domapp.setDataFormat(2)
            domapp.setCompressionMode(2)            
            domapp.setLC(mode=5, type=1, source=0, span=1)
            domapp.disableMinbias() # We explicitly do not want minbias set or waveforms will creep in!
            domapp.startRun()
            domapp.setMonitoringIntervals(hwInt=5, fastInt=1)

            nhits = 0
            t = MiniTimer(self.runLength*1000)
            broken = False
            while not broken and not t.expired():
                self.appendMoni(domapp)
                hitdata = domapp.getWaveformData()
                if len(hitdata) > 0:
                    hitBuf = DeltaHitBuf(hitdata) # Does basic integrity check
                    for hit in hitBuf.next():
                        if not hit.is_spe: continue # Skip beacon-only hits
                        nhits += 1
                        if (not hit.is_beacon) and hit.hitsize > 12:
                            self.fail("After %d hits, SLC-only hit buffer contains waveforms (%d bytes)" \
                                      % (nhits, hit.hitsize))
                            self.debugMsgs.append(str(hit))
                            broken = True
                            break

            domapp.endRun()
            if doHV: self.turnOffHV(domapp)
            domapp.setPulser(mode=BEACON, rate=4) # Turn FE pulser off

            if nhits < 1:
                self.fail("No hits found!")
                
        except Exception, e:
            self.fail(exc_string())
            try:
                if doHV: self.turnOffHV(domapp)
                domapp.endRun()
            except:
                pass
            self.appendMoni(domapp)
            return

        
class SLCOnlyPulserTest(SLCOnlyTest, DOMAppTest):
    """
    Test 'SLC-Only' mode where SLC is required and LC is "off" (compression
    on.  Requirement is to get some non-beacon hits but NO waveforms - just
    delta-compression headers.  This test runs with front end pulser (no HV).
    """
    def run(self, fd):
        SLCOnlyTest.run(self, fd)

            
class SLCOnlyHVTest(DOMAppHVTest, SLCOnlyTest):
    """
    Test 'SLC-Only' mode where SLC is required and LC is "off" (compression
    on.  Requirement is to get some non-beacon hits but NO waveforms - just
    delta-compression headers.  This test runs with real SPEs with HV on.
    """
    def run(self, fd):
        SLCOnlyTest.run(self, fd, doHV=True)

    
class SNDeltaSPEHitTest(DOMAppHVTest):
    """
    Collect both SPE and SN data, make sure there are no gaps in SN data
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)        
        try:
            domapp.resetMonitorBuffer()
            setDefaultDACs(domapp)
            domapp.setTriggerMode(2)
            domapp.selectMUX(255)
            domapp.setMonitoringIntervals()
            self.setHV(domapp, DOMAppHVTest.nominalHVVolts)
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
                    self.fail("GET WAVEFORM DATA FAILED: %s" % exc_string())
                    self.appendMoni(domapp)
                    break

                # SN data
                
                if snTimer.expired():
                    try:
                        sndata = domapp.getSupernovaData()
                        self.debugMsgs.append("Got %d sn bytes" % len(sndata))
                        self.debugMsgs.append("Delta hits: %d bytes total" % nbDelta)
                    except Exception, e:
                        self.fail("GET SN DATA FAILED: %s" % exc_string())
                        self.appendMoni(domapp)
                        break

                    try:
                        prevClock, prevBins = self.checkSNdata(sndata, prevClock, prevBins)
                    except Exception, e:
                        self.fail("SN data check failed: '%s'" % e)
                        self.appendMoni(domapp)
                        break
                    
                    # Reset timer for next time
                    snTimer = MiniTimer(1000)

            domapp.endRun()
            self.turnOffHV(domapp)

        except Exception, e:
            self.fail(exc_string())
            try:
                self.turnOffHV(domapp)
                domapp.endRun()
            except:
                pass
            self.appendMoni(domapp)
            return


class TimedDOMAppTest(DOMAppHVTest):
    """
    This class is an attempt to abstract out some common behaviors in several of the tests.
    !!!!!!!!!
    TRY TO USE THIS CLASS FOR NEW TESTS, AND BACK-PORT THE OLD ONES AS TIME ALLOWS!
    !!!!!!!!
    """
    targetHV = None
                              
    def resetDomapp(self, domapp):
        """
        Reset method (generic)
        """
        domapp.setMonitoringIntervals(0, 0, 0)
        domapp.resetMonitorBuffer()
        
    def prepDomapp(self, domapp):
        """
        Generic preparation method for domapp test - override me
        """
        setDefaultDACs(domapp)
        if self.targetHV is not None:
            self.setHV(domapp, self.targetHV)

    def startRun(self, domapp):
        """
        Generic start method
        """
        domapp.startRun()
        domapp.setMonitoringIntervals(hwInt=5, fastInt=1)

    def endRun(self, domapp):
        domapp.endRun()

    def cleanup(self, domapp):
        """
        Generic cleanup method for domapp test
        """
        if self.targetHV is not None:
            self.turnOffHV(domapp)
        self.appendMoni(domapp)

    def interval(self, domapp):
        """
        Do every second (e.g. poll domapp)
        """
        return False # Don't end test early

    def runcore(self, domapp):
        t = MiniTimer(self.runLength*1000)
        while not t.expired():
            if self.interval(domapp):
                break
            time.sleep(1)

    def run(self, fd):
        """
        Generic run method - shouldn't have to override me
        """
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        try:
            self.resetDomapp(domapp)
            self.prepDomapp(domapp)
            self.startRun(domapp)
        except Exception, e:
            self.fail(exc_string())
            self.cleanup(domapp)
            return

        splat = False
        try:
            self.runcore(domapp)
        except Exception, e:
            self.fail(exc_string())
            splat = True

        try:
            self.endRun(domapp)
        except Exception, e:
            self.fail(exc_string())
            splat = True
            
        try:
            self.cleanup(domapp)
        except Exception, e:
            self.fail(exc_string())
            splat = True

        if not splat:
            self.finalCheck()

    def finalCheck(self):
        """
        Final checks on data go here
        """


class FADCClockPollutionTest(TimedDOMAppTest):
    """
    Look for 20 MHz oscillations
    """
    targetHV = 800 # This will cause HV to get turned on!
    
    def prepDomapp(self, domapp):
        TimedDOMAppTest.prepDomapp(self, domapp)
        ATWD_PEDS_PER_LOOP = 100
        FADC_PEDS_PER_LOOP = 200
        MAX_ALLOWED_RMS = 1.0
        numloops = 100
        domapp.setTriggerMode(2)
        domapp.selectMUX(255)
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
        sign = 1
        sum  = 0
        wf = []
        sumval = 0
        nbins = 256
        for samp in xrange(nbins):
            idx = 8*128 + samp
            val, = unpack('>H', buf[idx*2:idx*2+2])
            wf.append(val)
            sumval += val
        avg = float(sumval)/float(nbins)
        for samp in xrange(nbins):
            sum += sign*(wf[samp]-avg)
            sign = -sign
            self.debugMsgs.append("sign=%d sum=%d samp=%d val=%d" % (sign, sum, samp, wf[samp]))
        MAX_OSC = 90
        if abs(sum) > MAX_OSC:
            self.fail("Alternating sum abs(%d) > %d!" % (sum, MAX_OSC))
                                                    
    def interval(self, domapp):
        return True # Short-circuit 'running' phase - do everything in prep

    
class PedestalStabilityTest(TimedDOMAppTest):
    """
    Measure pedestal stability by taking an average over several tries; replaces old-style test
    by subclassing the new style of test.
    """
    
    targetHV = 800 # This will cause HV to get turned on!
    
    def prepDomapp(self, domapp):
        TimedDOMAppTest.prepDomapp(self, domapp)
        ATWD_PEDS_PER_LOOP = 100
        FADC_PEDS_PER_LOOP = 200
        MAX_ALLOWED_RMS    = 1.0
        numloops           = 100
        domapp.setTriggerMode(2)
        domapp.selectMUX(255)

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

            self.debugMsgs.append("Trial %d FADC waveforms:" % numloops)
            
            for samp in xrange(256):
                idx = 8*128 + samp
                val, = unpack('>H', buf[idx*2:idx*2+2])
                self.debugMsgs.append("%d, %d" % (samp, val))
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

        if maxrms > MAX_ALLOWED_RMS:
            raise Exception("Maximum allowed RMS (%2.3f) exceeeded (%2.3f)!" %\
                            (MAX_ALLOWED_RMS, maxrms))

    def interval(self, domapp): return True # Short-circuit 'running' phase - do everything in prep

class NoHVPedestalStabilityTest(PedestalStabilityTest):
    """
    Same as NewPedestalStabilityTest, but with HV off
    """
    targetHV = None
    

class PedestalMonitoringTest(TimedDOMAppTest):
    """
    Make sure pedestal monitoring records are present and well-formatted when
    pedestal generation occurs
    """
    def __init__(self, card, wire, dom, dor, runLength=10):
        self._biases = {}
        super(TimedDOMAppTest, self).__init__(card, wire, dom, dor, runLength)

    def do_peds(self, domapp, set_bias=None):
        if set_bias:
            self._biases = set_bias
        domapp.collectPedestals(100, 100, 200, set_bias)
        
    def prepDomapp(self, domapp):
        self.atwd_norm = [[[0 for bin in range(128)] for chan in range(3)] for chip in 0, 1]
        self.atwd_sums = [[[0 for bin in range(128)] for chan in range(3)] for chip in 0, 1]
        self.totalBeaconHits = 0
        self.contaminated = False
        self.contaminatedTrials = 0
        TimedDOMAppTest.prepDomapp(self, domapp)
        # Superclass DAC settings don't work for SPTS ichub21 00a,
        # need to tweak SPE threshold or we saturate w/ fake SPEs:
        setDAC(domapp, DAC_SINGLE_SPE_THRESH, 300)  
        domapp.setTriggerMode(2)            
        domapp.setPulser(mode=BEACON, rate=100)
        domapp.setDataFormat(0)
        domapp.setCompressionMode(0)
                                    
        pedcount = 0
        try:
            self.do_peds(domapp)
            mlist = getLastMoniMsgs(domapp)
            for m in mlist:
                self.debugMsgs.append(m)
                s = search(r'PED-ATWD (?P<atwd>\S+) CH (?P<ch>\d+)--'
                           r'(?P<trials>\d+) trials, bias (?P<bias>\d+)', m)
                if s:
                    pedcount += 1
                    if self._biases:
                        atwdnum = s.group("atwd") == "B" and 1 or 0
                        channel = int(s.group("ch"))
                        if channel == 3:
                            continue
                        bias_wanted = self._biases["atwd%s" % atwdnum][channel]
                        bias_found = int(s.group("bias"))
                        if bias_wanted != bias_found:
                            self.fail("Expected programmed bias %d, got %d!!!" % \
                                      (bias_wanted, bias_found))
                    continue

                s = search('pedestal average contaminated.*trial (\d+)', m)
                if s:
                    self.contaminatedTrials = int(s.group(1))
                    continue

                s = search('continuing with possibly light-contaminated pedestal', m)
                if s:
                    self.contaminated = True
                    continue
                
        except Exception, e:
            self.fail(exc_string())
            self.appendMoni(domapp)
            return

        if pedcount < 8:
            self.fail("Insufficient (%d) pedestal monitoring records" % \
                      pedcount)
            self.appendMoni(domapp)

    def interval(self, domapp):
        if not self._biases:
            return
        hitdata = domapp.getWaveformData()
        if len(hitdata) > 0:
            hitBuf = EngHitBuf(hitdata)
            for hit in hitBuf.next():
                assert hit.is_beacon, "Hit is not beacon hit!!! Data follows:\n%s" % hit
                self.totalBeaconHits += 1
                for chan in range(3):
                    for bin in range(128):
                        thisbin = hit.atwd[chan][bin]
                        self.atwd_norm[hit.atwd_chip][chan][bin] += 1
                        self.atwd_sums[hit.atwd_chip][chan][bin] += thisbin
        return False

    def finalCheck(self):
        if not self._biases:
            return
        if self.totalBeaconHits < 1:
            self.fail("Got no waveform data!!!")
        else:
            self.summary += "%d hits, " % self.totalBeaconHits
            for chip in range(2):
                for chan in range(3):
                    sum_over_bins = 0.0
                    for bin in range(128):
                        sum = self.atwd_sums[chip][chan][bin]
                        norm = self.atwd_norm[chip][chan][bin]
                        sum_over_bins += sum/float(norm)
                    average_over_bins = sum_over_bins / 128.
                    self.summary += "%1.3f " % average_over_bins
                    expected = self._biases['atwd%d' % chip][chan]
                                                             
                    if abs(average_over_bins - expected) > 2.:
                        self.fail('Chip %d channel %d average ped. value %1.3f '
                                  'deviates from expected (%1.3f)' % (chip, chan,
                                  average_over_bins, expected))
                                  

class PedestalSetBiasTest(PedestalMonitoringTest):
    def __init__(self, card, wire, dom, dor, runLength=10):
        runLength = 30
        super(PedestalSetBiasTest, self).__init__(card, wire, dom, dor, runLength)

    def do_peds(self, domapp):
        super(PedestalSetBiasTest, self).do_peds(domapp,
                                            set_bias = {'atwd0': [100,200,300],
                                                        'atwd1': [400,500,600]})

class DomappPowerCycle(SimpleDomAppTest):
    """
    Transition from domapp back to domapp by power-cycling.
    """    
    def __init__(self, card, wire, dom, dor):
        super(DomappPowerCycle, self).__init__(card, wire, dom, dor)
        self.syncWithPartner = True
        self.maxPowerOnTrials = 3

    def run(self, fd):
        self.dor.close()
        eStart = self.startEvent   # Indicates we need to sync A/B DOMs because of the power-cycle
        if eStart:
            if self.dom == 'B':
                # This DOM will flag when it's ready to be powered off
                eStart.set()
            else:
                # This DOM will wait until partner has signaled it's ready to go
                eStart.wait()
                eStart.clear()                

        # A DOM normally controls power cycle for a pair
        # Exception is if A DOM was excluded from testing
        if (self.dom == 'A') or ((not eStart) and (self.dom == 'B')):
            # POWER CYCLE
            dor = Driver()
            dor.off(self.card, self.wire)
            time.sleep(5)

            if dor[self.card][self.wire].powered:
                self.fail("Couldn't power off the DOM")
                
            # FIX ME: why does one have to do this multiple times for some wire pairs?!
            pwrtrial = 0
            while (pwrtrial < self.maxPowerOnTrials) and not dor[self.card][self.wire].powered:
                dor.on(self.card, self.wire)
                time.sleep(5)
                pwrtrial += 1

            if not dor[self.card][self.wire].powered:
                self.fail("Couldn't power on the DOM in %d tries" % self.maxPowerOnTrials)
                            
        # Put A DOM back into domapp            
        if self.dom == 'A':
            self.dor.open()
            ok = self.dor.isInConfigboot2()
            if not ok:
                self.fail("Didn't find DOM in configboot after power-cycle!")
            time.sleep(3)                
            ok, txt = self.dor.configbootToIceboot2()
            if not ok:
                self.fail("Could not transition into iceboot")
                self.debugMsgs.append(txt)

            if self.uploadFileName: 
                ok, txt = self.dor.uploadDomapp2(self.uploadFileName)
            else:
                ok, txt = self.dor.icebootToDomapp2()
            if not ok:        
                self.fail("Could not transition into domapp")
                self.debugMsgs.append(txt)            

        eFinish = self.finishEvent
        if eFinish:
            if self.dom == 'B':
                # This DOM will wait on the testing DOM to finish
                eFinish.wait()
                eFinish.clear()
            else:
                # This DOM will signal that is has finished with the test
                eFinish.set()
        
        # Put B DOM back into domapp
        if self.dom == 'B':
            self.dor.open()
            ok = self.dor.isInConfigboot2()
            if not ok:
                self.fail("Didn't find DOM in configboot after power-cycle!")
            time.sleep(3)                
            ok, txt = self.dor.configbootToIceboot2()
            if not ok:
                self.fail("Could not transition into iceboot")
                self.debugMsgs.append(txt)

            if self.uploadFileName: 
                ok, txt = self.dor.uploadDomapp2(self.uploadFileName)
            else:
                ok, txt = self.dor.icebootToDomapp2()
            if not ok:        
                self.fail("Could not transition into domapp")
                self.debugMsgs.append(txt)
                
    
class PedestalPrescanTest(PedestalSetBiasTest):
    """
    Test that ATWDs are prescanned by collecting pedestals averages with
    a small number of samples, and looking for a bias problem.  Must be
    power-cycled to expose prescanning problem, though.
    """
    def do_peds(self, domapp):
        set_bias = {'atwd0': [600,600,600],
                    'atwd1': [600,600,600]}
        self._biases = set_bias
        domapp.collectPedestals(10, 10, 20, set_bias)

class PedestalContaminationTest(PedestalSetBiasTest):
    """
    Test that pedestals are not light-contaminated (or that the
    light-contamination code is not overzealous), by watching for
    monitoring messages tracking the contamination status.
    """
    def do_peds(self, domapp):
        set_bias = {'atwd0': [600,600,600],
                    'atwd1': [600,600,600]}
        self._biases = set_bias
        domapp.collectPedestals(10, 10, 20, set_bias)

    def finalCheck(self):
        if not self._biases:
            return
        if self.totalBeaconHits < 1:
            self.fail("Got no waveform data!!!")
        if self.contaminated or (self.contaminatedTrials > 2):
            self.fail("Pedestal was contaminated after %d trials!" % (self.contaminatedTrials))
        
        self.summary += "%d trial(s)" % (self.contaminatedTrials+1)
        
class DeltaCompressionBeaconTest(DOMAppTest):
    """
    Make sure delta-compressed beacons have all four ATWD channels read out
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
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
            self.fail(exc_string())
            self.appendMoni(domapp)
            return

        # collect data
        t = MiniTimer(self.runLength * 1000)
        gotData = False
        while not t.expired():
            self.appendMoni(domapp)

            # Fetch hit data
            good = True
            try:
                hitdata = domapp.getWaveformData()
                if len(hitdata) > 0:
                    gotData = True
                    hitBuf = DeltaHitBuf(hitdata)
                    for hit in hitBuf.next():
                        if hit.is_beacon and hit.natwdch < 3:
                            self.debugMsgs.append("Beacon hit has insufficient readouts!!!")
                            self.debugMsgs.append(`hit`)
                            good = False
                            break
            except Exception, e:
                self.fail("GET WAVEFORM DATA FAILED: %s" % exc_string())
                self.appendMoni(domapp)
                break
            
            if not good:
                self.fail("No hit data was retrieved!")
                break

        # end run
        try:
            domapp.endRun()
        except Exception, e:
            self.fail("END RUN FAILED: %s" % exc_string())
            self.appendMoni(domapp)
            
        # Make sure we got SOMETHING....
        if not gotData:
            self.fail("Didn't get any hit data!")

class SLCEngineeringFormatTest(DOMAppTest):
    """
    Disallow SLC when engineering format is set
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
        domapp.setDataFormat(0)
        try:
            domapp.setLC(mode=1, type=1, source=0, span=1)
            self.fail('DOMApp did NOT complain about SLC when engineering format set')
        except MessagingException: # We actually want this
            pass
        # Set delta compression and SLC, then revert to eng. format...
        # ... should reset LC mode and type.
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        domapp.setLC(mode=1, type=1, source=0, span=1)
        domapp.setDataFormat(0)
        domapp.startRun()
        mlist = getLastMoniMsgs(domapp)
        domapp.endRun()
        mode, type = getLastModeTypeMsg(mlist)
        if mode != 0 or type != 0:
            self.debugMsgs.append(mlist)
            self.fail('Got mode=%s, type=%s' % (mode, type))


def getLastModeTypeMsg(mlist):
    """
    Return LC mode and type as reported from a short stream of domapp monitoring data
    """
    mode, type = None, None
    for l in mlist:
        m = search('set_HAL_lc_mode\(LCmode=(\d+), LCtype=(\d+)\)', l)
        if m:
            mode = int(m.group(1))
            type = int(m.group(2))
    return mode, type


class SNTest(DOMAppTest):
    """
    Make sure no gaps are present in SN data
    """
    def run(self, fd):
        domapp = DOMApp(self.card, self.wire, self.dom, fd)
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
            self.fail(exc_string())
            self.appendMoni(domapp)
            return
            
        prevBins, prevClock = None, None

        for i in xrange(0,self.runLength):

            self.appendMoni(domapp)
            
            # Fetch supernova

            try:
                sndata = domapp.getSupernovaData()
            except Exception, e:
                self.fail("GET SN DATA FAILED: %s" % exc_string())
                self.appendMoni(domapp)
                break

            try:
                prevClock, prevBins = self.checkSNdata(sndata, prevClock, prevBins)
            except Exception, e:
                self.fail("SN data check failed: '%s'" % e)
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
            self.fail("END RUN FAILED: %s" % exc_string())
            self.appendMoni(domapp)


class MinimumBiasTest(TimedDOMAppTest):
    """
    Test new minimum-bias (no LC required) functionality - require LC, configure minimum bias,
    expect some hits to show up with bit 30 set in the first header word.
    """
    def prepDomapp(self, domapp):
        self.runLength = 30 # Run length must be longer to avoid
                            # effect where LC of one DOM beats against
                            # another, causing beacons to be
                            # suppressed; also we stop early when a
                            # beacon hit is found        
        self.gotMinbias = False
        self.totalHits  = 0
        TimedDOMAppTest.prepDomapp(self, domapp)
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 1000)
        domapp.setTriggerMode(2)
        domapp.setPulser(mode=FE_PULSER, rate=8000)
        domapp.writeDAC(DAC_SINGLE_SPE_THRESH, 650)
        domapp.setLC(mode=1, type=2, source=0, span=1, window=(25,25)) # Set min. window, to get fewer hits
        domapp.enableMinbias()

    def cleanupDomapp(self, domapp):
        domapp.disableMinbias()
        
    def interval(self, domapp):
        hitdata = domapp.getWaveformData()
        if len(hitdata) > 0:
            hitBuf = DeltaHitBuf(hitdata)
            for hit in hitBuf.next():
                self.totalHits += 1
                self.debugMsgs.append("hit word0 = 0x%x" % hit.words[0])
                if hit.isMinbias:
                    self.gotMinbias = True
                    return True # Test successful, if cleanup is ok
        return False # Keep going

    def finalCheck(self):
        if self.totalHits < 1:
            self.fail("Got no waveform data!!!")
        if not self.gotMinbias:
            self.fail("Got no minimum bias data (%d total hits)!!!" % self.totalHits)

class ATWDSelectTest(TimedDOMAppTest):
    """
    Use the more abstract TimedDOMAppTest to make sure that the ATWD select function works
    """
    def prepDomapp(self, domapp):
        self.hadData  = False
        self.hadAtwdA = False
        self.hadAtwdB = False
        TimedDOMAppTest.prepDomapp(self, domapp)
        setDAC(domapp, DAC_INTERNAL_PULSER_AMP, 1000)
        setDAC(domapp, DAC_SINGLE_SPE_THRESH, 600)
        domapp.setTriggerMode(2)
        domapp.setPulser(mode=FE_PULSER, rate=8000)
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        domapp.setLC(mode=0) # Make sure no LC is required
        
    def interval(self, domapp):
        hitdata = domapp.getWaveformData()
        if len(hitdata) > 0:
            self.hadData = True
            hitBuf = DeltaHitBuf(hitdata)
            for hit in hitBuf.next():
                if hit.atwd_chip == 0:
                    self.hadAtwdA = True
                elif hit.atwd_chip == 1:
                    self.hadAtwdB = True
        return False # Don't abort early

    def cleanupDomapp(self, domapp):
        domapp.selectAtwd(2)
        TimedDOMAppTest.cleanup(self)

    def finalCheck(self):
        if not self.hadData:
            self.fail("Got no waveform data!")
        
class ATWDAOnlyTest(ATWDSelectTest):
    """
    Require that selecting only ATWD A works
    """
    def prepDomapp(self, domapp):
        domapp.selectAtwd(0)
        ATWDSelectTest.prepDomapp(self, domapp)
                                                   
    def finalCheck(self):
        if not self.hadAtwdA:
            self.fail("Got no ATWD A data!")
        if self.hadAtwdB:
            self.fail("Got ATWD B data - shouldn't have!")
        ATWDSelectTest.finalCheck(self)

class ATWDBOnlyTest(ATWDSelectTest):
    """
    Require that selecting only ATWD B works
    """
    def prepDomapp(self, domapp):
        domapp.selectAtwd(1)
        ATWDSelectTest.prepDomapp(self, domapp)

    def finalCheck(self):
        if self.hadAtwdA:
            self.fail("Got ATWD A data - shouldn't have!")
        if not self.hadAtwdB:
            self.fail("Got no ATWD B data!")
        ATWDSelectTest.finalCheck(self)

            
class ATWDBothTest(ATWDSelectTest):
    """
    Require that both ATWD chips work
    """

    def prepDomapp(self, domapp):
        domapp.selectAtwd(2)
        ATWDSelectTest.prepDomapp(self, domapp)
        
    def finalCheck(self):
        if not self.hadAtwdA:
            self.fail("Got no ATWD A data!")
        if not self.hadAtwdB:
            self.fail("Got no ATWD B data!")
        ATWDSelectTest.finalCheck(self)


class FRecordsLcTypePrepTest(TimedDOMAppTest):
    """
    Make sure we can get/set SLC/HLC for F record rate readout
    """
    def prepDomapp(self, domapp):
        TimedDOMAppTest.prepDomapp(self, domapp)
        # Check default F moni rate type:
        t, = unpack('b', domapp.get_f_moni_rate_type())
        if t != 0:
            self.fail('Unexpected F moni rate type (%d), expected 0!' % t)

        # Test set/get:
        domapp.set_f_moni_rate_type(1) # SLC
        t, = unpack('b', domapp.get_f_moni_rate_type())
        if t != 1:
            self.fail('Unexpected F moni rate type (%d), expected 1!' % t)

    def interval(self, domapp): # Skip actual data taking
        return True
    

class LCFRecordsTest(TimedDOMAppTest):
    """
    Make sure one can set HLC/SLC 'F' records and that the behavior is correct; basically,
    SLC rates should be >= HLC rates.
    """
    targetHV = 1200 # Will cause HV to get turned on!
    HLC = 0
    SLC = 1
    
    def prepDomapp(self, domapp):
        TimedDOMAppTest.prepDomapp(self, domapp)
        self.hadData = False
        self.hit_sum = 0
        self.num_hit_recs = 0
        
        domapp.set_f_moni_rate_type(self.LcTypeForFRecord) # SLC
        t, = unpack('b', domapp.get_f_moni_rate_type())
        if t != self.LcTypeForFRecord:
            self.fail('Unexpected F moni rate type (%d), expected %d!' \
                      % (t, self.LcTypeForFRecord))

        setDefaultDACs(domapp)
        domapp.writeDAC(DAC_SINGLE_SPE_THRESH, 500)            
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        domapp.setTriggerMode(2)
        domapp.setLC(mode=1, type=1, source=0, span=1)
                    
    def interval(self, domapp):
        hitdata = domapp.getWaveformData()
        if len(hitdata) > 0:
            self.hadData = True
        moni = getLastMoniMsgs(domapp)
        for msg in moni:
            s = search(r'^F (\d+) (\d+) (\d+) (\d+)$', msg)
            if s:
                hits = int(s.group(3))
                self.hit_sum += hits
                self.num_hit_recs += 1

    def finalCheck(self):
        if not self.hadData:
            self.fail("Got no waveform data!")
        if self.num_hit_recs == 0:
            self.fail("Had no F records in data!")
        avg = self.hit_sum / float(self.num_hit_recs)
        if avg <= 0.0:
            self.fail("Average hit rate in F records was zero!")
        #print "LCtype %d hits %d recs %d avg %2.2f" % (self.LcTypeForFRecord,
        #                                               self.hit_sum,
        #                                               self.num_hit_recs,
        #                                               avg)



class HLCFRecordsTest(LCFRecordsTest):
    """
    Test F record LC hit counters in (default) HLC mode
    """
    LcTypeForFRecord = LCFRecordsTest.HLC


class SLCFRecordsTest(LCFRecordsTest):
    """
    Test F record LC hit counters in SLC mode
    """
    LcTypeForFRecord = LCFRecordsTest.SLC


def lbm_moni_warning_pointers(msg):
    """
    Detect LBM overflow in message and extract relevant pointers
    """
    if 'LBM OVER' in msg:
        m = search('pointer=(.+?) lbmp=(.+)', msg)
        assert(m)
        wrptr = int(m.group(1), 16)
        rdptr = int(m.group(2), 16)
        return wrptr, rdptr
    return None, None


class LBMOverflowTest(TimedDOMAppTest):
    """
    Verify correct behavior when hardware wraps LBM
    """
    def prepDomapp(self, domapp):
        """
        Set up delta-compression, beacon hits with high initial rate
        to fill LBM quickly (changed in runcore()).
        """
        TimedDOMAppTest.prepDomapp(self, domapp)
        domapp.setDataFormat(2)
        domapp.setCompressionMode(2)
        domapp.setTriggerMode(2)            
        domapp.setPulser(mode=BEACON, rate=40000)
        self.had_wf = False

    def runcore(self, domapp):
        """
        Watch what happens when LBM pointers reach the end of the
        physical address space.  LBM overflow messages should not
        occur here.  prepDomapp() has started the filling of LBM
        before we get to this point.  We wait for LBM to get nearly
        full, turn down the beacon rate, pull out hits as quickly as
        possible, let the LBM wrap occur, and check for overflow
        warnings in the monitoring stream.
        """
        start_of_top_region  = 0xFD00000
        end_of_bottom_region = 0x0008000

        # Wait for LBM to get close to filling up
        self.debugMsgs.append("Filling LBM...")
        while True:
            wrptr = domapp.get_lbm_ptrs()[0]
            if wrptr > start_of_top_region:
                break
        self.debugMsgs.append("Got to tail end of range: 0x%08x" % wrptr)

        # Slow down pulser to slowly approach end of range
        domapp.setPulser(mode=BEACON, rate=200)

        # Trigger initial LBM moni warning, and discard:
        wf_data = domapp.getWaveformData()
        found_initial_warning = False
        moni = getLastMoniMsgs(domapp)
        for msg in moni:
            wr, rd = lbm_moni_warning_pointers(msg)
            if wr is not None and rd is not None:
                # Check that we didn't already send this LBM overflow alert
                assert(not found_initial_warning)
                found_initial_warning = True
                assert(rd == 0)
        assert(found_initial_warning)

        # Collect data until wrap occurs
        i = 0
        while True:
            wf_data = domapp.getWaveformData() # Trigger LBM check
            if len(wf_data) > 0:
                self.had_wf = True
            wrptr, rdptr = domapp.get_lbm_ptrs()

            if not i%100:
                self.debugMsgs.append("wr: %08x  rd: %08x" % (wrptr, rdptr))
            i += 1

            # Stop when we have wrapped:
            if wrptr < start_of_top_region:
                break
            
        # Collect more WF data to make sure LBM message is triggered
        while len(domapp.getWaveformData()) == 0:
            pass

        # Collect resulting LBM warnings, if any:
        found_last_lbm_warnings = False
        while True:
            moni = getLastMoniMsgs(domapp)
            for msg in moni:
                self.debugMsgs.append(msg)
                wr, rd = lbm_moni_warning_pointers(msg)
                if wr is not None and rd is not None:
                    self.debugMsgs.append("OVFL 0x%08x 0x%08x" % (wr, rd))
                    found_last_lbm_warnings = True
            wrptr, rdptr = domapp.get_lbm_ptrs()
            if wrptr > end_of_bottom_region:
                break
        if found_last_lbm_warnings:
            self.fail("LBM warnings found, possible LBM wrap issue!")

    def finalCheck(self):
        if not self.had_wf:
            self.fail("No waveform data received!!!")

################################### HIGH-LEVEL TESTING LOGIC ###############################
            
class TestingSet:
    "Class for running multiple tests on a group of DOMs in parallel"
    def __init__(self, domDict, doOnly=False, domappOnly=False, stopOnFail=False, useDomapp=None):
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
        self.testsyncDict = {}
        self.testsyncLock = threading.Lock()
        self.stopOnFail   = stopOnFail
        self.useDomapp    = useDomapp
        self.domappOnly   = domappOnly

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

    def cycle(self, testList, startState, doOnly, domappOnly, c, w, d):
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
                # Skip non-domapp tests if required:
                if domappOnly \
                       and test.startState != DOMTest.STATE_DOMAPP \
                       and test.endState != DOMTest.STATE_DOMAPP:
                    continue
                # Use "test" if 
                # (1) test count hasn't surpassed specified count, and
                # (2) state doesn't change, and
                # (3) either we're doing all standard tests, or this test has been
                #     specified explicitly on the command line
                # otherwise use next state change
                if (doneDict[test] < self.ntrialsDict[test.__class__.__name__]) \
                       and test.startState == state:
                    nextTest = test
                    if test.endState == state \
                           and (not doOnly
                                or self.dontSkipDict.has_key(test.__class__.__name__)):
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

    def doAllTests(self, domid, c, w, d, doQuiet):
        startState = DOMTest.STATE_ICEBOOT
        testObjList = []
        dor = MiniDor(c, w, d)
        dor.open()
        for testName in self.testList:
            t = testName(c,w,d,dor)
            # Tell the domapp test to use alternate domapp if required:
            if self.useDomapp:
                t.setUploadFileName(self.useDomapp)
            # Set duration which may have been set explicitly by user:
            if self.durationDict[testName]:
                t.setRunLength(self.durationDict[testName])
            # Check if we need to synchronize this test with the same test on its partner DOM
            if t.requiresSync():
                #### LOCK -- partner may be trying to do this at the same time
                self.testsyncLock.acquire()
                try:
                    # Check to see if partner has already been here
                    e = None
                    for syncTest in self.testsyncDict:
                        if (type(t) == type(syncTest) and t.card == syncTest.card
                            and t.wire == syncTest.wire and t.dom != syncTest.dom):
                            e = self.testsyncDict[syncTest]
                            break
                    # Create the event if we didn't find it
                    if not e:
                        e = threading.Event()
                        self.testsyncDict[t] = e                
                    else:
                        # We have linked a pair of tests; set the sync event for both
                        t.setStartEvent(e)
                        syncTest.setStartEvent(e)
                        eFinish = threading.Event()
                        t.setFinishEvent(eFinish)
                        syncTest.setFinishEvent(eFinish)
                finally:
                    #### UNLOCK
                    self.testsyncLock.release()

            testObjList.append(t)
            # FIXME - check to make sure tests for which ntrialsDict > 1 preserve state
            if self.ntrialsDict[t.__class__.__name__] > 1 and t.changesState():
                raise RepeatedTestChangesStateException("Test %s changes DOM state, "
                                                        % t.__class__.__name__ + "cannot be repeated.")
        for test in self.cycle(testObjList, startState, self.doOnly, self.domappOnly, c, w, d):
            tstart = time.strftime("%d %b %Y %H:%M:%S", time.localtime())
            t0 = time.time()
            test.reset()
            test.run(dor.fd)
            dt = "%2.2f" % (time.time()-t0)
            if(test.startState != test.endState): # If state change, flush buffers etc. to get clean IO
                dor.close()
                dor.open()

            sf = False
            #### LOCK - have to protect shared counters, as well as TTY...
            self.counterLock.acquire()
            runLenStr = ""
            if test.runLength: runLenStr = "%d sec " % test.runLength
            if not doQuiet or test.result != "PASS":
                print "%s%s%s %s %s->%s %s %s%s: %s %s" % (c,w,d, tstart, test.startState,
                                                           test.endState, dt, runLenStr,
                                                           test.__class__.__name__, test.result,
                                                           test.summary)
            if test.result == "PASS":
                self.numpassed += 1
            else:
                self.numfailed += 1
                print "################################################"
                dbg = test.getDebugTxt()
                if len(dbg) > 0:
                    print dbg
                    print "################################################"
                if self.stopOnFail: sf = True
            self.numtests += 1
            test.clearDebugTxt()
            self.counterLock.release()
            #### UNLOCK
            if sf: break # Quit upon first failure
        dor.close()
            
    def runThread(self, domid, doQuiet, nCycles):
        c, w, d = self.domDict[domid]
        dor = Driver()
        try:
            for i in range(nCycles):
                self.doAllTests(domid, c,w,d, doQuiet)
        except KeyboardInterrupt:
            raise SystemExit
        except Exception, e:
            print "Test sequence aborted: %s" % exc_string()        
        
    def go(self, doQuiet, nCycles):
        self.tStart = datetime.now()
        for dom in self.domDict:
            self.threads[dom] = threading.Thread(target=self.runThread, args=(dom, doQuiet, nCycles))
            self.threads[dom].setDaemon(True)
            self.threads[dom].start()
        for dom in self.domDict:
            try:
                self.threads[dom].join()
            except Exception, e:
                print exc_string()
                raise SystemExit
        
    def summary(self):
        "show summary of results"
        dt = datetime.now() - self.tStart
        tElapsed = dt.days*86400 + dt.seconds
        return "Passed tests: %d   Failed tests: %d   Total: %d (%d seconds)" % (self.numpassed,
                                                                                 self.numfailed,
                                                                                 self.numtests, tElapsed)


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

    p.add_option("-F", "--flasher-tests",
                 action="store",      type="string",
                 dest="doFlasherTests",
                 help="Perform flasher tests, arg. is 'A' or 'B'")

    p.add_option("-P", "--power-cycle-tests",
                 action="store_true",
                 dest="doPowerTests",
                 help="Perform tests that require power-cycling")    
        
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

    p.add_option("-x", "--exclude-dom",
                 action="append",     type="string",    nargs=1,
                 dest="excludeDoms",  help="Exclude DOM (e.g. 00A; repeatable)")
    
    p.add_option("-a", "--upload-app",
                 action="store",      type="string",
                 dest="uploadApp",    help="Upload ARM application to execute " +\
                                           "instead of using flash image")
    p.add_option("-y", "--domapp-only",
                 action="store_true",
                 dest="domappOnly",   help="Only do domapp-related tests (including state changes)")

    p.add_option("-q", "--quiet",
                 action="store_true",
                 dest="doQuiet",      help="Suppress output for successful tests")

    p.add_option("-r", "--repeat-all",
                 action="store",      type="int",
                 dest="nCycles",      help="Number of times to repeat entire test cycle (default=1)")
    
    p.set_defaults(stopFail         = False,
                   doHVTests        = False,
                   doFlasherTests   = None,
                   doPowerTests     = False,
                   setDuration      = None,
                   repeatCount      = None,
                   excludeDoms      = None,
                   doOnly           = False,
                   domappOnly       = False,
                   doQuiet          = False,
                   nCycles          = 1,
                   uploadApp        = None,
                   listTests        = False)
    opt, args = p.parse_args()

    startState = DOMTest.STATE_ICEBOOT # FIXME: what if it's not?

    ListOfTests = [IcebootToConfigboot,
                   CheckConfigboot,
                   ConfigbootToIceboot,
                   CheckIceboot,
                   ATWDDeadtimeTest,
                   IcebootSelfReset,
                   SoftbootCycle,
                   IcebootToDomapp]

    # Domapp tests have to be kept together for the
    # -o option to work correctly (FIXME)
    ListOfTests.extend([ATWDAOnlyTest,
                        ATWDBOnlyTest,
                        ATWDBothTest,
                        MinimumBiasTest,
                        DeltaCompressionBeaconTest,
                        DOMIDTest,
                        IdleCounterTest,
                        GetDomappRelease,
                        MessageSizePulserTest,
                        PedestalMonitoringTest,
                        PedestalSetBiasTest,
                        PedestalContaminationTest,
                        NoHVPedestalStabilityTest,
                        ScalerDeadtimePulserTest,
                        SNTest,
                        SLCOnlyPulserTest,
                        SLCEngineeringFormatTest,
                        FRecordsLcTypePrepTest,
                        LBMBufferSizeTest,
                        LBMOverflowTest,
                        DomappUnitTests,
                        GetIntervalTest])

    if opt.doPowerTests:
        ListOfTests.extend([DomappPowerCycle,
                            PedestalPrescanTest])

    if opt.doFlasherTests == "A":
        ListOfTests.extend([FlasherATest])
    elif opt.doFlasherTests == "B":
        ListOfTests.extend([FlasherBTest])
    elif opt.doFlasherTests != None:
        print "Flasher test arg must be 'A' or 'B'"
        raise SystemExit
    
    if opt.doHVTests:
        ListOfTests.extend([FastMoniTestHV, PedestalStabilityTest, FADCClockPollutionTest,
                            SPEScalerNotZeroTest, SNDeltaSPEHitTest,
                            SLCOnlyHVTest, FADCHistoTest, 
                            ATWDHistoTest, HLCFRecordsTest, SLCFRecordsTest])
   # Post-domapp tests
    ListOfTests.extend([DomappToIceboot,
                        IcebootToEcho,
                        EchoTest,
                        EchoCommResetTest,
                        EchoToIceboot])
        
    try:
        dor = Driver()
        dor.enable_blocking(0)
        domDict = dor.get_active_doms(opt.excludeDoms)
    except Exception, e:
        print "No driver present? ('%s')" % e
        raise SystemExit

    if opt.uploadApp and not exists(opt.uploadApp):
        print "File %s does not exist!" % opt.uploadApp
        raise SystemExit


    testSet = TestingSet(domDict, doOnly=opt.doOnly, domappOnly=opt.domappOnly,
                         stopOnFail=opt.stopFail, useDomapp=opt.uploadApp)

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

    if not opt.doQuiet:
        print "domapp-tools-python revision: %s" % revTxt
        print "dor-driver release: %s" % dor.release
    
    testSet.go(opt.doQuiet, opt.nCycles)
    print testSet.summary()
    
    raise SystemExit

if __name__ == "__main__":
    main()
