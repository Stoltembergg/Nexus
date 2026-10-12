/* Guest regression: CTFontDrawGlyphs must draw pixels and preserve text position. */
typedef struct { double x,y; } Point;
extern void *CFStringCreateWithCString(void *,const char *,unsigned);
extern void *CTFontCreateWithName(void *,double,const void *);
extern int CTFontGetGlyphsForCharacters(void *,const unsigned short *,unsigned short *,long);
extern void CTFontDrawGlyphs(void *,const unsigned short *,const Point *,unsigned long,void *);
extern void *CGColorSpaceCreateDeviceRGB(void);
extern void *CGBitmapContextCreate(void *,unsigned long,unsigned long,unsigned long,unsigned long,void *,unsigned);
extern void CGContextSetRGBFillColor(void *,double,double,double,double);
extern void CGContextSetTextPosition(void *,double,double);
extern Point CGContextGetTextPosition(void *);
extern int atoi(const char *);
extern int printf(const char *,...);
typedef struct { Point origin; struct {double width,height;} size; } Rect;
extern Rect CTFontGetBoundingRectsForGlyphs(void *,unsigned,const unsigned short *,Rect *,long);
extern double CTFontGetAdvancesForGlyphs(void *,unsigned,const unsigned short *,void *,long);
extern int pthread_create(unsigned long *,void *,void *(*)(void *),void *);
extern int pthread_join(unsigned long,void **);
static void *sharedFont;
static unsigned short sharedGlyph;
static void *metrics(void *unused) {
 for(int i=0;i<20000;i++) {
  CTFontGetBoundingRectsForGlyphs(sharedFont,0,&sharedGlyph,0,1);
  CTFontGetAdvancesForGlyphs(sharedFont,0,&sharedGlyph,0,1);
 }
 return 0;
}
static unsigned char pixels[128*64*4];
int main(int argc, char **argv) {
 void *name=CFStringCreateWithCString(0,"DejaVu Sans",0x08000100);
 void *font=CTFontCreateWithName(name,24,0), *space=CGColorSpaceCreateDeviceRGB();
 void *context=CGBitmapContextCreate(pixels,128,64,8,128*4,space,argc > 1 ? atoi(argv[1]) : 2);
 if(!font||!context)return 1;
 unsigned short chars[]={'A','B'},glyphs[2];
 if(!CTFontGetGlyphsForCharacters(font,chars,glyphs,2))return 2;
 Point positions[]={{10,30},{55,30}};
 CGContextSetRGBFillColor(context,1,1,1,1);
 CGContextSetTextPosition(context,7,9);
 CTFontDrawGlyphs(font,glyphs,positions,2,context);
 unsigned referenceLeft=0,referenceRight=0;
 for(unsigned y=0;y<64;y++)for(unsigned x=0;x<128;x++)
  if(pixels[(y*128+x)*4]||pixels[(y*128+x)*4+1]||pixels[(y*128+x)*4+2]){if(x<45)referenceLeft++;else referenceRight++;}
 for(unsigned i=0;i<sizeof(pixels);i++)pixels[i]=0;
 sharedFont=font;sharedGlyph=glyphs[0];
 unsigned long worker;pthread_create(&worker,0,metrics,0);
 for(int i=0;i<20000;i++)CTFontDrawGlyphs(font,glyphs,positions,2,context);
 pthread_join(worker,0);
 Point after=CGContextGetTextPosition(context);
 unsigned left=0,right=0;
 for(unsigned y=0;y<64;y++)for(unsigned x=0;x<128;x++)
  if(pixels[(y*128+x)*4]||pixels[(y*128+x)*4+1]||pixels[(y*128+x)*4+2]){if(x<45)left++;else right++;}
 printf("GLYPHS left_pixels=%u right_pixels=%u text_position=%.0f,%.0f\n",left,right,after.x,after.y);
 printf("REFERENCE left=%u right=%u\n",referenceLeft,referenceRight);
 return !(left==referenceLeft&&right==referenceRight&&after.x==7&&after.y==9);
}
