#!/usr/bin/env python

"""
DOR Driver interface class

$Id: dor.py,v 1.20 2006/01/02 20:16:35 kael Exp $
"""

import os, sys
import string, re
# import ibidaq as daq

class PairNotPlugged(Exception):
    def __init__(self, card, pair):
        self.strerror = "Card %d pair %d is not plugged." % (card, pair)
    def __str__(self):
        return self.strerror

class CardInfo:
    """A class/struct to hold information about a DOR card.
    Contains the following (public) fields:
        .id      The numeric card ID (set via turnswitch on card) - 0-7.
        .pairs   A list of wire pairs attached to this card
        .fpga    The FPGA version
    """
    def __init__(self, id):
        self.id    = id
        self.pairs = [ ]
        self.fpga  = None
   
    def __int__(self):
        return self.id

    def __str__(self):
        s = "card:%d fpga:%s\n" % (self.id, self.fpga)
        s += string.join(["  -- " + str(p) for p in self.pairs], "\n")
        return s

    def __getitem__(self, key):
        for p in self.pairs:
            if p.id == key:
                return p
        return None   
   
class PairInfo:
    """Informational wire pair struct that contains the fields:
        .id        the pair ID (0 - 4)
        .plugged   =1 if the 1-6 jumper is detected
        .powered   =1 if the driver thinks there's power on this pair
    """
    def __init__(self, id):
        self.id      = id
        self.plugged = 0
        self.powered = 0

    def __int__(self):
        return self.id

    def __str__(self):
        return "pair:%d plug:%d pwr:%d" % (self.id, self.plugged, self.powered)

class DOMInfo:
    """
    Contains data from the /proc/driver/domhub/cardX/pairY/domZ proc tree
    """
   
def makedev(card, pair, dom):
    return "/dev/dhc%dw%dd%s" % (card, pair, dom.upper())

class Driver:
    """Main driver interface."""
    def __init__(self, root='/proc/driver/domhub'):
        self.root = root
        f = file(os.path.join(self.root, "revision"))
        revstr = f.read()
        grp = re.search('^(\S+).+?\$\Revision:\s*(\S+)\s*\$', revstr)
        if grp == None:
            self.version = None
            self.release = None
        else:
            self.release = grp.group(1)
            self.version = grp.group(2)
        self.scan()

    def __getitem__(self, key):
	for c in self.cards:
	    if c.id == key:
		return c
	return None

    def _dispatch(self, method, params):
        """Hack around Linux python bug"""
        return apply(getattr(self,method), params)

    def scan(self):
        """Discover the hierarchy of cards and wire pairs."""
        self.cards = [ ]
        self.doms  = { }
        cre = re.compile("card([0-9]+)")
        pre = re.compile("pair([0-9]+)")
        cards = filter(cre.match, os.listdir(self.root))
        for c in cards:
            pairs = filter(pre.match, os.listdir(os.path.join(self.root, c)))
            ci = CardInfo(int(cre.match(c).group(1)))
            self.cards.append(ci)
            f = file(os.path.join(self.path(ci.id), "fpga"))
            while 1:
                s = f.readline()
                if s == "":
                    break
                if s[0:4] == 'FREV':
                    ci.fpga = s[11:14] + chr(int(s[14:16], 16))
            for p in pairs:
                pi = PairInfo(int(pre.match(p).group(1)))
                f = file(os.path.join(self.path(ci, pi), "is-plugged"))
                try:
                    f.read().index("not")
                    pi.plugged = 0
                except:
                    pi.plugged = 1

                f = file(os.path.join(self.path(ci, pi), "pwr"))
                try:
                    f.read().index("off")
                    pi.powered = 0
                except:
                    pi.powered = 1
                ci.pairs.append(pi)
        return self.cards

    def path(self, *args):
        """Form path to (card, pair, dom)."""
        path = self.root
        if len(args) > 0:
            card = args[0]
            path = os.path.join(path, "card%d" % (card))
        if len(args) > 1:
            pair = args[1]
            path = os.path.join(path, "pair%d" % (pair))
        if len(args) > 2:
            dom = args[2]
            if dom == 'a':
                dom = 'A'
            elif dom == 'b':
                dom = 'B'
            path = os.path.join(path, "dom%s" % (dom))
        return path
           
    def on(self, card, pair):
        """Turn on specified (card, pair)."""
        f = file(os.path.join(self.path(card, pair), "pwr"), "w")       
        f.write("on\n")
        f.close()
        return self.scan()
       
    def onAll(self):
        """Turn all channels on."""
        f = file(os.path.join(self.root, "pwrall"), "w")
        f.write("on\n")
        f.close()
        return self.scan()
       
    def offAll(self):
        """Turns all channels off."""
        f = file(os.path.join(self.root, "pwrall"), "w")
        f.write("off\n")
        f.close()
        return self.scan()
       
    def off(self, card, pair):
        """Turn off specified (card, pair)."""
        f = file(os.path.join(self.path(card, pair), "pwr"), "w")
        f.write("off\n")
        f.close()
        return self.scan()

    def softboot(self, domId):
        """Softboot a DOM"""
        if len(self.doms == 0):
            self.discover_doms()
        card, pair, dom = self.doms[domId]
        f = file(os.path.join(self.path(card, pair, dom), "softboot"))
        f.write("reset\n")
        f.close()
        return self.scan()
   
    def get_dom_id(self, card, pair, dom):
        f = file(os.path.join(self.path(card, pair, dom), "id"))
        s = f.read()
        # print "get_dom_id(): ", s
        m = re.search("([0-9a-f]{12})", s)
        if m: return m.group(1)
        return None

    def get_current(self, card, pair):
        f = file(os.path.join(self.path(card, pair), "current"))
        m = re.compile(".+ current is (\d+) mA").match(f.read())
        if m is None: return -1
        return int(m.group(1))
           
    def print_dom_table(self, out=sys.stdout):
        """Print out a formatted table of the DOMs"""
        print >>out, "CARD PAIR DOM Driver-File         DOMId"
        for (domid, loc) in self.doms.items():
            print >>out, " %2.2d   %2.2d   %s /dev/dhc%dw%dd%s %s" % (
                loc[0], loc[1], loc[2], loc[0], loc[1], loc[2], domid
                )

    def discover_doms(self):
        """Search the /proc/driver tree for DOMs and return
        a hashtable with the DOM IDs as keys and (card, pair, dom)
        tuples as the values."""
        self.doms = { }
        for c in self.cards:
            for p in c.pairs:
                if p.plugged == 1 and p.powered == 1:
                    for d in ('A', 'B'):
                        f = file(os.path.join(self.path(c, p, d),
                                              "is-communicating"), "r")
                        try:
                            f.read().index("not")
                        except ValueError:
                            domid = self.get_dom_id(c, p, d)
                            if domid:
                                if long(domid, 16) == 0:
                                    # In configboot - put into IceBoot
                                    devfile = makedev(int(c), int(p), d)
                                    dev = file(devfile, "w")
                                    dev.write("r\r\n")
                                    dev.close()
                                    domid = self.get_dom_id(c, p, d)
                                self.doms[domid] = (int(c), int(p), d)
        return self.doms

    def driver_version(self):
        """Get the version of the DOR driver as reported by the procfile."""
        return self.version

    def fpga_version(self, card):
        """Get the FPGA version running on the DOR card."""
        return self.cards[card].fpga

    def enable_blocking(self, state):
        """disable blocking on the domhub"""
        f = file(os.path.join(self.root, 'blocking'), 'w')
        f.write(str(state) + "\n")
        f.close()

    def go_to_iceboot(self):
        """Put all the DOMs into IceBoot mode"""
        for c in self.cards:
            for p in c.pairs:
                if p.plugged == 1 and p.powered == 1:
                    for d in ('A', 'B'):
                        f = file(os.path.join(self.path(c, p, d),
                                              'is-communicating'), 'r')
                        try:
                            f.read().index('not')
                        except ValueError:
                            devfile = makedev(int(c), int(p), d)
                            dev = file(devfile, 'w')
                            dev.write("r\r\n")
                            dev.close()
        self.scan()

    def get_active_doms(self):
        """list all active DOMs"""
        for c in self.cards:
            for p in c.pairs:
                if p.plugged == 1 and p.powered == 1:
                    for d in ('A', 'B'):
                        domid = self.get_dom_id(c, p, d)
                        if domid:
                            self.doms[domid] = (int(c), int(p), d)
        return self.doms

class Power:
    """
    This is an old interface - users are strongly discouraged
    from using it.  Please use the Driver class.
    """
    def __init__(self, card, pair):
        """Constructor for a particular card and pair."""
        self.ptop = "%s/card%d/pair%d" % (_DRIVER_BASE, card, pair)
        self.fpwr = file(self.ptop + "/pwr", "w")
        self.card = card
        self.pair = pair
   
    def on(self):
        """Turn on power to a twisted pair and check DOM status."""
        # First, check that the driver thinks it's a plugged pair
        fpq = file(self.ptop + "/is-plugged")
        s = fpq.readline()
        fpq.close()
        try:
            s.index("not")
            raise PairNotPlugged(self.card, self.pair)
        except ValueError:
            pass
        self.fpwr.write("on\n")
        self.fpwr.flush()
       
        # Now check for DOM alive status and return
        stat = [ ]
        for dom in ('A', 'B'):
            fcq = file(self.ptop + "/dom" + dom + "/is-communicating", "r")
            s = fcq.readline()
            fcq.close()
            try:
                s.index("NOT")
            except ValueError:
                stat.append(dom)
        return stat
       
    def off(self):
        """Turn off power to a twisted pair."""
        self.fpwr.write("off\n")
        self.fpwr.flush()


#Kael Hanson
#University of Wisconsin - Madison
#222 West Washington Ave
#Suite 500
#Madison, WI 53703
#Tel: (608) 890-0540
#kael.hanson@gmail.com


