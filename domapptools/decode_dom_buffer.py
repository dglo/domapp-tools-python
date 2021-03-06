#!/usr/bin/env python

"""
decode_dom_buffer.py
John Jacobsen, NPX Designs, Inc., john@mail.npxdesigns.com
Started: Mon Nov 16 14:36:41 2009

Function to decode raw buffer data from DOM, for softboot/restart testing
"""

from re import findall

# Test data, from :
#    > 0 100 0 ?DO $80000000 i 4 * + @ . drop LOOP
BUF = """
16384
20480
8227
1701005600
1953460066
2053187616
1869770797
1646274916
1684826485
926102560
774778414
658734
73732
540936717
16384
20480
4096
8194
2573
73730
8254
69632
139266
2573
204802
8254
135168
270338
2573
335874
8254
200704
401409
108
266240
466945
115
331776
532482
2573
598069
761670957
539831666
538980896
538976288
540024864
807411744
874520608
892811317
2016419890
808464692
808464432
1701013792
1953460066
10
663605
761671013
539831597
538980896
538976288
540090400
824188960
538976288
859125046
2016419894
925905204
808464432
1954047264
1937010277
10
729143
757935405
539831666
538980896
538976288
540155936
840966176
538976288
842346547
2016419889
942682420
808464432
1734965024
778398823
686695
794683
757935405
539831666
538980896
538976288
540221472
857743392
538976288
875901749
2016419892
942682420
808466487
1936028704
1836016756
779120737
"""


def printable_byte(b):
    if b > 31 and b < 127:
        return chr(b)
    else:
        return "[%0X]" % b
    

def decode_dom_buffer(buf):
    """
    >>> b = decode_dom_buffer(BUF)
    >>> assert('Iceboot (az-prod) build 437' in b)
    """
    s = ""
    for n in [int(s_) for s_ in findall(r'(?m)^(\d+)\s*$', buf)]:
        for i in range(4):
            byte = (n >> i*8) & 0xFF
            s += printable_byte(byte)
    return s


def printable_string(txt):
    """
    >>> printable_string("")
    ''
    >>> printable_string("AAA")
    'AAA'
    >>> printable_string("AA\001A\177")
    'AA[1]A[7F]'
    """
    ret = ""
    for c in txt:
        ret += printable_byte(ord(c))
    return ret


if __name__ == "__main__":
    import doctest
    doctest.testmod()

