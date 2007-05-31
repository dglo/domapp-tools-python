#!/usr/bin/env python

# setup.py
# John Jacobsen, NPX Designs, Inc., jacobsen\@npxdesigns.com
# Started: Wed May 30 16:39:14 2007

from distutils.core import setup
from re import sub

def getDomappToolsVersion():
    f = file("VERSION","r")
    version = f.readline()
    version = version.rstrip()
    version = sub('-', '.', version)
    return version

version = getDomappToolsVersion()

setup(name="domapp-tools-python",
      version=version,
      description="Tools for testing domapp and domapp.sbi",
      author="John Jacobsen, NPX Designs, Inc. for UW-Madison",
      author_email="john@mail.npxdesigns.com",
      url="http://www.npxdesigns.com",
      packages=["domapptools"],
      )
