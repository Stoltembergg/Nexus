/* Owned, offscreen Onyx2D ICNS decoder probe. Never prints image data. */
#import <Foundation/Foundation.h>
#import <Onyx2D/O2ImageSource.h>
#import <Onyx2D/O2BitmapContext.h>
#import <Onyx2D/O2ColorSpace.h>
#include <stdio.h>

int main(int argc, char **argv) {
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    int failed = argc < 2;
    for (int arg = 1; arg < argc; arg++) {
        NSString *path = [NSString stringWithUTF8String: argv[arg]];
        O2ImageSource *source = [O2ImageSource newImageSourceWithURL:
                [NSURL fileURLWithPath: path] options: NULL];
        NSUInteger count = [source count], rendered = 0;
        for (NSUInteger i = 0; i < count; i++) {
            O2Image *image = [source createImageAtIndex: i options: NULL];
            if (image == nil) continue;
            size_t width = O2ImageGetWidth(image), height = O2ImageGetHeight(image);
            O2ColorSpace *space = O2ColorSpaceCreateDeviceRGB();
            O2BitmapContext *context = width && height ? (O2BitmapContext *)
                    O2BitmapContextCreate(NULL, width, height, 8, width * 4, space,
                            kO2ImageAlphaPremultipliedFirst | kO2BitmapByteOrder32Host) : nil;
            if (context != nil && O2BitmapContextGetData(context) != NULL) {
                [context drawImage: image inRect: O2RectMake(0, 0, width, height)];
                rendered++;
            }
            [context release];
            [space release];
            [image release];
        }
        printf("ICNS_CHECK input=%d representations=%lu rendered=%lu\n", arg,
               (unsigned long)count, (unsigned long)rendered);
        if (!rendered) failed = 1;
        [source release];
    }
    [pool release];
    return failed;
}
