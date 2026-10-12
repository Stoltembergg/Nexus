/* Chromium queries subtype for ordinary mouse and motion events. */
typedef struct {double x,y;} Point;
extern void *objc_getClass(const char *),*sel_registerName(const char *);
extern void objc_msgSend(void);
extern int printf(const char *,...);
static void *send(void *o,const char *s){return ((void *(*)(void *,void *))objc_msgSend)(o,sel_registerName(s));}
int main(void){
 void *pool=send(objc_getClass("NSAutoreleasePool"),"new");int ok=1;
 int types[]={1,2,3,4,5,6,7,8,9,22,25,26,27};
 for(unsigned i=0;i<sizeof(types)/sizeof(types[0]);i++){
  void *e=((void *(*)(void *,void *,unsigned long,Point,unsigned long,void *,long,double,double))objc_msgSend)(objc_getClass("NSEvent"),sel_registerName("mouseEventWithType:location:modifierFlags:window:clickCount:deltaX:deltaY:"),types[i],(Point){10,20},0,0,1,0,0);
  short subtype=((short(*)(void *,void *))objc_msgSend)(e,sel_registerName("subtype"));ok &= e!=0&&subtype==0;
 }
 printf("MOUSE_SUBTYPE events=%lu regular=%d pass=%d\n",sizeof(types)/sizeof(types[0]),ok,ok);send(pool,"drain");return ok?0:1;
}
