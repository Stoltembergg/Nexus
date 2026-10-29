#import <Foundation/Foundation.h>
#import <Onyx2D/O2ImageSource.h>
#import <Onyx2D/O2Image.h>
#import <Onyx2D/O2DataProvider.h>
#import <Onyx2D/O2BitmapContext.h>
#import <Onyx2D/O2ColorSpace.h>
#include <stdio.h>

int main(int argc, char **argv) {
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    int ok = argc == 4;
    for (int i = 1; ok && i <= 3; i++) {
        O2ImageSource *source = [O2ImageSource newImageSourceWithURL:
            [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[i]]] options:NULL];
        NSUInteger count = [source count];
        if (i == 3) ok = count == 0;
        else {
            O2Image *image = count == 1 ? [source createImageAtIndex:0 options:NULL] : nil;
            CFDataRef data = image ? O2DataProviderCopyData(O2ImageGetDataProvider(image)) : NULL;
            const UInt8 *p = data ? CFDataGetBytePtr(data) : NULL;
            unsigned a = i == 1 ? 255 : 128;
            ok = image && O2ImageGetWidth(image) == 256 && O2ImageGetHeight(image) == 256 &&
                data && CFDataGetLength(data) == 256 * 256 * 4 && p[3] == a &&
                p[0] == (17 * a + 127) / 255 && p[1] == (83 * a + 127) / 255 &&
                p[2] == (191 * a + 127) / 255;
            O2ColorSpace *space = O2ColorSpaceCreateDeviceRGB();
            O2BitmapContext *ctx = (O2BitmapContext *)O2BitmapContextCreate(NULL, 256, 256, 8, 1024, space,
                kO2ImageAlphaPremultipliedFirst | kO2BitmapByteOrder32Host);
            if (ok && ctx && O2BitmapContextGetData(ctx)) {
                [ctx drawImage:image inRect:O2RectMake(0, 0, 256, 256)];
                uint32_t rendered = ((uint32_t *)O2BitmapContextGetData(ctx))[0];
                ok = (rendered >> 24) == a && ((rendered >> 16) & 255) == p[0] &&
                    ((rendered >> 8) & 255) == p[1] && (rendered & 255) == p[2];
            } else ok = 0;
            [ctx release];
            [space release];
            if (data) CFRelease(data);
            [image release];
        }
        printf("ICNS_JP2 case=%d count=%lu %s\n", i, (unsigned long)count, ok ? "PASS" : "FAIL");
        [source release];
    }
    [pool release];
    return ok ? 0 : 1;
}
