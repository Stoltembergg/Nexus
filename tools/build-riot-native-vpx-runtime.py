#!/usr/bin/env python3
"""Build the guarded native VP9 codec bridge outside the product bundle."""
from pathlib import Path
import shlex,subprocess
root=Path(__file__).resolve().parent.parent
host=root/'build/libriot-native-vpx.so'
libs=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','vpx'],text=True))
subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(root/'tools/riot-native-vpx-host.c'),*libs,'-o',str(host)+'.next'],check=True)
subprocess.run(['clang','-target','x86_64-apple-macosx11.0','-fuse-ld=lld','-dynamiclib','-nostdlib','-isysroot','@DARLING_SDK@','-I'+str(root/'build/darling-src/src/startup/mldr/elfcalls'),'-DRIOT_NATIVE_VPX_HOST="'+str(host)+'"','-O2','-Wall','-Wextra','-Werror',str(root/'tools/riot-native-vpx-bridge.c'),'-lSystem','-Wl,-install_name,@GUEST_HOME@/libRiotNativeVpx.dylib','-o',str(root/'build/libRiotNativeVpx.dylib.next')],check=True)
