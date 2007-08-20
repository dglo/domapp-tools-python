#!/usr/bin/env python

# EngHit.py
# John Jacobsen, NPX Designs, Inc., john.npxdesigns.com
# Started: Fri Aug 10 16:09:01 CDT 2007

from __future__ import generators
import unittest
from struct import unpack

class EngHit:
    def __init__(self, data):
        self.data = data
        self.trigType, = unpack('B', self.data[8:9])

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

    
