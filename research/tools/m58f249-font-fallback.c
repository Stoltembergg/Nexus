extern void *objc_getClass(const char *),*sel_registerName(const char *);
extern void objc_msgSend(void);
extern void *CFStringCreateWithCString(void *,const char *,unsigned);
extern int CTFontGetGlyphsForCharacters(void *,const unsigned short *,unsigned short *,long);
extern double CTFontGetSize(void *);
extern int printf(const char *,...);
typedef struct {unsigned long location,length;} Range;
int main(void){void *cls=objc_getClass("NSFont");void *font=((void *(*)(void *,void *,double))objc_msgSend)(cls,sel_registerName("systemFontOfSize:"),16);
const char *text[]={"A","\xe4\xb8\xad"};unsigned short chars[]={65,0x4e2d};
for(int i=0;i<2;i++){void *s=CFStringCreateWithCString(0,text[i],0x08000100);void *fallback=((void *(*)(void *,void *,void *,void *,Range,void *))objc_msgSend)(cls,sel_registerName("findFontLike:forString:withRange:inLanguage:"),font,s,(Range){0,1},0);unsigned short glyph=0;
if(!fallback||CTFontGetSize(fallback)!=16||!CTFontGetGlyphsForCharacters(fallback,&chars[i],&glyph,1)||!glyph)return 1;
printf("FALLBACK codepoint=%x glyph=%u size=16\n",chars[i],glyph);}
return 0;}
