#!/usr/bin/env python

# decodemoni.py
#
# Decode and print a .moni monitoring stream output file
#
# John Kelley, jkelley@icecube.wisc.edu
# 3 August 2012
#

import sys
from domapptools.monitoring import *

if len(sys.argv) < 2:
    print "Usage: %s <.moni file> [.moni file]..." % (sys.argv[0])
    sys.exit(0)
    
for filename in sys.argv[1:]:

    try:
        f = open(filename, "r")
    except:
        print "Error: couldn't open file %s, skipping" % (filename)
        continue
    
    xroot = readMoniStream(f)
    if xroot:        
        for dom in xroot.keys():
            for m in xroot[dom]:
                print m
    else:
        print "Error: coudln't parse monitoring stream in file",filename

    f.close()
