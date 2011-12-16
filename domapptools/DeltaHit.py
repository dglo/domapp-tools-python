#!/usr/bin/env python

# DeltaHit.py
# John Jacobsen, NPX Designs, Inc., john.npxdesigns.com
# Started: Fri Jun  8 17:37:58 2007

from __future__ import generators
import unittest
from struct import unpack

class MalformedDeltaCompressedHitBuffer(Exception): pass

class DeltaHit:
    def __init__(self, hitbuf):
        self.words = unpack('<2I', hitbuf[0:8])
        iscompressed = (self.words[0] & 0x80000000L) >> 31 # Use L constant to suppress maxint warning
        if not iscompressed:
            raise MalformedDeltaCompressedHitBuffer("no compression bit found")
        self.isMinbias  = (self.words[0] & 0x40000000L) >> 30
        self.hitsize    = self.words[0] & 0x7FF
        self.natwdch    = ((self.words[0] & 0x3000) >> 12)+1
        self.trigger    = (self.words[0] & 0x7ffe0000L) >> 18
        self.atwd_avail = ((self.words[0] & 0x4000) != 0)
        self.atwd_chip  = (self.words[0] & 0x0800) >> 11
        self.fadc_avail = ((self.words[0] & 0x8000) != 0)
        self.lcdown     = (( self.words[0] >> 16) & 0x1 == 1)
        self.lcup       = (( self.words[0] >> 17) & 0x1 == 1)
        self.is_spe = self.trigger & 0x01
        self.is_mpe = self.trigger & 0x02
        self.is_beacon = self.trigger & 0x04
        self.hitbytes = hitbuf[16:]

    def __repr__(self):
        lcup = self.lcup and "LCUP" or ""
        lcdn = self.lcdown and "LCDN" or ""
        return ("W0 0x%08x W1 0x%08x %s %s  Hit-size=%4d  "
               "ATWD-avail=%s  FADC-avail=%s  A/B=%d  "
               "#ATWD=%d  trigword=0x%04x  rest=%d %s" %
                (self.words[0], self.words[1], lcup, lcdn, self.hitsize,
                 self.atwd_avail and "Y" or "n",
                 self.fadc_avail and "Y" or "n", self.atwd_chip,
                 self.natwdch, self.trigger, len(self.hitbytes), [ord(b) for b in self.hitbytes]))


class DeltaHitBuf:
    def __init__(self, hitdata):
        if len(hitdata) < 8:
            raise MalformedDeltaCompressedHitBuffer()
        junk, nb   = unpack('>HH', hitdata[0:4])
        junk, tmsb = unpack('>HH', hitdata[4:8])
        nb -= 8
        if nb <= 0:
            raise MalformedDeltaCompressedHitBuffer()
        self.payload = hitdata[8:]
        
    def next(self):
        rest = self.payload
        while(len(rest) > 8):
            words = unpack('<2i', rest[0:8])
            hitsize = words[0] & 0x7FF
            yield DeltaHit(rest[0:hitsize])
            rest = rest[hitsize:]
