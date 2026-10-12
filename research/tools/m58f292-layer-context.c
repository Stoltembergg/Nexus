/* Root backing contexts must survive repeated setup and follow layer replacement. */
typedef struct {double x,y;} Point;
typedef struct {double width,height;} Size;
typedef struct {Point origin;Size size;} Rect;
extern void *objc_getClass(const char *),*sel_registerName(const char *);
extern void objc_msgSend(void);
extern int printf(const char *,...);
static void *send(void *o,const char *s){return ((void *(*)(void *,void *))objc_msgSend)(o,sel_registerName(s));}
static void arg(void *o,const char *s,void *v){((void (*)(void *,void *,void *))objc_msgSend)(o,sel_registerName(s),v);}
static void *key(void *o,const char *s){void *k=((void *(*)(void *,void *,const char *))objc_msgSend)(objc_getClass("NSString"),sel_registerName("stringWithUTF8String:"),s);return ((void *(*)(void *,void *,void *))objc_msgSend)(o,sel_registerName("valueForKey:"),k);}
static void *view(void){Rect r={{0,0},{32,32}};return ((void *(*)(void *,void *,Rect))objc_msgSend)(send(objc_getClass("NSView"),"alloc"),sel_registerName("initWithFrame:"),r);}
int main(void){
 void *pool=send(objc_getClass("NSAutoreleasePool"),"new");
 send(objc_getClass("NSApplication"),"sharedApplication");
 void *v=view(),*layer=send(objc_getClass("CALayer"),"new");arg(v,"setLayer:",layer);send(layer,"release");
 void *ctx=key(v,"layerContext");int deferred=send(ctx,"glContext")==0;int stable=ctx!=0,updated=1;
 for(int i=0;i<100;i++){
  send(v,"_createLayerContextIfNeeded");stable &= key(v,"layerContext")==ctx;
  layer=send(objc_getClass("CALayer"),"new");arg(v,"setLayer:",layer);
  updated &= key(ctx,"layer")==layer;send(layer,"release");
 }
 void *child=view();layer=send(objc_getClass("CALayer"),"new");arg(child,"setLayer:",layer);send(layer,"release");
 arg(v,"addSubview:",child);send(child,"_addLayerToSuperlayer");
 int joined=key(child,"layerContext")==0 && send(send(child,"layer"),"_context")==ctx;
 Rect rect={{300,300},{32,32}};
 void *window=((void *(*)(void *,void *,Rect,unsigned long,unsigned long,int))objc_msgSend)
  (send(objc_getClass("NSWindow"),"alloc"),sel_registerName("initWithContentRect:styleMask:backing:defer:"),rect,1,2,0);
 arg(window,"setContentView:",v);
 arg(window,"makeKeyAndOrderFront:",0);
 void *attachedContext=send(send(v,"layer"),"_context");
 int attached=attachedContext!=0 && send(attachedContext,"glContext")!=0;
 int ok=stable&&updated&&joined&&deferred&&attached;
 printf("LAYER_CONTEXT stable=%d replacement=%d joined=%d deferred=%d attached=%d pass=%d\n",stable,updated,joined,deferred,attached,ok);
 send(child,"release");send(v,"release");send(window,"close");send(pool,"drain");return ok?0:1;
}
