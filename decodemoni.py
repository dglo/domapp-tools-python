#!/usr/bin/env python

# decodemoni.py
#
# Decode and print a .moni monitoring stream output file
#
# John Kelley, jkelley@icecube.wisc.edu
# 3 August 2012
#
#---------------------------------------------------------------

import sys
from optparse import OptionParser
from domapptools.monitoring import *

#---------------------------------------------------------------

usage = "usage: %prog [options] file [file2 ...]"
parser = OptionParser(usage=usage)

parser.add_option("-p", "--payload",
                  dest="payload", action="store_true", default=False,
                  help="Decode moni file with payload envelope (2ndbuild output)")

parser.add_option("-d", "--domhub",
                  dest="hub", action="store_true", default=False,
                  help="Decode moni file from direct DOMHub output")

(options, args) = parser.parse_args()
if len(args) < 1:
    parser.error("must specify at least one input moni file")

if (options.payload and options.hub):
    parser.error("can't specify both payload and hub formats; choose one or none (default is StringHub .moni format)")
    
#---------------------------------------------------------------
for filename in args:
    try:
        f = open(filename, "r")
    except:
        print "Error: couldn't open file %s, skipping" % (filename)
        continue

    type = None
    if options.payload:
        type = MonitorStreamType.PAYLOAD
    elif options.hub:
        type = MonitorStreamType.DIRECT
    else:
        type = MonitorStreamType.STRINGHUB

    xroot = readMoniStream(f, type)        
    if xroot:        
        for dom in xroot.keys():
            for m in xroot[dom]:
                print m
    else:
        print "Error: coudln't parse monitoring stream in file",filename

    f.close()
