/* Owned, neutral status-menu timing probe. No client integration. */
#import <AppKit/AppKit.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

@interface NSStatusItem (SequenceNative)
- (BOOL)_ensureNative;
- (const char *)_nativeBusName;
@end

@interface SequenceOwner : NSObject {
    NSMenu *menu;
    NSStatusItem *status;
}
- (id)initWithMenu:(NSMenu *)value status:(NSStatusItem *)item;
- (void)populate:(NSTimer *)timer;
- (void)noop:(id)sender;
@end
@implementation SequenceOwner
- (id)initWithMenu:(NSMenu *)value status:(NSStatusItem *)item { self = [super init]; if (self) { menu = value; status = item; } return self; }
- (void)noop:(id)sender { (void)sender; }
- (void)populate:(NSTimer *)timer {
    (void)timer;
    NSArray *titles = @[@"Primeiro teste", @"Segundo teste", @"Terceiro teste", @""];
    for (NSUInteger i = 0; i < [titles count]; i++) {
        NSMenuItem *entry = [menu itemAtIndex:i];
        [entry setTitle:[titles objectAtIndex:i]];
        [entry setEnabled:YES];
        [entry setHidden:NO];
    }
    [status setMenu:menu]; /* Publish the completed snapshot through the public API. */
    printf("SEQUENCE_POPULATED count=%ld\n", (long)[menu numberOfItems]);
}
@end

int main(void) {
    setbuf(stdout, NULL);
    @autoreleasepool {
        [NSApplication sharedApplication];
        NSStatusBar *bar = [NSStatusBar systemStatusBar];
        NSStatusItem *status = [[bar statusItemWithLength:NSSquareStatusItemLength] retain];
        const char *variant = getenv("SEQUENCE_VARIANT");
        BOOL corrected = variant && strcmp(variant, "corrected") == 0;
        NSString *title = corrected ? @"Neutral corrected probe" : @"Neutral control probe";
        [[status button] setTitle:title];
        [[status button] setToolTip:title];
        NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(22, 22)];
        [image lockFocus];
        if (corrected)
            [[NSColor colorWithCalibratedRed:1 green:0 blue:0.9 alpha:1] set];
        else
            [[NSColor colorWithCalibratedRed:0.05 green:0.9 blue:0.25 alpha:1] set];
        NSRectFill(NSMakeRect(0, 0, 22, 22));
        [[NSColor whiteColor] set]; NSRectFill(NSMakeRect(7, 7, 8, 8));
        [image unlockFocus]; [[status button] setImage:image]; [image release];
        NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Neutral probe"];
        [menu setAutoenablesItems:NO];
        SequenceOwner *owner = [[SequenceOwner alloc] initWithMenu:menu status:status];
        for (int i = 0; i < 4; i++) {
            NSMenuItem *entry = [menu addItemWithTitle:@"" action:@selector(noop:) keyEquivalent:@""];
            [entry setTarget:owner];
            [entry setEnabled:NO];
            [entry setHidden:YES];
        }
        [status setMenu:menu];
        if (![status _ensureNative] || ![status _nativeBusName]) return 1;
        printf("SEQUENCE_INITIAL bus=%s count=%ld\n", [status _nativeBusName], (long)[menu numberOfItems]);
        [NSTimer scheduledTimerWithTimeInterval:8 target:owner selector:@selector(populate:) userInfo:nil repeats:NO];
        long duration = 180;
        const char *setting = getenv("SEQUENCE_TEST_SECONDS");
        if (setting && atoi(setting) >= 10 && atoi(setting) <= 180) duration = atoi(setting);
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:duration];
        while ([deadline timeIntervalSinceNow] > 0) {
            @autoreleasepool { [[NSRunLoop mainRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]]; }
        }
        [bar removeStatusItem:status]; [status release]; [menu release]; [owner release];
        puts("SEQUENCE_DONE");
    }
    return 0;
}
