/* Exercise the same Carbon keyboard queries used by Chromium. */
extern void *objc_getClass(const char *),*sel_registerName(const char *);
extern void objc_msgSend(void);
extern unsigned char LMGetKbdType(void),LMGetKbdLast(void);
extern void *TISCopyCurrentKeyboardLayoutInputSource(void);
extern void *TISGetInputSourceProperty(void *,const void *);
extern const void *kTISPropertyUnicodeKeyLayoutData;
extern const unsigned char *CFDataGetBytePtr(const void *);
extern void CFRelease(const void *);
extern int UCKeyTranslate(const void *,unsigned short,unsigned short,unsigned,unsigned,unsigned,unsigned *,unsigned,unsigned *,unsigned short *);
extern int printf(const char *,...);
int main(void){
 ((void *(*)(void *,void *))objc_msgSend)(objc_getClass("NSApplication"),sel_registerName("sharedApplication"));
 void *source=TISCopyCurrentKeyboardLayoutInputSource();if(!source)return 1;
 const void *layout=CFDataGetBytePtr(TISGetInputSourceProperty(source,kTISPropertyUnicodeKeyLayoutData));
 if(!layout)return 2;
 unsigned dead=0,n=0;unsigned short lower[4]={0},upper[4]={0};
 int a=UCKeyTranslate(layout,0,0,0,LMGetKbdLast(),0,&dead,4,&n,lower);
 if(a||n!=1)return 3;
 int b=UCKeyTranslate(layout,0,0,2,LMGetKbdLast(),0,&dead,4,&n,upper);
 printf("CARBON_KEYBOARD type=%u last=%u lower=%04x shifted=%04x statuses=%d,%d\n",LMGetKbdType(),LMGetKbdLast(),lower[0],upper[0],a,b);
 CFRelease(source);
 return b||n!=1||LMGetKbdLast()!=LMGetKbdType()||lower[0]<'a'||lower[0]>'z'||upper[0]!=lower[0]-32;
}
