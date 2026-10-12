/* Guest regression: Chromium requires non-null CoreText trait dictionaries. */
typedef const void *CFTypeRef;
typedef struct {double x,y;} CGPoint;
typedef struct {double width,height;} CGSize;
typedef struct {CGPoint origin;CGSize size;} CGRect;
extern CFTypeRef CFStringCreateWithCString(CFTypeRef, const char *, unsigned int);
extern CFTypeRef CTFontCreateWithName(CFTypeRef, double, const void *);
extern CFTypeRef CTFontCopyTraits(CFTypeRef);
extern CFTypeRef CTFontCopyPostScriptName(CFTypeRef);
extern CFTypeRef CTFontCopyFamilyName(CFTypeRef);
extern long CFStringGetLength(CFTypeRef);
extern CFTypeRef CTFontCreateWithFontDescriptor(CFTypeRef,double,const void *);
extern double CTFontGetSize(CFTypeRef);
extern long CFStringCompare(CFTypeRef,CFTypeRef,unsigned long);
extern CFTypeRef CTFontCopyFontDescriptor(CFTypeRef);
extern CFTypeRef CTFontCopyAvailableTables(CFTypeRef, unsigned);
extern unsigned CTFontGetUnitsPerEm(CFTypeRef);
extern long CFArrayGetCount(CFTypeRef);
extern CFTypeRef CFArrayGetValueAtIndex(CFTypeRef,long);
extern CFTypeRef CTFontCopyTable(CFTypeRef, unsigned int, unsigned int);
extern int CTFontGetGlyphsForCharacters(CFTypeRef, const unsigned short *, unsigned short *, long);
extern CGRect CTFontGetBoundingRectsForGlyphs(CFTypeRef, int, const unsigned short *, CGRect *, long);
extern double CTFontGetAdvancesForGlyphs(CFTypeRef, int, const unsigned short *, CGSize *, long);
extern CFTypeRef CFDictionaryGetValue(CFTypeRef, CFTypeRef);
extern int CFNumberGetValue(CFTypeRef, int, void *);
extern long CFDataGetLength(CFTypeRef);
extern void CFRelease(CFTypeRef);
extern CFTypeRef CFRetain(CFTypeRef);
extern CFTypeRef kCTFontWeightTrait;
extern int printf(const char *, ...);
extern void *objc_getClass(const char *);
extern void *sel_registerName(const char *);
extern void objc_msgSend(void);
int main(int argc, char **argv) {
    CFTypeRef name = CFStringCreateWithCString(0, "DejaVu Sans", 0x08000100);
    CFTypeRef font = CTFontCreateWithName(name, 16, 0);
    if (argc > 1)
        font=((void *(*)(void *,void *,double))objc_msgSend)(objc_getClass("NSFont"),sel_registerName("systemFontOfSize:"),16);
    if (!font) return 1;
    if (argc > 1) CFRetain(font);
    CFTypeRef psName=CTFontCopyPostScriptName(font), family=CTFontCopyFamilyName(font);
    if (!psName || !family || !CFStringGetLength(psName) || !CFStringGetLength(family)) return 11;
    CFRelease(psName); CFRelease(family);
    CFTypeRef descriptor = CTFontCopyFontDescriptor(font);
    CFTypeRef tables = CTFontCopyAvailableTables(font, 0);
    unsigned units = CTFontGetUnitsPerEm(font);
    if (!descriptor || !tables || CFArrayGetCount(tables) < 1 || !units) return 8;
    for (long i=0;i<CFArrayGetCount(tables);++i) {
        int tag=0;
        if (!CFNumberGetValue(CFArrayGetValueAtIndex(tables,i),3,&tag)||!tag) return 9;
    }
    printf("FONT units_per_em=%u table_count=%ld descriptor=valid\n",units,CFArrayGetCount(tables));
    CFTypeRef roundTrip=CTFontCreateWithFontDescriptor(descriptor,0,0);
    if (!roundTrip || CTFontGetSize(roundTrip)!=16) return 12;
    CFTypeRef originalPS=CTFontCopyPostScriptName(font), roundTripPS=CTFontCopyPostScriptName(roundTrip);
    if (!originalPS || !roundTripPS || CFStringCompare(originalPS,roundTripPS,0)!=0) return 13;
    CFRelease(originalPS);CFRelease(roundTripPS);CFRelease(roundTrip);
    printf("FONT descriptor_roundtrip=size_and_name_match\n");
    CFRelease(descriptor);
    CFRelease(tables);
    CFTypeRef traits = CTFontCopyTraits(font);
    if (!traits) return 2;
    CFTypeRef weight = CFDictionaryGetValue(traits, kCTFontWeightTrait);
    double value = 9;
    if (!weight || !CFNumberGetValue(weight, 6 /* double */, &value)) return 3;
    CFTypeRef table = CTFontCopyTable(font, 0x4f532f32 /* OS/2 */, 0);
    if (!table || CFDataGetLength(table) < 8) return 4;
    printf("FONT traits_weight=%.2f OS2_bytes=%ld\n", value, CFDataGetLength(table));
    unsigned short characters[] = {'A', ' '};
    struct { unsigned short glyphs[2], guard[2]; } output = {{0,0},{0xbeef,0xcafe}};
    unsigned short *glyphs = output.glyphs;
    CGRect bounds[2];
    if (!CTFontGetGlyphsForCharacters(font, characters, glyphs, 2)) return 6;
    if (output.guard[0]!=0xbeef || output.guard[1]!=0xcafe) return 10;
    CTFontGetBoundingRectsForGlyphs(font, 0, glyphs, bounds, 2);
    double advance = CTFontGetAdvancesForGlyphs(font, 0, glyphs, 0, 2);
    printf("FONT A_bounds=%.2fx%.2f space_bounds=%.2fx%.2f total_advance=%.2f\n",
            bounds[0].size.width, bounds[0].size.height,
            bounds[1].size.width, bounds[1].size.height, advance);
    if (bounds[0].size.width <= 0 || bounds[0].size.height <= 0 ||
            bounds[1].size.width != 0 || bounds[1].size.height != 0 || advance <= 0) return 7;
    CFRelease(table); CFRelease(traits); CFRelease(font); CFRelease(name);
    return value == 0 ? 0 : 5;
}
