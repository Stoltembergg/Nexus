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
    send(cls, "begin"); send(cls, "begin");
    add(cls, ^{ append(1); }, 1);
    add(cls, ^{ append(0); }, 0);
    add(cls, ^{
        append(2); ++depth;
        add(cls, ^{ append(3); }, 0);
        send(cls, "commit");
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.005, 0);
        --depth;
    }, 2);
    send(cls, "commit");
    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, 0);
    int nestedDeferred = count == 0;
    send(cls, "commit"); returned = 1;
    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, 0);
    int ok = nestedDeferred && count == 4 && !inlineCall && maxDepth == 1;
    for (int i = 0; i < 4; ++i) ok = ok && order[i] == i;
    printf("CA_COMMIT nested=%d count=%d order=%d%d%d%d inline=%d depth=%d pass=%d\n",
        nestedDeferred, count, order[0], order[1], order[2], order[3], inlineCall, maxDepth, ok);
    send(pool, "drain");
    return ok ? 0 : 1;
}
