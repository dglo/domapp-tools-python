#!/bin/env python

import sys
from struct import unpack

def MonitorRecordFactory(buf, domid='????????????', timestamp=0L):
    domClock = 0L
    for i in range(6):
        domClock = (domClock << 8) | unpack('B', buf[i+4])[0]
    (moniLen, moniType) = unpack('>hh', buf[0:4])
    if moniType == 0xC8:
        return HardwareMonitorRecord(domid, timestamp, buf, moniLen, moniType, domClock)
    elif moniType == 0xC9:
        return ConfigMonitorRecord(domid, timestamp, buf, moniLen, moniType, domClock)
    elif moniType == 0xCB:
        return ASCIIMonitorRecord(domid, timestamp, buf, moniLen, moniType, domClock)
    else:
        return MonitorRecord(domid, timestamp, buf, moniLen, moniType, domClock)
    
class MonitorRecord:
    """
    Generic monitor record type - supports the common base information
    contained in all monitor records.
    """
    def __init__(self, domid, timestamp, buf, moniLen, moniType, domClock):
        self.domid = domid
        self.timestamp = timestamp
        self.buf = buf
        self.moniLen = moniLen
        self.moniType = moniType
        self.domClock = domClock
        
    def getDOMClock(self):
        """Retrieve the DOM timestamp."""
        return self.domClock
        
class ASCIIMonitorRecord(MonitorRecord):
    """
    Implements the ASCII type logging monitor record.
    """
    def __init__(self, domid, timestamp, buf, moniLen, moniType, domClock):
        MonitorRecord.__init__(self, domid, timestamp, buf, moniLen, moniType, domClock)
        self.text = self.buf[10:]
        
    def getMessage(self):
        """Retrieve the payload message from the DOM monitor record."""
        return self.text

class ConfigMonitorRecord(MonitorRecord):
    def __init__(self, domid, timestamp, buf, moniLen, moniType, domClock):
        MonitorRecord.__init__(self, domid, timestamp, buf, moniLen, moniType, domClock)

    def __str__(self):
        print len(self.buf)
        return """
    DOM Id .............................. %s
    UT Timestamp ........................ %x
    DOM Timestamp ....................... %x
    Config Version ...................... %d
    Mainboard ID ........................ %8.8X%4.4X
    HV Control ID ....................... %8.8X%8.8X
    FPGA Build ID ....................... %d
    DOM-MB Software Build ID ............ %d
    Message Handler Version ............. %d.%2.2d
    Experiment Control Version .......... %d.%2.2d
    Slow Control Version ................ %d.%2.2d
    Data Access Version ................. %d.%2.2d
    Trigger Configuration ............... %x
    ATWD Readout Info ................... %x
    """ % (
        (self.domid, self.timestamp, self.domClock) +
        unpack('>B3xIH2xIIH2xH8B2xII', self.buf[10:])
        )
    
class HardwareMonitorRecord(MonitorRecord):
    
    def __init__(self, domid, timestamp, buf, moniLen, moniType, domClock):
        MonitorRecord.__init__(self, domid, timestamp, buf, moniLen, moniType, domClock)
        
    def getVoltageSumADC(self):
        """Gets the voltage sum ADC."""
        return unpack('>h', self.buf[12:14])[0]
        
    def get5VMonitor(self):
        """Gets the ADC monitoring the 5V power line."""
        adc5v = unpack('>h', self.buf[14:16])[0]
        return adc5v
        
    def __getattr__(self, name):
        """
        Provide nice getters for the following attributes:
            m.i5v   - 5 V current monitor ADC
            m.i3_3v - 3.3 V current monitor ADC
            m.i2_5v - 2.5 V current monitor ADC
            m.i1_8v - 1.8 V current monitor ADC
            m.i_minus_5v - -5 V current monitor ADC
        """
        if name == 'i5v':
            return unpack('>h', self.buf[18:20])[0]
        elif name == 'i3_3v':
            return unpack('>h', self.buf[20:22])[0]
        elif name == 'i2_5v':
            return unpack('>h', self.buf[22:24])[0]
        elif name == 'i1_8v':
            return unpack('>h', self.buf[24:26])[0]
        elif name == 'i_minus_5v':
            return unpack('>h', self.buf[26:28])[0]
        else:
            raise AttributeError
            
    def getPressure(self):
        """Returns the pressure in kPa."""
        padc = unpack('>h', self.buf[16:18])[0]
        vsum = self.get5VMonitor();
        return (float(padc) / float(vsum) + 0.095) / 0.009 
        
    def getTemperature(self):
        """Returns the temperature in deg C."""
        temp = unpack('>h', self.buf[64:66])[0]
        return temp / 256.0
        
    def getHVSet(self):
        """Returns the HV set point (in volts).""" 
        return unpack('>h', self.buf[60:62])[0] * 0.5
        
    def getHVMonitor(self):
        """Returns the HV readback (in volts)."""
        return unpack('>h', self.buf[62:64])[0] * 0.5
        
    def getSPERate(self):
        """
        Returns the counting rate (Hz) for the SPE trigger disc.
        Note that the scaling factor 10/9 has been taken out:
        that was the right behavior for TestDOMApp but is incorrect
        for DOMApp.
        """
        return unpack('>i', self.buf[66:70])[0]
        
    def getMPERate(self):
        """
        Returns the counting rate (Hz) for the MPE trigger disc.
        Note that the scaling factor 10/9 has been taken out:
        that was the right behavior for TestDOMApp but is incorrect
        for DOMApp.
        """
        return unpack('>i', self.buf[70:74])[0]
        
    def __str__(self):
        return """
        DOM Id ....................... %s
        UT Timestamp ................. %x
        DOM Timestamp ................ %x
        Hardware Record Ver .......... %d
        Voltage Sum ADC .............. %d
        5 V Power Supply ............. %d
        Pressure ..................... %d
        5 V Current Monitor .......... %d
        3.3 V Current Monitor ........ %d
        2.5 V Current Monitor ........ %d
        1.8 V Current Monitor ........ %d
        -5 V Current Monitor ......... %d
        ATWD0 Trigger Bias DAC ....... %d
        ATWD0 Ramp Top DAC ........... %d
        ATWD0 Ramp Rate DAC .......... %d
        ATWD Analog Ref DAC .......... %d
        ATWD1 Trigger Bias DAC ....... %d
        ATWD1 Ramp Top DAC ........... %d
        ATWD1 Ramp Rate DAC .......... %d
        FE Bias Voltage DAC .......... %d
        Multi-PE Discriminator DAC ... %d
        SPE Discriminator DAC ........ %d
        LED Brightness DAC ........... %d
        FADC Reference DAC ........... %d
        Internal Pulser DAC .......... %d
        FE Amp Lower Clamp DAC ....... %d
        FL Ref DAC ................... %d
        MUXer Bias DAC ............... %d
        PMT HV DAC Setting ........... %d
        PMT HV Readback ADC .......... %d
        DOM Mainboard Temperature .... %d
        SPE Scaler ................... %d
        MPE Scaler ................... %d
        """ % (
            (self.domid, self.timestamp, self.domClock) + 
            unpack('>Bx27hii', self.buf[10:])
            )

def readMoniStream(f):
    
    xroot = { }
    
    while 1:
        hdr = f.read(32)
        if len(hdr) == 0: break
        (recl, recid, domid, timestamp) = unpack('>iiq8xq', hdr)
        domid = "%12.12x" % (domid)
        #print recl, recid, domid, timestamp
        buf = f.read(recl - 32)
        moni = MonitorRecordFactory(buf, domid, timestamp)
        if domid not in xroot: 
            xroot[domid] = [ ]
        xroot[domid].append(moni)
        
    return xroot
    
def readMoniStreamDH(f):
    """
    Can digest direct DOMHub output
    """
    
    xroot = { }
    
    while 1:
        hdr = f.read(16)
        if len(hdr) != 16: break
        (recl, recid, domid) = unpack('>iiq', hdr)
        domid = "%12.12x" % (domid)
        #print recl, recid, domid, timestamp
        buf = f.read(recl - 16)
        if domid not in xroot: 
            xroot[domid] = [ ]
        while len(buf) > 0:
            blen, = unpack('>h', buf[0:2])
            moni = MonitorRecordFactory(buf[0:blen], domid, -1L)
            buf  = buf[blen:]
            xroot[domid].append(moni)
        
    return xroot    
