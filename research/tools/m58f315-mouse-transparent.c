/* Validate native hit testing when ignoresMouseEvents changes. */
typedef struct { double x, y; } Point;
typedef struct { double width, height; } Size;
typedef struct { Point origin; Size size; } Rect;
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern int printf(const char *, ...), fflush(void *), usleep(unsigned);
static void *send(void *o, const char *s) {
    return ((void *(*)(void *, void *))objc_msgSend)(o, sel_registerName(s));
}
int main(void) {
    void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
    send(objc_getClass("NSApplication"),"sharedApplication");
    Rect rect={{300,300},{100,100}};
    void *w=((void *(*)(void *,void *,Rect,unsigned long,unsigned long,int))objc_msgSend)
      (send(objc_getClass("NSWindow"),"alloc"),sel_registerName("initWithContentRect:styleMask:backing:defer:"),rect,0,2,0);
    ((void (*)(void *,void *,int))objc_msgSend)(w,sel_registerName("setIgnoresMouseEvents:"),1);
    ((void (*)(void *,void *,void *))objc_msgSend)(w,sel_registerName("orderFront:"),0);
    void *p=send(w,"platformWindow");
    unsigned long xid=((unsigned long (*)(void *,void *))objc_msgSend)(p,sel_registerName("windowHandle"));
    printf("MOUSE_SHAPE xid=%lu ignored=1\n",xid);fflush(0);usleep(2000000);
    ((void (*)(void *,void *,int))objc_msgSend)(w,sel_registerName("setIgnoresMouseEvents:"),0);
    printf("MOUSE_SHAPE xid=%lu ignored=0\n",xid);fflush(0);usleep(2000000);
    send(w,"close");send(pool,"drain");return 0;
}
