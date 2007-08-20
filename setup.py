#!/usr/bin/env python

# setup.py
# John Jacobsen, NPX Designs, Inc., jacobsen\@npxdesigns.com
# Started: Wed May 30 16:39:14 2007

from distutils.core import setup
from re import sub
import sys, re

def getDomappToolsVersion():
    f = file("domapp-tools-python-version","r")
    version = f.readline()
    version = version.rstrip()
    version = sub('-', '.', version)
    return version

def doSetup(version, pyVersion):
    setup(name="domapp-tools-python-%s" % pyVersion,
          version=version,
          description="Tools for testing domapp and domapp.sbi",
          author="John Jacobsen, NPX Designs, Inc. for UW-Madison",
          author_email="john@mail.npxdesigns.com",
          url="http://www.npxdesigns.com",
          packages=["domapptools"],
          scripts=["domapptest.py", "DOMPrep.py"],
          data_files=[("/usr/local/share", ["domapp-tools-python-version"])]
          )
    
if __name__ == "__main__":
    python = "2.3"
    for arg in sys.argv:
        m = re.search(r'python=python(\d+\.\d+)', arg)
        if m:
            python = m.group(1)
    version = getDomappToolsVersion()
    doSetup(version, python)

