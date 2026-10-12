/* A self-signalling ready source must not pay an idle delay per callback. */
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern void *CFRunLoopGetCurrent(void);
extern const void *kCFRunLoopDefaultMode,*NSDefaultRunLoopMode;
extern void *CFRunLoopSourceCreate(void *,long,const void *);
extern void CFRunLoopAddSource(void *,void *,const void *),CFRunLoopRemoveSource(void *,void *,const void *);
extern void CFRunLoopSourceSignal(void *),CFRunLoopWakeUp(void *),CFRelease(const void *);
extern int printf(const char *,...);
static void *source,*loop;static int count;
static void perform(void *info){if(++count<500)CFRunLoopSourceSignal(source);CFRunLoopWakeUp(loop);}
static void *send(void *o,const char *s){return ((void*(*)(void*,void*))objc_msgSend)(o,sel_registerName(s));}
int main(void){
 void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
 send(objc_getClass("NSApplication"),"sharedApplication");
 void *display=send(objc_getClass("NSDisplay"),"currentDisplay");
 struct {long version;void *info,*retain,*release,*description,*equal,*hash,*schedule,*cancel;void(*perform)(void*);} context={0};
 context.perform=perform;loop=CFRunLoopGetCurrent();source=CFRunLoopSourceCreate(0,0,&context);
 CFRunLoopAddSource(loop,source,kCFRunLoopDefaultMode);CFRunLoopSourceSignal(source);
 void *deadline=((void*(*)(void*,void*,double))objc_msgSend)(objc_getClass("NSDate"),sel_registerName("dateWithTimeIntervalSinceNow:"),.25);
 void *mode=(void*)NSDefaultRunLoopMode;
 ((void*(*)(void*,void*,unsigned long,void*,void*,int))objc_msgSend)(display,sel_registerName("nextEventMatchingMask:untilDate:inMode:dequeue:"),~0ul,deadline,mode,1);
 CFRunLoopRemoveSource(loop,source,kCFRunLoopDefaultMode);CFRelease(source);
 printf("RUNLOOP_DRAIN callbacks=%d minimum=100 pass=%d\n",count,count>=100);
 send(pool,"drain");return count>=100?0:1;
}
