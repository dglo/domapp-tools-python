#!/usr/bin/env python

# UploadDOMs.py
# John Jacobsen, NPX Designs, Inc., john@mail.npxdesigns.com
# Started: Fri Oct 26 18:12:39 2007

import unittest, optparse, re, time, threading, os, os.path, gzip, select, signal, re, md5
from domapptools.dor import *
from domapptools.exc_string import exc_string
from domapptools.domapp import *
from domapptools.MiniDor import *

class Uploader:
    def __init__(self, releaseFile, domHash, md5sum=None, verbose=False, doSkip=False):
        self.card    = {}
        self.pair    = {}
        self.aorb    = {}
        self.doms    = []
        self.doSkip  = doSkip
        self.release = releaseFile
        self.verbose = verbose
        self.md5sum  = md5sum
        for d in domHash.values():
            dom = "%d%d%s" % (d[0],d[1],d[2])
            self.doms.append(dom)
            self.card[dom] = d[0]
            self.pair[dom] = d[1]
            self.aorb[dom] = d[2]

        if self.verbose:
            print "Uploading", releaseFile, "to",
            for d in self.doms: print d,
            print "..."
            
        self.lock    = threading.Lock()
        self.threads = {}

    def warn(self, cwd, m):
        self.lock.acquire()
        print cwd+": "+m
        self.lock.release()

    def log(self, cwd, m):
        if self.verbose: self.warn(cwd, m)
        
    def runThread(self, cwd):
        dor = MiniDor(self.card[cwd],
                      self.pair[cwd],
                      self.aorb[cwd])
        try:
            self.log(cwd, "softboot...")
            dor.softboot()
            self.log(cwd, "open...")
            dor.open()
            self.log(cwd, "check iceboot...")
            ok, txt = dor.isInIceboot2()
            if not ok:
                self.warn(cwd, "%s\nNOT in Iceboot!" % txt)
                self.warn(cwd, "FAIL")
                return
            self.log(cwd, "iset command ...")
            txt = dor.se1("$ffffffff $01000000 $00800000 4 / iset\r\n", ">", 30000)

            if not self.doSkip:
                self.log(cwd, "send buffer...")
                fileSize = os.path.getsize(self.release)
                txt = dor.se1("%d read-bin\r\n" % fileSize, "read-bin\r\n", 30000)
                f = file(self.release)
                segsize  = 4000 # =< 4092
                buf = None
                while True:
                    buf = f.read(segsize)
                    if (not buf) or len(buf) == 0: break
                    # Drain current buffer (should generally go in just try)
                    while len(buf) > 0:
                        select.select([],[dor.fd],[])
                        nw = os.write(dor.fd, buf)
                        buf = buf[nw:]
                        
                # Make sure iceboot still there
                self.log(cwd, "check iceboot again...")
                txt = dor.se1("\r", "> $", 10000)

                # Get location and length (last two items on stack)
                self.log(cwd, "get remote details...")
                txt = dor.se1(".s\r", "\d+ \d+\s+> $", 10000)
                m = re.search('(\d+) (\d+)\s+> $', txt)
                if not m:
                    self.warn(cwd, "Bad stack details '%s'!" % txt)
                    self.warn(cwd, "FAIL")
                    return
                loc, length = m.group(1), m.group(2)

                # Check md5sum
                if self.md5sum:
                    self.log(cwd, "check md5sum...")
                    txt = dor.se1("md5sum type crlf type\r", "md5sum.+?> $", 10000)
                    m = re.search('md5sum.+?\s+(\w+)\s+> $', txt)
                    if not m:
                        self.warn(cwd, "Unexpected md5sum '%s'!" % txt)
                        self.warn(cwd, "FAIL")
                        return
                    if self.md5sum != m.group(1):
                        self.warn(cwd, "MD5SUM ERROR: local '%s' remote '%s'" % (self.md5sum,
                                                                                 m.group(1)))
                        self.warn(cwd, "FAIL")
                        return
                    self.log(cwd, "md5sum %s" % m.group(1))
                
                # gunzip/hex-to-bin command
                self.log(cwd, "gunzip image on remote...")
                txt = dor.se1("%s %s gunzip $01000000 $01000000 hex-to-bin\r" % (loc, length),
                              "hex-to-bin\s+> $", 30000)
                self.log(cwd, "Got %s" % txt)

                # Flash the image.  Here we want to make sure there is no extra output!
                self.log(cwd, "FLASHING IMAGE...")
                txt0 = dor.se1("$01000000 $00400000 install-image\r",
                              "install-image\s+install:.+?are you sure [y/n]?",
                              10000)
                txt1 = dor.se1("y\r", "^y.*> $", 240000)
                m = re.search('write ERRORS detected', txt1, re.S)
                if m:
                    self.warn(cwd, "WARNING: FLASH ERRORS\n"+txt0+txt1)
                m = re.search("chip 0: unlock\.\.\. erase\.\.\.\s+"+
                              "chip 1: unlock\.\.\. erase\.\.\.\s+"+
                              "Programming\.\.\.\s+"+
                              "chip 0: lock\.\.\.\s+"+
                              "chip 1: lock\.\.\.\s+> $", txt1, re.S)
                if not m:
                    self.warn(cwd, "WARNING: unexpected flash write output\n"+txt0+txt1)
                    
            # Check version
            self.log(cwd, "softboot...")
            dor.softboot()
            self.log(cwd, "check version...")
            txt = dor.se1("\r\n", ">", 5000)
            m = re.search('Iceboot.+?build (\d+)\.', txt)
            if not m:
                self.warn(cwd, "WARNING: Build number not found: %s", txt)
            else:
                self.warn(cwd, "DONE (%s)" % m.group(1))
            dor.close()
            
        except KeyboardInterrupt, k:
            self.warn(cwd, "Interrupting...")
            self.warn(cwd, "FAIL")
            return
        except IOError, e:
            self.warn(cwd, "IOError: "+str(e))
            self.warn(cwd, "FAIL")
            return
        except Exception, e:
            self.warn(cwd, exc_string())
            self.warn(cwd, "FAIL")
            return
        
    def runWatcher(self):
        """
        We don't wait to join this thread, so don't put any crucial
        cleanup in here
        """
        i = 1
        while True:
            domList = []
            for dom in self.doms:
                if self.threads[dom].isAlive(): domList.append(dom)
            if not domList: break
            self.lock.acquire()
            if (i % 30) == 0 and self.verbose: print "Waiting on "+" ".join(domList)+"..."
            self.lock.release()
            time.sleep(1)
            i += 1
        
    def go(self):
        for dom in self.doms:
            self.threads[dom] = threading.Thread(target=self.runThread, args=(dom, ))
            self.threads[dom].start()
        self.watchThread = threading.Thread(target=self.runWatcher)
        self.watchThread.start()
        for dom in self.doms:
            try:
                while True:
                    self.threads[dom].join(1)
                    if not self.threads[dom].isAlive(): break
            except KeyboardInterrupt:
                raise SystemExit
            except Exception, e:
                print exc_string()
                raise SystemExit
        
class TestMyStuff(unittest.TestCase):
    def test1(self): self.assertEqual(2+2, 4)

def doTests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMyStuff)
    unittest.TextTestRunner(verbosity=2).run(suite)

def usage(): return """
Usage: UploadDOMs.py release.hex [dom1 dom2 ...]
E.g.   UploadDOMs.py release.hex 00a 01b
       UploadDOMs.py release.hex   (does all DOMs)
"""

class ArgumentException(Exception): pass

def checkArgs(l):
    doms = []
    for arg in l:
        match = re.search('(\d)(\d)(\w)$', arg)
        if (not match) or (len(match.group(3)) != 1): raise ArgumentException(arg)
        doms.append((int(match.group(1)), int(match.group(2)), match.group(3).upper()))
    return doms           

def domsToUse(arglist, dict):
    if len(arglist) == 0: return dict
    ret = {}
    for dom in arglist: # Make sure each DOM is in list
        found = False
        for mbid in dict.keys():
            if dom == dict[mbid]:
                found = True
                ret[mbid] = dict[mbid]
                break
        if not found:
            print "DOM %d%d%s not found in active set!" % (dom[0],dom[1],dom[2])
            raise SystemExit
    return ret

def doGzip(f, verbose):
    base = os.path.basename(f)
    newFile = "/tmp/%s.gz" % base
    if verbose: print "Creating %s..." % newFile
    gz = gzip.GzipFile(newFile, "wb")
    gz.write(file(f).read())
    gz.close()
    return newFile

def getMd5sum(fname):
    """
    Use md5 module to form md5sum
    """
    f = file(fname, "rb")
    m = md5.new()
    while True:
        buf = f.read(8092)
        if not buf: break
        m.update(buf)
    f.close()
    ret = m.hexdigest()
    return ret

def main():
    p = optparse.OptionParser(usage="usage: %prog [options] <releasefile>")
    p.add_option("-s", "--skip-actual-upload", action="store_true", dest="doSkip",
                 help="Skip actual upload and flash step - just check versions")
    p.add_option("-v", "--verbose",            action="store_true", dest="verbose",
                 help="Print more output")
    p.set_defaults(doSkip  = False,
                   verbose = False)
    
    opt, args = p.parse_args()

    releaseFile = args.pop(0)
    if releaseFile == None: print usage(); raise SystemExit
    if not os.path.exists(releaseFile):
        print releaseFile, "doesn't exist!"
        print usage()
        raise SystemExit
    
    try:
        doms = checkArgs(args)
    except ArgumentException, e:
        print usage()
        raise SystemExit
    try:
        dor = Driver()
        dor.enable_blocking(0)
        domDict = dor.get_active_doms()
    except Exception, e:
        print "No driver present? ('%s')" % e
        raise SystemExit
    uploadSet = domsToUse(doms, domDict)
    if len(uploadSet)==0:
        print "No communicating DOMs selected!"
        raise SystemExit

    # Compress image
    tmpFile = None
    try:
        if not opt.doSkip:
            tmpFile = doGzip(releaseFile, opt.verbose)
    except Exception, e:
        print "Couldn't create gzip file corresponding to %s: %s" % (releaseFile, exc_string())
        raise SystemExit

    if tmpFile:
        md5sum = getMd5sum(tmpFile)
        if opt.verbose: print "Local md5sum is %s" % md5sum               
    else:
        md5sum = None

    # Do the upload
    u = Uploader(tmpFile, uploadSet, md5sum, opt.verbose, opt.doSkip)
    u.go()

    # Clean up
    try:
        if not opt.doSkip:
            os.unlink(tmpFile)
    except Exception, e:
        print "Couldn't unlink %s: %s" % (tmpFile, exc_string())

    raise SystemExit
    
if __name__ == "__main__": main()

