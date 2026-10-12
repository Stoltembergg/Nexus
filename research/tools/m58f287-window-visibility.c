/* Exercise custom cursor pixels and hide-until-motion on a native window. */
typedef struct { double x, y; } Point;
typedef struct { double width, height; } Size;
typedef struct { Point origin; Size size; } Rect;
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern void NSRectFill(Rect);
extern int printf(const char *, ...), fflush(void *), usleep(unsigned);
static void *send(void *object, const char *selector) {
    return ((void *(*)(void *, void *))objc_msgSend)(object, sel_registerName(selector));
}
static void pump(void *display, int iterations) {
    for (int i=0;i<iterations;++i) {
        send(display,"processPendingEvents"); usleep(25000);
    }
}
extern const void *NSWindowDidChangeOcclusionStateNotification;
int main(void) {
    void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
    send(objc_getClass("NSApplication"),"sharedApplication");
    void *display=send(objc_getClass("NSDisplay"),"currentDisplay");
    Rect rect={{800,300},{100,100}};
    void *window=((void *(*)(void *,void *,Rect,unsigned long,unsigned long,int))objc_msgSend)
        (send(objc_getClass("NSWindow"),"alloc"),sel_registerName("initWithContentRect:styleMask:backing:defer:"),rect,1,2,0);
    void *center=send(objc_getClass("NSNotificationCenter"),"defaultCenter");
    __block int notifications=0;
    void (^callback)(void *)=^(void *note){++notifications;};
    void *observer=((void *(*)(void *,void *,void *,void *,void *,void(^)(void *)))objc_msgSend)
        (center,sel_registerName("addObserverForName:object:queue:usingBlock:"),(void *)NSWindowDidChangeOcclusionStateNotification,window,0,callback);
    ((void (*)(void *,void *,void *))objc_msgSend)(window,sel_registerName("orderFront:"),0);
    int first=notifications;
    ((void (*)(void *,void *,void *))objc_msgSend)(window,sel_registerName("orderFront:"),0);
    int repeated=notifications;
    ((void (*)(void *,void *,void *))objc_msgSend)(window,sel_registerName("orderOut:"),0);
    int hidden=notifications;
    ((void (*)(void *,void *,void *))objc_msgSend)(window,sel_registerName("orderFront:"),0);
    int ok=first==1&&repeated==1&&hidden==2&&notifications==3;
    printf("WINDOW_VISIBILITY show=%d repeat=%d hide=%d reshow=%d pass=%d\n",first,repeated,hidden,notifications,ok);
    ((void (*)(void *,void *,void *))objc_msgSend)(center,sel_registerName("removeObserver:"),observer);
    send(window,"close");send(pool,"drain");return ok?0:1;
}
