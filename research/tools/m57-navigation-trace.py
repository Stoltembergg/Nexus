#!/usr/bin/env python3
import collections,struct,sys
names=['','LOADED','START','START_EXIT','DID_START','DID_START_EXIT','BEGIN',
       'COMMIT','READY_TO_COMMIT','STUB_DISPATCH']
d=open(sys.argv[1],'rb').read(); rs=[struct.unpack_from('IIQ',d,o) for o in range(0,len(d)-15,16)]
for (p,e),n in sorted(collections.Counter((p,e) for p,e,_ in rs).items()):
 print(f'pid={p} {names[e]} count={n}')
