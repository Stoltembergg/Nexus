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
 Point after=CGContextGetTextPosition(context);
 unsigned left=0,right=0;
 for(unsigned y=0;y<64;y++)for(unsigned x=0;x<128;x++)
  if(pixels[(y*128+x)*4]||pixels[(y*128+x)*4+1]||pixels[(y*128+x)*4+2]){if(x<45)left++;else right++;}
 printf("GLYPHS left_pixels=%u right_pixels=%u text_position=%.0f,%.0f\n",left,right,after.x,after.y);
 return !(left&&right&&after.x==7&&after.y==9);
}
