#define _GNU_SOURCE
#include <sched.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <dlfcn.h>
#include <time.h>
#include <stdio.h>
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec*1e-9; }
int main(void) {
 cpu_set_t original,one; if(sched_getaffinity(0,sizeof original,&original))return 1;
 int cpu=sched_getcpu(); CPU_ZERO(&one);CPU_SET(cpu,&one);if(sched_setaffinity(0,sizeof one,&one))return 2;
 void* handle=dlopen("linux-vdso.so.1",RTLD_NOW);int (*fast)(unsigned*,unsigned*,void*)=handle?dlvsym(handle,"__vdso_getcpu","LINUX_2.6"):0;
 if(!fast)return 3;
 unsigned value=0; int checked=0;
 for(int candidate=0;candidate<CPU_SETSIZE;candidate++){
  if(!CPU_ISSET(candidate,&original))continue;
  CPU_ZERO(&one);CPU_SET(candidate,&one);if(sched_setaffinity(0,sizeof one,&one))return 2;
  for(int i=0;i<1000;i++){if(fast(&value,0,0)||value!=(unsigned)candidate)return 4;if(syscall(SYS_getcpu,&value,0,0)||value!=(unsigned)candidate)return 5;}
  checked++;
 }
 CPU_ZERO(&one);CPU_SET(cpu,&one);if(sched_setaffinity(0,sizeof one,&one))return 2;
 printf("CHECK: migrated across %d allowed CPUs, CPU IDs agree\n",checked);
 const int n=1000000;
 for(int pass=0;pass<4;pass++){
  double start=now();for(int i=0;i<n;i++){int r=pass%2?fast(&value,0,0):syscall(SYS_getcpu,&value,0,0);if(r)return 6;}
  printf("%s %.1f ns/call\n",pass%2?"vDSO":"syscall",(now()-start)*1e9/n);
 }
 if(sched_setaffinity(0,sizeof original,&original))return 7;
 puts("PASS: CPU IDs agree while pinned; only this diagnostic's affinity changed");return 0;
}
