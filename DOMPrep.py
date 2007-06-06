#!/usr/bin/env python

# DOMPrep.py
# John Jacobsen, NPX Designs, Inc., jacobsen\@npxdesigns.com
# Started: Thu May 31 19:28:06 2007

import threading, time
from domapptools.dor import *
from domapptools.MiniDor import *
from domapptools.exc_string import exc_string

numInIceboot = 0 # PROTECT WITH LOCK to prevent races (esp. if this gets richer)
counterLock  = threading.Lock()

def prepDom(c,w,d):
    """
    Put a DOM into iceboot.  If it's in configboot, send 'r'.  If it's not, softboot it.
    Keep track of success or failure.
    """
    global numInIceboot
    dom = MiniDor(c,w,d)
    try:
        dom.open()
    except KeyboardInterrupt, k:
        print "(%s%s%s transition to iceboot FAILED - interrupted)" % (c,w,d)
        return
    except Exception, e:
        # if open fails, just softboot it to try to get it back to a good state
        pass
        
    if dom.isInConfigboot() and not dom.configbootToIceboot():
            print "(%s%s%s transition to iceboot FAILED)" % (c,w,d)
    else:
        dom.softboot()
        
    if not dom.isInIceboot():
        print "(%s%s%s transition to iceboot FAILED)" % (c,w,d)
    else: 
        counterLock.acquire() ### ++++++++++++++++++++
        numInIceboot += 1
        counterLock.release() ### --------------------

def main():
    dor = Driver()
    dor.enable_blocking(0)
    alreadyPowered = False
    numPlugged = 0
    numPowered = 0
    
    for card in dor.scan():
        for pair in card.pairs:
            if pair.plugged: numPlugged += 1
            if pair.powered:
                alreadyPowered = True
                numPowered += 1

    if not alreadyPowered:
        print "POWERING ON ALL DOMS"
        dor.onAll()

    threads = {}
    domList = dor.get_communicating_doms()
    numCommunicating = len(domList)
    for dom in domList:
        threads[dom] = threading.Thread(target=prepDom, args=(dom[0],dom[1],dom[2],))
        threads[dom].start()
    for dom in domList:
        try:
            threads[dom].join()
        except KeyboardInterrupt:
            raise SystemExit
        except Exception, e:
            print exc_string()
            raise SystemExit

    print "%d pairs plugged, %d powered;" % (numPlugged, numPowered),
    print "%d DOMs communicating, %d in iceboot" % (numCommunicating, numInIceboot)
    
if __name__ == "__main__": main()

