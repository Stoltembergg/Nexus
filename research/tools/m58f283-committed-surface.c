/* Verify remote pixels refresh on a transaction without a contents setter. */
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern const void *kIOSurfaceWidth, *kIOSurfaceHeight, *kIOSurfaceBytesPerElement, *kIOSurfaceBytesPerRow;
extern const char kCFTypeDictionaryKeyCallBacks[], kCFTypeDictionaryValueCallBacks[];
extern void *CFNumberCreate(void *, int, const void *);
extern void *CFDictionaryCreate(void *, const void **, const void **, long, const void *, const void *);
extern void CFRelease(const void *);
extern void *IOSurfaceCreate(const void *), *IOSurfaceGetBaseAddress(void *);
extern unsigned getuid(void); extern int getpid(void), open(const char *, int, ...), close(int);
extern long pread(int, void *, unsigned long, long);
extern int snprintf(char *, unsigned long, const char *, ...), printf(const char *, ...);
static void send(void *object, const char *method) {
    ((void (*)(void *, void *))objc_msgSend)(object, sel_registerName(method));
}
int main(void) {
    int numbers[4] = {8, 8, 4, 32};
    const void *keys[4] = {kIOSurfaceWidth,kIOSurfaceHeight,kIOSurfaceBytesPerElement,kIOSurfaceBytesPerRow};
    const void *values[4];
    for (int i=0;i<4;++i) values[i]=CFNumberCreate(0,3,&numbers[i]);
    void *dict=CFDictionaryCreate(0,keys,values,4,kCFTypeDictionaryKeyCallBacks,kCFTypeDictionaryValueCallBacks);
    void *surface=IOSurfaceCreate(dict); CFRelease(dict);
    for (int i=0;i<4;++i) CFRelease(values[i]);
    if (!surface) return 1;
    unsigned char *pixels=IOSurfaceGetBaseAddress(surface);
    for (int i=0;i<256;++i) pixels[i]=17;
    void *layer=((void *(*)(void *,void *))objc_msgSend)(objc_getClass("CALayer"),sel_registerName("new"));
    ((void (*)(void *,void *,void *))objc_msgSend)(layer,sel_registerName("setContents:"),surface);
    char path[128];snprintf(path,sizeof(path),"/dev/shm/darling-ca-frame-%u-%d",getuid(),getpid());
    int fd=open(path,0); if(fd<0)return 1;
    unsigned header[8]; if(pread(fd,header,32,0)!=32)return 1;
    unsigned before=header[1];
    send(objc_getClass("CATransaction"),"begin");
    for (int i=0;i<256;++i) pixels[i]=68;
    send(objc_getClass("CATransaction"),"commit");
    unsigned char pixel=0;pread(fd,header,32,0);pread(fd,&pixel,1,32);close(fd);
    int ok=header[1]==before+2 && pixel==68;
    printf("COMMITTED_SURFACE sequence_delta=%u updated=%d pass=%d\n",header[1]-before,pixel==68,ok);
    send(layer,"release"); CFRelease(surface);
    return ok?0:1;
}
