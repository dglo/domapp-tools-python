#!/usr/bin/env python

# HubGPS.py
# John Jacobsen, NPX Designs, Inc., john@mail.npxdesigns.com
# Started July 18, 2007

import threading, time
from domapptools.dor import *
from domapptools.MiniDor import *
from domapptools.exc_string import exc_string

threadLock = threading.Lock()
threadResults = {}

# GPS thread:
#   read first n gps's
#   read m more strings
#   make sure data is ok
#   make sure dt == 20M
#   return status

def doCard(driver, card):
    gps = driver.readgps(card)
    global threadResults
    threadLock.acquire()
    print "Card %d GPS: %s" % (card, gps)
    threadResults[card] = "OK"
    threadLock.release()

def main():
    # Get list of active dor cards
    driver = Driver()
    # Fire off threads for each dor card
    threads = {}
    cards = []
    for card in driver.cards:
        cards.append(card.id)
        threads[card.id] = threading.Thread(target=doCard, args=(driver, card.id,))
        threads[card.id].start()
        
    # Wait for threads to return
    for card in driver.cards:
        try:
            threads[card.id].join()
            result = threadResults[card.id]
            print "Got result for card %d: %s" % (card.id, result)
        except KeyboardInterrupt:
            raise SystemExit
        except Exception, e:
            print exc_string()
            raise SystemExit
        
    # Report status for each thread
    # When all threads done, report overall status summary
    
if __name__ == "__main__": main()
