/* AppKit's blocking input wait must keep 60Hz timers running. */
typedef struct {double x,y;} Point;
extern void *objc_getClass(const char *),*sel_registerName(const char *),*objc_allocateClassPair(void*,const char*,unsigned long);
extern int class_addMethod(void*,void*,void*,const char*);extern void objc_registerClassPair(void*),objc_msgSend(void);
extern void *NSDefaultRunLoopMode;extern int printf(const char*,...);
static void *send(void *o,const char*s){return ((void*(*)(void*,void*))objc_msgSend)(o,sel_registerName(s));}
static double now(void){return ((double(*)(void*,void*))objc_msgSend)(objc_getClass("NSDate"),sel_registerName("timeIntervalSinceReferenceDate"));}
static unsigned ticks;static double last,gap;
extern double CFAbsoluteTimeGetCurrent(void);
extern void *CFRunLoopGetCurrent(void), *CFRunLoopTimerCreate(void*,double,double,unsigned long,long,void(*)(void*,void*),void*);
extern void CFRunLoopAddTimer(void*,void*,void*),CFRunLoopTimerInvalidate(void*),CFRelease(void*);
extern void *kCFRunLoopDefaultMode;
static void tick(void*t,void*i){double n=now();if(last&&n-last>gap)gap=n-last;last=n;ticks++;}
int main(void){
 void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
 send(objc_getClass("NSApplication"),"sharedApplication");
 void *display=send(objc_getClass("NSDisplay"),"currentDisplay");
 void *timer=CFRunLoopTimerCreate(0,CFAbsoluteTimeGetCurrent()+1.0/60,1.0/60,0,0,tick,0);
 CFRunLoopAddTimer(CFRunLoopGetCurrent(),timer,kCFRunLoopDefaultMode);
 double start=now();void *deadline=((void*(*)(void*,void*,double))objc_msgSend)(objc_getClass("NSDate"),sel_registerName("dateWithTimeIntervalSinceNow:"),2.1);
 while(now()-start<2.1)((void*(*)(void*,void*,unsigned long,void*,void*,int))objc_msgSend)(display,sel_registerName("nextEventMatchingMask:untilDate:inMode:dequeue:"),~0ul,deadline,NSDefaultRunLoopMode,1);
 CFRunLoopTimerInvalidate(timer);CFRelease(timer);double elapsed=now()-start;
 printf("TIMER_DEADLINE ticks=%u elapsed=%.3f hz=%.1f max_gap_ms=%.1f pass=%d\n",ticks,elapsed,ticks/elapsed,gap*1000,ticks>=110&&gap<.05);
 send(pool,"drain");return ticks>=110&&gap<.05?0:1;
}
