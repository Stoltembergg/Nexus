/* Neutral, owned window. Commands are authenticated by a per-run nonce. */
#import <AppKit/AppKit.h>
#include <stdio.h>

@interface NSApplication (ProbeReopen)
- (void)_reopen;
@end
@interface NSWindow (ProbePlatform)
- (id)platformWindow;
@end
@interface NSObject (ProbeHandle)
- (unsigned long)windowHandle;
@end

@interface ProbeDelegate : NSObject <NSWindowDelegate> {
    NSWindow *window;
    NSString *path, *nonce;
    unsigned long sequence;
}
- (id)initWithWindow:(NSWindow *)w path:(NSString *)p nonce:(NSString *)n;
- (void)tick:(NSTimer *)timer;
@end
@implementation ProbeDelegate
- (id)initWithWindow:(NSWindow *)w path:(NSString *)p nonce:(NSString *)n {
    if ((self = [super init])) { window = w; path = [p copy]; nonce = [n copy]; sequence = 0; }
    return self;
}
- (BOOL)windowShouldClose:(id)sender {
    if (sender != window) return NO;
    [window orderOut:nil];
    puts("CLOSED_BY_USER");
    return NO;
}
- (BOOL)applicationShouldHandleReopen:(NSApplication *)app hasVisibleWindows:(BOOL)visible {
    [window orderFront:nil];
    puts("REOPEN_CALLBACK");
    return NO;
}
- (void)tick:(NSTimer *)timer {
    NSString *data = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:NULL];
    NSArray *fields = [data componentsSeparatedByString:@" "];
    if ([fields count] != 3 || ![[fields objectAtIndex:0] isEqualToString:nonce]) return;
    NSString *number = [fields objectAtIndex:1];
    unsigned long next = (unsigned long)[number longLongValue];
    if (next <= sequence || ![[NSString stringWithFormat:@"%lu", next] isEqualToString:number]) return;
    NSString *command = [fields objectAtIndex:2];
    if ([command isEqualToString:@"reopen"] && next == sequence + 1) {
        sequence = next;
        [NSApp _reopen];
        printf("ACK %lu reopen\n", sequence);
    } else if ([command isEqualToString:@"stop"]) {
        sequence = next;
        printf("ACK %lu stop\n", sequence);
        [NSApp stop:nil];
    }
}
@end

int main(int argc, const char **argv) {
    setbuf(stdout, NULL);
    if (argc != 3) return 2;
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        if (![app respondsToSelector:@selector(_reopen)]) return 3;
        NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,320,180)
            styleMask:NSTitledWindowMask | NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
        [window setTitle:@"Neutral reopen probe — close with X"];
        [window setReleasedWhenClosed:NO];
        ProbeDelegate *delegate = [[ProbeDelegate alloc] initWithWindow:window
            path:[NSString stringWithUTF8String:argv[1]] nonce:[NSString stringWithUTF8String:argv[2]]];
        [window setDelegate:delegate]; [app setDelegate:delegate]; [window orderFront:nil];
        id platform = [window platformWindow];
        if (![platform respondsToSelector:@selector(windowHandle)]) return 4;
        unsigned long xid = [platform windowHandle];
        if (!xid) return 5;
        printf("READY %lu\n", xid);
        [NSTimer scheduledTimerWithTimeInterval:0.1 target:delegate selector:@selector(tick:) userInfo:nil repeats:YES];
        [app run];
    }
    return 0;
}
