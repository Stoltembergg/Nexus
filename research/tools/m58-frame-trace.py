#!/usr/bin/env python3
import collections, struct, sys

names = [
    "", "LOADED", "UI_SCHEDULE", "UI_BEGINMAIN", "UI_ACK", "UI_SINKSET",
    "PROXY_SETNEEDS", "PROXY_SUBMIT", "DSP_ATTEMPT", "DSP_BEGINSCHED",
    "DSP_DRAWSWAP", "CC_SCHEDPROC", "CC_REDRAW", "CC_ACK",
    "CC_CALCRENDER", "CC_DIDDRAWALL",
    "BND_SUBMIT", "BND_ENQBEGIN", "BND_FLUSHGRP", "CFR_ACK",
    "CFR_BIND", "CFR_SUBMIT", "CFR_NEEDS",
    "CSI_SETNEEDS", "CSI_DIDNOTPROD", "RCC_SETNEEDS", "RCC_SUBMIT",
    "DSP_DIDFINISH", "STP_DOBEGIN", "STP_DOCOMMIT", "CC_FINISHIMPL",
    "FSMB_ADDSINK", "PI_WILLBEGIN", "PI_DIDNOTPROD", "PI_DEFERMAIN",
    "PI_READYDRAW", "CFR_ONBEGIN", "CFCPROXY_ONBEGIN", "CFCPROXY_ACK",
    "SKIMPL_SWAP", "SKOFF_SWAP", "SKGL_SWAP", "DSP_SWACK",
    "ITS_SWAPIN", "ITS_SWAP", "SKBQ_SWAP", "SKWEB_SWAP",
    "DSRC_TIMER", "DSRC_ISSUE", "BND_GROUPBEGIN", "CFSS_BEGIN",
]
data = open(sys.argv[1], "rb").read()
records = [struct.unpack_from("IIQ", data, off)
           for off in range(0, len(data) - 15, 16)]
counts = collections.Counter((pid, event) for pid, event, _ in records)
for (pid, event), count in sorted(counts.items()):
    values = [v for p, e, v in records if p == pid and e == event]
    print(f"pid={pid} {names[event]} count={count} values="
          + ",".join(hex(v) for v in values[:8]))
