extern void *objc_getClass(const char *),*sel_registerName(const char *);
extern void objc_msgSend(void);
extern void *CFStringCreateWithCString(void *,const char *,unsigned);
extern void *NSDefaultRunLoopMode;
extern int printf(const char *,...);
typedef struct {double x,y;} Point;
#define SEND ((void *(*)(void *,void *))objc_msgSend)
int main(void){void *app=SEND(objc_getClass("NSApplication"),sel_registerName("sharedApplication"));
void *display=SEND(objc_getClass("NSDisplay"),sel_registerName("currentDisplay"));void *s=CFStringCreateWithCString(0,"p",0x08000100);
void *event=((void *(*)(void *,void *,unsigned long,Point,unsigned long,double,long,void *,void *,void *,signed char,unsigned short))objc_msgSend)(objc_getClass("NSEvent"),sel_registerName("keyEventWithType:location:modifierFlags:timestamp:windowNumber:context:characters:charactersIgnoringModifiers:isARepeat:keyCode:"),10,(Point){0,0},0,0,0,0,s,s,0,35);
((void (*)(void *,void *,void *,signed char))objc_msgSend)(display,sel_registerName("postEvent:atStart:"),event,0);
void *past=SEND(objc_getClass("NSDate"),sel_registerName("distantPast"));
void *received=((void *(*)(void *,void *,unsigned long,void *,void *,signed char))objc_msgSend)(display,sel_registerName("nextEventMatchingMask:untilDate:inMode:dequeue:"),1UL<<10,past,NSDefaultRunLoopMode,1);
printf("NONBLOCKING_INPUT queued_key_received=%d\n",received==event);(void)app;return received!=event;}
