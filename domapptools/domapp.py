#!/usr/bin/env python

import os, time
from sys import stderr
from struct import pack, unpack
from xml.sax import parse
from minitimer import MiniTimer

# Message facility typecodes
MESSAGE_HANDLER     = 1
DOM_SLOW_CONTROL    = 2
DATA_ACCESS         = 3
EXPERIMENT_CONTROL  = 4
TEST_MANAGER        = 5

# MESSAGE_HANDLER facility subtypes
MSGHAND_GET_DOM_ID              = 10
MSGHAND_ECHO_MSG                = 18
MSGHAND_ACCESS_MEMORY_CONTENTS  = 20
MSGHAND_GET_DOMAPP_RELEASE      = 24

# DOM_SLOW_CONTROL messages
DSC_WRITE_ONE_DAC               = 13
DSC_SET_PMT_HV                  = 14
DSC_ENABLE_PMT_HV               = 16
DSC_DISABLE_PMT_HV              = 18
DSC_QUERY_PMT_HV                = 22
DSC_SET_TRIG_MODE               = 31
DSC_SELECT_ATWD                 = 33
DSC_MUX_SELECT                  = 35
DSC_SET_PULSER_RATE             = 37
DSC_GET_PULSER_RATE             = 38
DSC_SET_PULSER_ON               = 39
DSC_SET_PULSER_OFF              = 40
DSC_SET_SCALER_DEADTIME         = 43
DSC_GET_SCALER_DEADTIME         = 44
DSC_SET_LOCAL_COIN_MODE         = 45
DSC_GET_LOCAL_COIN_MODE         = 46
DSC_SET_LOCAL_COIN_WINDOW       = 47
DSC_GET_LOCAL_COIN_WINDOW       = 48
DSC_SET_LC_TYPE                 = 49
DSC_GET_LC_TYPE                 = 50
DSC_SET_LC_TX                   = 51
DSC_GET_LC_TX                   = 52
DSC_SET_LC_SRC                  = 53
DSC_GET_LC_SRC                  = 54
DSC_SET_LC_SPAN                 = 55
DSC_GET_LC_SPAN                 = 56
DSC_SET_LC_CABLE_LEN            = 57
DSC_GET_LC_CABLE_LEN            = 58
DSC_ENABLE_SN                   = 59
DSC_DISABLE_SN                  = 60

# DATA_ACCESS message
DATA_ACC_GET_DATA               = 11
DATA_ACC_GET_NEXT_MONI_REC      = 12
DATA_ACC_SET_MONI_IVAL          = 13
DATA_ACC_SET_ENG_FMT            = 14
DATA_ACC_SET_BASELINE_THRESHOLD = 16
DATA_ACC_GET_BASELINE_THRESHOLD = 17
DATA_ACC_RESET_LOOKBACK_MEMORY  = 22
DATA_ACC_GET_FB_SERIAL          = 23
DATA_ACC_SET_DATA_FORMAT        = 24
DATA_ACC_GET_DATA_FORMAT        = 25
DATA_ACC_SET_COMP_MODE          = 26
DATA_ACC_GET_COMP_MODE          = 27
DATA_ACC_GET_SN_DATA            = 28
DATA_ACC_RESET_MONI_BUF         = 29
DATA_ACC_MONI_AVAIL             = 30

# EXPERIMENT_CONTROL messages subtypes
EXPCONTROL_BEGIN_RUN                = 12
EXPCONTROL_END_RUN                  = 13
EXPCONTROL_DO_PEDESTAL_COLLECTION   = 16
EXPCONTROL_GET_NUM_PEDESTALS        = 19
EXPCONTROL_GET_PEDESTAL_AVERAGES    = 20
EXPCONTROL_BEGIN_FB_RUN             = 27
EXPCONTROL_END_FB_RUN               = 28

# HAL DACs and ADCs
DAC_ATWD0_TRIGGER_BIAS          = 0
DAC_ATWD0_RAMP_TOP              = 1
DAC_ATWD0_RAMP_RATE             = 2
DAC_ATWD_ANALOG_REF             = 3
DAC_ATWD1_TRIGGER_BIAS          = 4
DAC_ATWD1_RAMP_TOP              = 5
DAC_ATWD1_RAMP_RATE             = 6
DAC_PMT_FE_PEDESTAL             = 7
DAC_MULTIPLE_SPE_THRESH         = 8
DAC_SINGLE_SPE_THRESH           = 9
DAC_FADC_REF                    = 10
DAC_INTERNAL_PULSER_AMP         = 11
DAC_LED_BRIGHTNESS              = 12
DAC_FE_AMP_LOWER_CLAMP          = 13
DAC_FLASHER_REF                 = 14
DAC_MUX_BIAS                    = 15

# Pulser modes
FE_PULSER  = 1
BEACON     = 2


DRIVER_ROOT = "/proc/driver/domhub"

_atwdMask = { 1 : { 0 : 0, 16 : 9, 32 : 1, 64 : 5, 128 : 13 },
              2 : { 0 : 0, 16 : 11, 32 : 3, 64 : 7, 128 : 15 } }
   
class MessagingException(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        if len(self.msg) < 8:
            return "(Message < 8 bytes)"
        return "(MT=%d,MST=%d,LEN=%d,0x%04x,ID=0x%02x,STATUS=0x%02x)" % unpack('>BBHHBB', self.msg)

class DOMApp:
   
    def __init__(self, card, pair, dom, fd):
        # File descriptor now passed into constructor - may be used outside of
        # DOMApp's methods...
        self.card    = card
        self.pair    = pair
        self.dom     = dom
        self.blksize = int(file(os.path.join(DRIVER_ROOT, "bufsiz")).read(100))
        self.fd      = fd
        
    def __del__(self):
        pass

    def sendMsg(self, type, subtype, data="", msgid=0, status=0, timeout=5000):
        ndat = len(data)
        msg  = pack(">BBHHBB", type, subtype, ndat, 0, msgid, status) + data
        EAGAIN = 11
        # FIXME: handle partial writes better
        t = MiniTimer(timeout)
        nw = 0
        while not t.expired():
            try:
                nw = os.write(self.fd, msg)
            except OSError, e:
                if e.errno == EAGAIN:
                    time.sleep(0.001) # Nothing available
                    continue
                else: raise
            except Exception: raise
            if nw > 0: break

        if nw != len(msg): raise Exception("Partial or failed write of %d bytes (wanted %d)" %
                                           (nw, len(msg)))
                
        t = MiniTimer(timeout)
        buf = ""
        while not t.expired():
            try:
                buf  += os.read(self.fd, self.blksize)
            except OSError, e:
                if e.errno == EAGAIN: time.sleep(0.001) # Nothing available
                else: raise
            except Exception: raise

            if len(buf) >= 8:
                msglen, = unpack('>H', buf[2:4])
                # FIXME - worry about second message in next portion of write
                if len(buf) >= msglen+8: break
                    
        if len(buf) < 8:
            raise MessagingException(buf[0:len(buf)])
        
        status, = unpack("B", buf[7])
        
        if status != 0x01:
            # print >>stderr, "Message Error: %s" % MessagingException(buf[0:8])
            raise MessagingException(buf[0:8])
        return buf[8:]

    def getMainboardID(self):
        return self.sendMsg(MESSAGE_HANDLER, MSGHAND_GET_DOM_ID)

    def getDomappVersion(self):
        return self.sendMsg(MESSAGE_HANDLER, MSGHAND_GET_DOMAPP_RELEASE)
    
    def enableHV(self):
        self.sendMsg(DOM_SLOW_CONTROL, DSC_ENABLE_PMT_HV)

    def disableHV(self):
        self.sendMsg(DOM_SLOW_CONTROL, DSC_DISABLE_PMT_HV)
       
    def setHV(self, hv):
        """
        Set the HV to hv DAC counts - range 0 (0.0 V) to 4095 (2047.5 V)
        Note that the HV should first be enabled with .enableHV() call
        """
        self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_PMT_HV,
                     data=pack(">H", int(hv))
                     )

    def queryHV(self):
        """
        Get the DOM HV setting as a tuple (x,y,z)
        """
        return unpack(">2H", self.sendMsg(DOM_SLOW_CONTROL, DSC_QUERY_PMT_HV))

    def setDataFormat(self, fmt):
        """
        Set data format
        fmt = 0: engineering format
        fmt = 1: default compression
        """
        self.sendMsg(DATA_ACCESS, DATA_ACC_SET_DATA_FORMAT, data=pack('b', fmt))

    def setCompressionMode(self, mode):
        """
        Set compression mode
        mode = 0: none (default)
        mode = 1: compressed data (delta compression)
        """
        self.sendMsg(DATA_ACCESS, DATA_ACC_SET_COMP_MODE, data=pack('b', mode))
        
    def setTriggerMode(self, mode):
        """
        Set the DOM triggering mode
          mode = 0: test pattern data
          mode = 1: forced triggers
          mode = 2: discriminator triggers (SPE)
          mode = 3: flasher board triggers
        """
        self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_TRIG_MODE, data=pack('b', mode))
       
    def enableSN(self, deadtime, mode):
        """
        Setup the supernova scalers.  Parameters are,
          - deadtime (nsec) : float - range [0, 512000]
          - mode : 0 = SPE, 1 = MPE
        Note that this *must* be called prior to EXPCONTROL_BEGIN_RUN
        """
        self.sendMsg(DOM_SLOW_CONTROL, DSC_ENABLE_SN,
                     data=pack(">ib", deadtime, mode)
                     )

    def setPulser(self, mode, rate=None):
        """
        Setup the onboard DOM pulser used for controlling heartbeats,
        electronic pulses, and the flasherboard pulse rate.
        Arguments:
           mode = FE_PULSER : disables heartbeats and enables the
                  analog pulser,
                = BEACON : disables analog pulser and enables
                  the heartbeat pulser
           rate = rate in Hz (roughly)
           """
        if mode == FE_PULSER:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_PULSER_ON)
        elif mode == BEACON:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_PULSER_OFF)
        if rate is not None:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_PULSER_RATE,
                         data=pack(">H", rate)
                         )
    def disableSN(self):
        self.sendMsg(DOM_SLOW_CONTROL, DSC_DISABLE_SN)
       
    def startRun(self):
        self.sendMsg(EXPERIMENT_CONTROL, EXPCONTROL_BEGIN_RUN)

    def endRun(self):
        self.sendMsg(EXPERIMENT_CONTROL, EXPCONTROL_END_RUN)

    def getSupernovaData(self):
        return self.sendMsg(DATA_ACCESS, DATA_ACC_GET_SN_DATA)
   
    def getWaveformData(self):
        """
        Returns up to 1 buffer worth of waveform data from
        lookback memory on DOM.  Please heed the caveats in
        the DOMAPP API about starting a run first.
        """
        return self.sendMsg(DATA_ACCESS, DATA_ACC_GET_DATA)

    def getMonitorData(self):
        return self.sendMsg(DATA_ACCESS, DATA_ACC_GET_NEXT_MONI_REC)

    def resetLookbackMemory(self):
        return self.sendMsg(DATA_ACCESS, DATA_ACC_RESET_LOOKBACK_MEMORY)

    def resetMonitorBuffer(self):
        return self.sendMsg(DATA_ACCESS, DATA_ACC_RESET_MONI_BUF)
   
    def setEngFormat(self, nFADC, wordSize, atwdCount):
        """
        (For engineering format data) specify the readout
        format - that is, number of FADC channels, and the
        wordsize and count of the ATWD chips
           - nFADC     : # of FADC channels to readout [0..255]
           - wordsize  : 4-tuple of word sizes - either 1 or 2
           - atwdCount : these are the 'coded' patterns used
                         as input to DOMApp.
        """
        atwd01 = _atwdMask[wordSize[0]][atwdCount[0]] |\
                 ( _atwdMask[wordSize[1]][atwdCount[1]] << 4 )
        atwd23 = _atwdMask[wordSize[2]][atwdCount[2]] |\
                 ( _atwdMask[wordSize[3]][atwdCount[3]] << 4 )
        self.sendMsg(DATA_ACCESS, DATA_ACC_SET_ENG_FMT,
                     data=pack(">3B", nFADC, atwd01, atwd23))

    def selectATWD(self, atwd):
        self.sendMsg(DOM_SLOW_CONTROL, DSC_SELECT_ATWD, data=pack("B", atwd))
       
    def setMonitoringIntervals(self, hwInt=40000000, cfInt=1200000000):
        self.sendMsg(DATA_ACCESS, DATA_ACC_SET_MONI_IVAL,
                     data=pack(">2I", hwInt, cfInt)
                     )

    def collectPedestals(self, natwd0=100, natwd1=100, nfadc=100):
        self.sendMsg(EXPERIMENT_CONTROL, EXPCONTROL_DO_PEDESTAL_COLLECTION,
                     data=pack(">3I", natwd0, natwd1, nfadc)
                     )

    def getPedestalAverages(self):
        return self.sendMsg(EXPERIMENT_CONTROL, EXPCONTROL_GET_PEDESTAL_AVERAGES)

    def getNumPedestals(self):
        return self.sendMsg(EXPERIMENT_CONTROL, EXPCONTROL_GET_NUM_PEDESTALS)

    def setLC(self, **lc_opts):
        """
        Setup DOM local coincidence:

          mode = 0: no LC required
          mode = 1: LC UP.or.DOWN
          mode = 2: LC UP only
          mode = 3: LC DOWN only

          transmit = 0: no LCtransmit
          transmit = 1: TX DOWN only
          transmit = 2: TX UP only
          transmit = 3: TX UP.and.DOWN (DEFAULT)
         
          type = 0: soft LC
          type = 1: hard LC (DEFAULT)
          type = 2: flabby LC

          source = 0: SPE triggers (DEFAULT)
          source = 1: MPE triggers

          span = <#>: set the LC span length (range 1..4; DEFAULT 1)
          window = (pre, post) : set LC pre/post windows [ns]
                   note that it is supported to send a 4-tuple
                   for testdomapps which expect
                   (up_pre, up_post, dn_pre, dn_post)
          cablelen = (up0, up1, up2, up3, dn0, dn1, dn2, dn3)
        """
        if 'mode' in lc_opts:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LOCAL_COIN_MODE,
                         data=pack("B", lc_opts['mode'])
                         )
        if 'type' in lc_opts:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LC_TYPE,
                         data=pack("B", lc_opts['type'])
                         )
        if 'source' in lc_opts:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LC_SRC,
                         data=pack("B", lc_opts['source'])
                         )
        if 'transmit' in lc_opts:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LC_TX,
                         data=pack("B", lc_opts['transmit'])
                         )
        if 'span' in lc_opts:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LC_SPAN,
                         data=pack("B", lc_opts['span'])
                         )
        if 'window' in lc_opts:
            data = ""
            for x in lc_opts['window']: data += pack(">i", x)
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LOCAL_COIN_WINDOW,
                         data=data
                         )
        if 'cablelen' in lc_opts:
            self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_LC_CABLE_LEN,
                         data=pack(">8H",
                                   lc_opts['cablelen'][0],
                                   lc_opts['cablelen'][1],
                                   lc_opts['cablelen'][2],
                                   lc_opts['cablelen'][3],
                                   lc_opts['cablelen'][4],
                                   lc_opts['cablelen'][5],
                                   lc_opts['cablelen'][6],
                                   lc_opts['cablelen'][7]
                                   ))
           
    def selectMUX(self, mux):
        """
        Select the multiplexer input channel
         - 0 : 20 MHz oscillator output
         - 1 : 40 MHz square wave clock signal
         - 2 : on-board LED current
         - 3 : flasher board current
         - 4 : LC signal (upper)
         - 5 : LC signal (lower)
         - 6 : COMM ADC input
         - 7 : front-end pulser
        """
        self.sendMsg(DOM_SLOW_CONTROL, DSC_MUX_SELECT, data=pack("B", mux))
       
    def writeDAC(self, dac, value):
        """
        Program a single DAC
        See hal.py for DAC symbolic constants
        """
        self.sendMsg(DOM_SLOW_CONTROL, DSC_WRITE_ONE_DAC, data=pack(">BBH", dac, 0, value))
       
    def setScalerDeadtime(self, deadtime):
        """
        Specify the artificial deadtime (in ns, range 100 ... 102400) for the
        SPE / MPE scalers (not supernova scalers)
        """
        self.sendMsg(DOM_SLOW_CONTROL, DSC_SET_SCALER_DEADTIME, data=pack(">I", deadtime))
       
    def accessMemory(self, address, n=1, byte=False, write=False):
        """
        Read (write = FALSE) or write (write = True) DOM memory locations.
        """
        ib = 1
        rw = 0
        if byte: ib = 0
        if write: rw = 1
        return self.sendMsg(
            MESSAGE_HANDLER,
            MSGHAND_ACCESS_MEMORY_CONTENTS,
            data=pack(">bbhi", ib, rw, n, address)
            )

