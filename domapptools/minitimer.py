import time

# FIXME - fix timer to use datetime once available on pcts
#start    = datetime.datetime.now()
#dtsec    = int(timeoutMsec)/1000
#dtusec   = (int(timeoutMsec)%1000)*1000
# while datetime.datetime.now()-start < datetime.timedelta(seconds=dtsec, microseconds=dtusec):

def hackTime():
    yr, mo, da, hr, mn, sc, junk, junk, junk = time.localtime()
    return da*86400 + hr*3600 + mn*60 + sc

class MiniTimer:
    def __init__(self, timeoutMsec=5000):
        self.start = hackTime()
        self.timeout = timeoutMsec
    def expired(self):
        if hackTime() < self.start: return True # HACK: in rare cases (month boundary), 
                                                # timer will expire early due to wrap.
        return (hackTime()-self.start >= self.timeout/1000)

if __name__=="__main__":
    t = MiniTimer()
    while not t.expired():
        print "waiting..."
        time.sleep(0.1)
