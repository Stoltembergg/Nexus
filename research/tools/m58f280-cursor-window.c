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
int main(void) {
    void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
    send(objc_getClass("NSApplication"),"sharedApplication");
    void *display=send(objc_getClass("NSDisplay"),"currentDisplay");
    Rect rect={{800,300},{100,100}};
    void *window=((void *(*)(void *,void *,Rect,unsigned long,unsigned long,int))objc_msgSend)
        (send(objc_getClass("NSWindow"),"alloc"),sel_registerName("initWithContentRect:styleMask:backing:defer:"),rect,1,2,0);
    ((void (*)(void *,void *,void *))objc_msgSend)(window,sel_registerName("makeKeyAndOrderFront:"),0);
    send(window,"becomeKeyWindow");
    void *platform=send(window,"platformWindow");
    unsigned long xid=((unsigned long (*)(void *,void *))objc_msgSend)(platform,sel_registerName("windowHandle"));
    Size size={32,32};
    void *image=((void *(*)(void *,void *,Size))objc_msgSend)(send(objc_getClass("NSImage"),"alloc"),sel_registerName("initWithSize:"),size);
    send(image,"lockFocus");send(send(objc_getClass("NSColor"),"redColor"),"set");
    Rect fill={{0,0},{32,32}};NSRectFill(fill);send(image,"unlockFocus");
    Point hot={0,0};
    void *cursor=((void *(*)(void *,void *,void *,Point))objc_msgSend)(send(objc_getClass("NSCursor"),"alloc"),sel_registerName("initWithImage:hotSpot:"),image,hot);
    pump(display,4);
    send(cursor,"set");
    printf("CURSOR_WINDOW key=%d xid=%lu phase=custom\n",send(send(objc_getClass("NSApplication"),"sharedApplication"),"keyWindow")==window,xid);
    printf("CURSOR_WINDOW xid=%lu phase=custom\n",xid);fflush(0);
    pump(display,80);
    ((void (*)(void *,void *,int))objc_msgSend)(objc_getClass("NSCursor"),sel_registerName("setHiddenUntilMouseMoves:"),1);
    printf("CURSOR_WINDOW xid=%lu phase=hidden\n",xid);fflush(0);
    pump(display,120);
    ((void (*)(void *,void *,int))objc_msgSend)(objc_getClass("NSCursor"),sel_registerName("setHiddenUntilMouseMoves:"),0);
    printf("CURSOR_WINDOW phase=done\n");fflush(0);
    send(cursor,"release");send(image,"release");send(window,"close");send(pool,"drain");
    return 0;
}
