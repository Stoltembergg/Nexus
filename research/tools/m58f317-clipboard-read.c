/* Read synthetic isolated clipboard, reporting only length and equality. */
extern void *objc_getClass(const char *),*sel_registerName(const char *);
extern void objc_msgSend(void);
extern int printf(const char *,...);
static void *send(void *o,const char *s){return ((void *(*)(void *,void *))objc_msgSend)(o,sel_registerName(s));}
static void *arg(void *o,const char *s,void *v){return ((void *(*)(void *,void *,void *))objc_msgSend)(o,sel_registerName(s),v);}
extern void *NSStringPboardType;
int main(int argc,char **argv){
 (void)argv;
 void *pool=send(objc_getClass("NSAutoreleasePool"),"new");send(objc_getClass("NSApplication"),"sharedApplication");
 void *p=send(objc_getClass("NSPasteboard"),"generalPasteboard");
 void *types=send(p,"types");
 int available=((int(*)(void*,void*,void*))objc_msgSend)(types,sel_registerName("containsObject:"),NSStringPboardType)&255;
 void *text=arg(p,"stringForType:",NSStringPboardType);
 void *expected=((void *(*)(void*,void*,const char*))objc_msgSend)(objc_getClass("NSString"),sel_registerName("stringWithUTF8String:"),argc>1?"darling_past\xc3\xa9":"darling_paste");
 unsigned long len=((unsigned long(*)(void*,void*))objc_msgSend)(text,sel_registerName("length"));
 int match=((int(*)(void*,void*,void*))objc_msgSend)(text,sel_registerName("isEqualToString:"),expected)&255;
 printf("CLIPBOARD_READ available=%d length=%lu match=%d\n",available,len,match);send(pool,"drain");return available&&match?0:1;
}
