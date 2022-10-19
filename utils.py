#!/usr/bin/env python3
from netaddr import *


def dotdec2hex(dotdec):
    """convert dotted decimal to hex"""
    hexlist = []
    for decimal in dotdec.split("."):
        d = int(decimal)
        if d < 0 or d > 255:
            print(dotdec, "is not a valid dotted decimal")
            return None
        h = format(d, "02x")
        hexlist.append(h)
    hexout = ":".join(hexlist)
    return hexout


def hex2dotdec(mac):
    """convert hex to dotted decimal"""
    hexlist = []
    for h in mac.split(":"):
        d = int(h, 16)
        hexlist.append(str(d))
    dotdecout = ".".join(hexlist)
    return dotdecout


def mac_to_colon_separated(mac):
    eui_mac = EUI(mac)
    eui_mac.dialect = mac_unix_expanded
    return str(eui_mac).upper()
