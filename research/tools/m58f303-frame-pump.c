/* Verify retained remote presentation independently of Riot. */
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
static void *testPlatform;
static void pump(void *display, int iterations) {
    for (int i=0;i<iterations;++i) {
        send(display,"processPendingEvents"); ((int(*)(void*,void*,void*))objc_msgSend)(testPlatform,sel_registerName("presentRemoteCAFrame:"),0); usleep(25000);
    }
}
extern const void *kIOSurfaceWidth, *kIOSurfaceHeight, *kIOSurfaceBytesPerElement, *kIOSurfaceBytesPerRow;
extern const char kCFTypeDictionaryKeyCallBacks[], kCFTypeDictionaryValueCallBacks[];
extern void *CFNumberCreate(void *, int, const void *);
extern void *CFDictionaryCreate(void *, const void **, const void **, long, const void *, const void *);
extern void CFRelease(const void *);
extern int IOSurfaceLock(void *, unsigned, unsigned *), IOSurfaceUnlock(void *, unsigned, unsigned *);
extern void *IOSurfaceCreate(const void *), *IOSurfaceGetBaseAddress(void *);

int main(void) {
    void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
    send(objc_getClass("NSApplication"),"sharedApplication");
    void *display=send(objc_getClass("NSDisplay"),"currentDisplay");
    Rect rect={{800,300},{100,100}};
    void *window=((void *(*)(void *,void *,Rect,unsigned long,unsigned long,int))objc_msgSend)
        (send(objc_getClass("NSWindow"),"alloc"),sel_registerName("initWithContentRect:styleMask:backing:defer:"),rect,1,2,0);
    ((void (*)(void *,void *,void *))objc_msgSend)(window,sel_registerName("makeKeyAndOrderFront:"),0);
    send(window,"becomeKeyWindow");
    void *platform=send(window,"platformWindow");testPlatform=platform;
    unsigned long xid=((unsigned long (*)(void *,void *))objc_msgSend)(platform,sel_registerName("windowHandle"));
    int numbers[4]={100,122,4,400};
    const void *keys[4]={kIOSurfaceWidth,kIOSurfaceHeight,kIOSurfaceBytesPerElement,kIOSurfaceBytesPerRow};
    const void *values[4];
    for(int i=0;i<4;++i)values[i]=CFNumberCreate(0,3,&numbers[i]);
    void *dict=CFDictionaryCreate(0,keys,values,4,kCFTypeDictionaryKeyCallBacks,kCFTypeDictionaryValueCallBacks);
    void *surface=IOSurfaceCreate(dict);CFRelease(dict);
    for(int i=0;i<4;++i)CFRelease(values[i]);
    unsigned *pixels=IOSurfaceGetBaseAddress(surface);
    IOSurfaceLock(surface,0,0);
    for(int i=0;i<100*122;++i)pixels[i]=0xff113355;
    IOSurfaceUnlock(surface,0,0);
    void *layer=send(objc_getClass("CALayer"),"new");
    ((void(*)(void*,void*,void*))objc_msgSend)(layer,sel_registerName("setContents:"),surface);
    int presented=((int(*)(void*,void*,void*))objc_msgSend)(platform,sel_registerName("presentRemoteCAFrame:"),0);
    printf("FRAME_WINDOW xid=%lu phase=first presented=%d\n",xid,presented);fflush(0);
    usleep(3000000);
    for(int i=0;i<100*122;++i)pixels[i]=0xff775533;
    send(layer,"setContentsChanged");
    ((int(*)(void*,void*,void*))objc_msgSend)(platform,sel_registerName("presentRemoteCAFrame:"),0);
    printf("FRAME_WINDOW xid=%lu phase=updated\n",xid);fflush(0);
    pump(display,120);
    send(layer,"release");CFRelease(surface);
    send(window,"close");send(pool,"drain");
    return 0;
}
