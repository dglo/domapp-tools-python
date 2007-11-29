#!/usr/bin/env python

# EngHit.py
# John Jacobsen, NPX Designs, Inc., john.npxdesigns.com
# Started: Fri Aug 10 16:09:01 CDT 2007

from __future__ import generators
import unittest
from struct import unpack, calcsize
from cStringIO import StringIO
from array import array

def calc_atwd_fmt(fmt):
    """Returns unpack info for ATWDs."""
    dtab = ( 0, ">32b", 0, ">32h", 
             0, ">64b", 0, ">64h",
             0, ">16b", 0, ">16h",
             0, ">128b", 0, ">128h" )
             
    return ( dtab[fmt[0] & 0x0f], 
        dtab[(fmt[0] & 0xf0) >> 4],
        dtab[fmt[1] & 0x0f],
        dtab[(fmt[1] & 0xf0) >> 4] );

class EngHit:
    """Some stuff stolen from hits.py in Kael's PyDOM"""
    def __init__(self, data):
        self.data = data 
        self.trigByte,  = unpack('B', self.data[8:9])
        self.trigSource = self.trigByte & 0x03;
        self.fbRunInProgress = (self.trigByte>>4)&1 and True or False
        self.atwd = [ None, None, None, None ]
        
        io = StringIO(data)
        decotup = unpack(">2H6B6s", io.read(16))

        # Decode the time stamp - 6-bit integer a little tricky
        self.domclk = unpack(">q", "\x00\x00" + decotup[8])[0]
        self.atwd_chip = decotup[2] & 1
        # self.evt_trig_flag = decotup[6]
        # Next decode the FADC samples, if any
        fadcfmt = ">%dH" % decotup[3:4]
        fadclen = calcsize(fadcfmt)
        self.fadc = array('H', list(unpack(fadcfmt, io.read(fadclen))))
        # Next decode the ATWD samples, if any.
        atwdfmt = calc_atwd_fmt(decotup[4:6])
        for ich in range(4):
            if atwdfmt[ich] is not 0:
                atwdlen = calcsize(atwdfmt[ich])
                self.atwd[ich] = array('H',
                                       list(unpack(atwdfmt[ich], io.read(atwdlen)))
                                       )
        
    def __repr__(self):
        atwds = ""
        for a in xrange(0,4):
            atwds += ("ATWD %d: " % a) + str(self.atwd[a]) + "\n"
        return """
%d data bytes; TrigByte 0x%02x TrigSource %d FB-in-prog: %s
%s
""" % (len(self.data), self.trigByte, self.trigSource, self.fbRunInProgress, atwds)

    
class MalformedEngineeringEventBuffer(Exception): pass

class EngHitBuf:
    def __init__(self, hitdata):
        self.hitdata = hitdata
        
    def next(self):
        while self.hitdata:
            if len(self.hitdata) < 8: MalformedEngineeringEventBuffer()
            nb, = unpack('>H', self.hitdata[0:2])
            if nb <= 0: raise MalformedEngineeringEventBuffer()
            yield EngHit(self.hitdata[0:nb])
            self.hitdata = self.hitdata[nb:]

    
