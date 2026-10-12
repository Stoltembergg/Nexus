/* Validate deferred phase order, nesting, and reentrant registration. */
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern const void *kCFRunLoopDefaultMode;
extern int CFRunLoopRunInMode(const void *, double, unsigned char);
extern int printf(const char *, ...);
extern unsigned alarm(unsigned);
static int order[8], count, returned, inlineCall, depth, maxDepth;
static void append(int value) {
    ++depth; if (depth > maxDepth) maxDepth = depth;
    if (!returned) inlineCall = 1;
    order[count++] = value;
    --depth;
}
static void send(void *cls, const char *name) {
    ((void (*)(void *, void *))objc_msgSend)(cls, sel_registerName(name));
}
static void add(void *cls, void (^block)(void), int phase) {
    ((void (*)(void *, void *, void (^)(void), int))objc_msgSend)
        (cls, sel_registerName("addCommitHandler:forPhase:"), block, phase);
}
int main(void) {
    alarm(10);
    void *pool = objc_getClass("NSAutoreleasePool");
    pool = ((void *(*)(void *, void *))objc_msgSend)(pool, sel_registerName("new"));
    void *cls = objc_getClass("CATransaction");
    ((void(*)(void*,void*,void(^)(void)))objc_msgSend)(cls,sel_registerName("setCompletionBlock:"),^{append(0);});
    send(cls,"flush");returned=1;CFRunLoopRunInMode(kCFRunLoopDefaultMode,.02,0);
    int implicitFlushed=count==1;
    send(cls,"begin");
    ((void(*)(void*,void*,void(^)(void)))objc_msgSend)(cls,sel_registerName("setCompletionBlock:"),^{append(1);});
    send(cls,"flush");CFRunLoopRunInMode(kCFRunLoopDefaultMode,.02,0);
    int explicitProtected=count==1;
    send(cls,"commit");CFRunLoopRunInMode(kCFRunLoopDefaultMode,.02,0);
    ((void(*)(void*,void*,void(^)(void)))objc_msgSend)(cls,sel_registerName("setCompletionBlock:"),^{append(2);});
    send(cls,"begin");
    ((void(*)(void*,void*,void(^)(void)))objc_msgSend)(cls,sel_registerName("setCompletionBlock:"),^{append(3);});
    CFRunLoopRunInMode(kCFRunLoopDefaultMode,.02,0);
    int nestingProtected=count==2;
    send(cls,"commit");CFRunLoopRunInMode(kCFRunLoopDefaultMode,.05,0);
    int ok=implicitFlushed&&explicitProtected&&nestingProtected&&count==4&&order[0]==0&&order[1]==1&&order[2]==3&&order[3]==2&&!inlineCall;
    printf("CA_FLUSH implicit=%d explicit_protected=%d nesting_protected=%d count=%d order=%d%d%d%d pass=%d\n",implicitFlushed,explicitProtected,nestingProtected,count,order[0],order[1],order[2],order[3],ok);
    send(pool, "drain");
    return ok ? 0 : 1;
}
