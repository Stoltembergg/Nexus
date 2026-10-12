/* Simulate a signalled source whose separate Mach wakeup is missing. */
extern void *CFRunLoopGetCurrent(void),*CFRunLoopSourceCreate(void*,long,const void*);
extern const void *kCFRunLoopDefaultMode;
extern void CFRunLoopAddSource(void*,void*,const void*),CFRunLoopRemoveSource(void*,void*,const void*),CFRunLoopSourceSignal(void*),CFRelease(void*);
extern int CFRunLoopRunInMode(const void*,double,int);
extern double CFAbsoluteTimeGetCurrent(void);
extern int pthread_create(unsigned long*,const void*,void*(*)(void*),void*),pthread_join(unsigned long,void**),usleep(unsigned),printf(const char*,...);
static void *source;static int count;
static void perform(void *info){++count;}
static void *signal_source(void *info){usleep(50000);CFRunLoopSourceSignal(source);return 0;}
int main(void){
 struct {long version;void *info,*retain,*release,*description,*equal,*hash,*schedule,*cancel;void(*perform)(void*);} context={0};
 context.perform=perform;void *loop=CFRunLoopGetCurrent();source=CFRunLoopSourceCreate(0,0,&context);CFRunLoopAddSource(loop,source,kCFRunLoopDefaultMode);
 unsigned long worker;pthread_create(&worker,0,signal_source,0);double start=CFAbsoluteTimeGetCurrent();int result;do{result=CFRunLoopRunInMode(kCFRunLoopDefaultMode,1,1);}while(!count&&CFAbsoluteTimeGetCurrent()-start<1.1);double ms=(CFAbsoluteTimeGetCurrent()-start)*1000;
 pthread_join(worker,0);CFRunLoopRemoveSource(loop,source,kCFRunLoopDefaultMode);CFRelease(source);
 int ok=count==1&&ms<250;printf("BOUNDED_RUNLOOP callbacks=%d elapsed_ms=%.1f result=%d pass=%d\n",count,ms,result,ok);return ok?0:1;
}
