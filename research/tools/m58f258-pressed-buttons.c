/* Query real global mouse state; accepts the expected AppKit bitmask. */
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern unsigned long strtoul(const char *,char **,int);
extern int printf(const char *,...);
int main(int argc,char **argv) {
 ((void *(*)(void *,void *))objc_msgSend)(objc_getClass("NSApplication"),sel_registerName("sharedApplication"));
 unsigned long actual=((unsigned long (*)(void *,void *))objc_msgSend)(objc_getClass("NSEvent"),sel_registerName("pressedMouseButtons"));
 unsigned long expected=argc>1?strtoul(argv[1],0,10):0;
 printf("PRESSED_BUTTONS actual=%lu expected=%lu\n",actual,expected);
 return actual!=expected;
}
