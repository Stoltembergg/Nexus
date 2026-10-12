/* Exercise sheet attachment state without showing a window. */
typedef struct { double x, y; } Point;
typedef struct { double width, height; } Size;
typedef struct { Point origin; Size size; } Rect;
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern int printf(const char *, ...);
static void *send(void *object, const char *selector) {
    return ((void *(*)(void *, void *))objc_msgSend)(object, sel_registerName(selector));
}
static void *window(void) {
    Rect rect = {{0, 0}, {100, 100}};
    return ((void *(*)(void *, void *, Rect, unsigned long, unsigned long, int))objc_msgSend)(
        send(objc_getClass("NSWindow"), "alloc"),
        sel_registerName("initWithContentRect:styleMask:backing:defer:"), rect, 0, 2, 1);
}
int main(void) {
    send(objc_getClass("NSAutoreleasePool"), "new");
    send(objc_getClass("NSApplication"), "sharedApplication");
    void *parent = window(), *sheet = window();
    int normal = send(sheet, "sheetParent") == 0;
    Rect rect = {{0, 0}, {100, 100}};
    void *context = ((void *(*)(void *, void *, void *, void *, void *, void *, Rect))objc_msgSend)(
        objc_getClass("NSSheetContext"),
        sel_registerName("sheetContextWithSheet:modalDelegate:didEndSelector:contextInfo:frame:"),
        sheet, 0, 0, 0, rect);
    ((void (*)(void *, void *, void *))objc_msgSend)(parent, sel_registerName("_setSheetContext:"), context);
    int attached = send(sheet, "sheetParent") == parent && send(parent, "sheetParent") == 0;
    ((void (*)(void *, void *, void *))objc_msgSend)(parent, sel_registerName("_setSheetContext:"), 0);
    int detached = send(sheet, "sheetParent") == 0;
    printf("SHEET_PARENT normal=%d attached=%d detached=%d\n", normal, attached, detached);
    return !(normal && attached && detached);
}
