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
        self.words   = unpack('<2i', hitbuf[0:8])
        iscompressed = (self.words[0] & 0x80000000) >> 31
        if not iscompressed:
            raise MalformedDeltaCompressedHitBuffer("no compression bit found")
        self.hitsize = self.words[0] & 0x7FF
        self.natwdch = ((self.words[0] & 0x3000) >> 12)+1
        self.trigger = (self.words[0] & 0x7ffe0000) >> 18
        self.atwd_avail = ((self.words[0] & 0x4000) != 0)
        self.atwd_chip  = (self.words[0] & 0x0800) >> 11
        self.fadc_avail = ((self.words[0] & 0x8000) != 0)
        self.lcdown     = (( self.words[0] >> 16) & 0x1 == 1)
        self.lcup       = (( self.words[0] >> 17) & 0x1 == 1)
        if self.trigger & 0x01: self.is_spe    = True
        else:                   self.is_spe    = False
        if self.trigger & 0x02: self.is_mpe    = True
        else:                   self.is_mpe    = False
        if self.trigger & 0x04: self.is_beacon = True
        else:                   self.is_beacon = False

    def __repr__(self):
        lcup = self.lcup and "LCUP" or ""
        lcdn = self.lcdown and "LCDN" or ""
        return """
W0 0x%08x W1 0x%08x %s %s
Hit size = %4d     ATWD avail   = %4d     FADC avail = %4d
A/B      = %4d     ATWD#        = %4d     Trigger word = 0x%04x
"""                         % (self.words[0], self.words[1], lcup, lcdn, self.hitsize,
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


class TestMyStuff(unittest.TestCase):
    def test1(self): self.assertEqual(2+2, 4)

def doTests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMyStuff)
    unittest.TextTestRunner(verbosity=2).run(suite)

def main():
    doTests()
    # Rest of main program goes here - nothing defined yet

if __name__ == "__main__": main()

