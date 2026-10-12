extern int printf(const char *, ...);
typedef const void *CFStringRef;
typedef const void *CFLocaleRef;
typedef long CFIndex;
typedef unsigned long CFOptionFlags;
typedef unsigned char Boolean;
typedef unsigned int UTF32Char;
typedef struct { CFIndex location, length; } CFRange;
extern CFStringRef CFStringCreateWithCString(const void *, const char *, unsigned int);
extern CFLocaleRef CFLocaleCreate(const void *, CFStringRef);
extern void CFRelease(const void *);
extern Boolean CFStringIsHyphenationAvailableForLocale(CFLocaleRef);
extern CFIndex CFStringGetHyphenationLocationBeforeIndex(CFStringRef, CFIndex, CFRange, CFOptionFlags, CFLocaleRef, UTF32Char *);
int main(void) {
 CFStringRef id=CFStringCreateWithCString(0,"en_US",0x08000100);
 CFStringRef s=CFStringCreateWithCString(0,"presentation",0x08000100);
 CFLocaleRef l=CFLocaleCreate(0,id); UTF32Char c=42;
 int available=CFStringIsHyphenationAvailableForLocale(l);
 CFIndex result=CFStringGetHyphenationLocationBeforeIndex(s,10,(CFRange){0,12},0,l,&c);
 CFIndex optional=CFStringGetHyphenationLocationBeforeIndex(s,10,(CFRange){0,12},0,l,0);
 printf("hyphenation available=%d location=%ld character=%u optional=%ld\n",available,result,c,optional);
 CFRelease(l); CFRelease(s); CFRelease(id);
 return available || result!=-1 || optional!=-1 || c!=0;
}
