from pathlib import Path
import shlex,subprocess,hashlib,json,urllib.request
r=Path(__file__).resolve().parent.parent; flags={}
root=r/'build/vpx-interop/old'
for name,expected in json.loads((r/'tools/riot-native-vpx-check-sources.json').read_text()).items():
 p=root/name
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
  data=urllib.request.urlopen('https://raw.githubusercontent.com/webmproject/libvpx/v1.12.0/'+name,timeout=30).read()
  if hashlib.sha256(data).hexdigest()!=expected:raise SystemExit('libvpx probe source hash differs: '+name)
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
(root/'vpx_version.h').write_text('#define VERSION_PACKED 0x010c00\n#define VERSION_STRING_NOSP "v1.12.0-probe"\n#define VERSION_EXTRA ""\n')
subprocess.run(['cc','-shared','-fPIC','-O2',str(r/'tools/riot-native-vpx-host.c'),'-lvpx','-o',str(r/'build/vpx-interop/libnative-vpx-test.so')],check=True)
for line in (r/'build/darling-src/build/src/frameworks/CoreVideo/CMakeFiles/CoreVideo.dir/flags.make').read_text().splitlines():
 if line.startswith('C_') and ' = ' in line:
  k,v=line.split(' = ',1);flags[k]=shlex.split(v)
objs=[]
for src in [r/'tools/riot-native-vpx-interop-check.c',r/'build/vpx-interop/old/vpx/src/vpx_codec.c',r/'build/vpx-interop/old/vpx/src/vpx_decoder.c']:
 obj=r/'build/vpx-interop'/ (src.stem+'.o');objs.append(str(obj))
 subprocess.run(['clang',*flags['C_DEFINES'],*flags['C_INCLUDES'],*flags['C_FLAGS'],'-I'+str(r/'build/vpx-interop/old'),'-I'+str(r/'build/darling-src/src/startup/mldr/elfcalls'),'-O2','-c',str(src),'-o',str(obj)],check=True)
subprocess.run(['clang','-target','x86_64-apple-macosx11.0','-fuse-ld=lld','-nostdlib','-isysroot','@DARLING_SDK@',*objs,'-lSystem','-o',str(r/'build/vpx-interop/check')],check=True)

# Generate only owned, uniform-color VP9 media for ABI/callback validation.
for width,height in ((320,180),(1920,1080)):
 fixture=r/f'build/vpx-interop/synthetic-{width}x{height}.ivf'
 if not fixture.exists():
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c=red:s={width}x{height}:r=60:d=1','-c:v','libvpx-vp9','-threads','4','-tile-columns','2','-row-mt','1','-deadline','realtime','-cpu-used','8','-f','ivf','-y',str(fixture)],check=True)

# Owned video/audio clips distinguish decoding, preroll and loop stalls.
long_video=r/'build/vpx-interop/synthetic-long-video.webm'
if not long_video.exists():
 subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=60:duration=60','-c:v','libvpx-vp9','-threads','2','-deadline','realtime','-cpu-used','8','-an',str(long_video)],check=True)
hd_video=r/'build/vpx-interop/synthetic-hd-video.webm'
if not hd_video.exists():
 subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=1280x720:rate=60:duration=30','-c:v','libvpx-vp9','-threads','4','-deadline','realtime','-cpu-used','8','-an',str(hd_video)],check=True)
counter_video=r/'build/vpx-interop/synthetic-counter-video.webm'
if not counter_video.exists():
 subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:size=1280x720:rate=60:duration=30','-f','lavfi','-i',r'nullsrc=size=128x128:rate=60:duration=30,format=gbrp,geq=r=255*mod(N\,2):g=100:b=255*(1-mod(N\,2)),format=yuv420p','-filter_complex','[0:v][1:v]overlay=(W-w)/2:(H-h)/2:shortest=1','-c:v','libvpx-vp9','-threads','2','-deadline','realtime','-cpu-used','8','-crf','20','-b:v','0','-colorspace','smpte170m','-color_primaries','smpte170m','-color_trc','bt709','-color_range','tv','-an',str(counter_video)],check=True)
audio=r/'build/vpx-interop/synthetic-audio.webm'
if not audio.exists():
 subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=60:duration=2','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-c:v','libvpx-vp9','-threads','1','-deadline','realtime','-cpu-used','8','-c:a','libopus','-shortest',str(audio)],check=True)
for name,options in [('synthetic-video-only.webm',['-an']),('synthetic-vorbis.webm',['-c:a','libvorbis'])]:
 fixture=r/'build/vpx-interop'/name
 if not fixture.exists():
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(audio),'-c:v','copy',*options,str(fixture)],check=True)
