#!/usr/bin/env python3
"""Exercise production log filtering/formatting with an isolated in-memory sink."""
import os,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parents[1]
source=root/'build/darling-src/src/external/darlingserver'
text=(source/'src/logging.cpp').read_text()
for header in ('server','thread','process'):
 text=text.replace('#include <darlingserver/'+header+'.hpp>','')
# Substitute only the external file/process sink; keep filtering and streams.
text=text[:text.index('void DarlingServer::Log::_log(')]
text+='''
static int emitted=0, formatted=0;
void DarlingServer::Log::_log(Type, std::string message) const {
 if (!message.empty()) ++emitted;
}
struct Item {};
std::ostream& operator<<(std::ostream& out, const Item&) {
 ++formatted; return out << "synthetic";
}
struct Object: DarlingServer::Loggable {
 mutable int calls=0;
 void logToStream(DarlingServer::Log::Stream& out) const override {
  ++calls; out << "object";
 }
};
int main(int argc,char** argv) {
 DarlingServer::Log log("synthetic"); Object object;
 log.debug()<<Item{}<<object<<std::hex<<42<<log.endLog;
 log.info()<<Item{}<<object<<log.endLog;
 log.warning()<<Item{}<<object<<log.endLog;
 log.error()<<Item{}<<object<<log.endLog;
 int expected=std::atoi(argv[1]);
 if(emitted!=expected || formatted!=expected || object.calls!=expected) return 1;
 if(expected==1) {
  formatted=0; object.calls=0;
  for(int i=0;i<100000;i++)log.debug()<<Item{}<<object<<i;
  if(formatted || object.calls || emitted!=1)return 2;
 }
 std::printf("LOG_FILTER expected=%d emitted=%d pass\\n",expected,emitted);
}
'''
with tempfile.TemporaryDirectory(prefix='m320-log-') as folder:
 p=pathlib.Path(folder);(p/'probe.cpp').write_text(text)
 subprocess.run(['c++','-std=c++17','-O2','-I'+str(source/'internal-include'),str(p/'probe.cpp'),'-o',str(p/'probe')],check=True)
 for level,n in [('error',1),('warning',2),('info',3),('debug',4)]:
  subprocess.run([str(p/'probe'),str(n)],env={**os.environ,'DSERVER_LOG_LEVEL':level},check=True)
