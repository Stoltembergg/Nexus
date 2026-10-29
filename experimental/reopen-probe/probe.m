/* SPDX-License-Identifier: GPL-3.0-only
 * Standalone owned probe: no client assets, windows, or production hooks. */
#import <AppKit/AppKit.h>
#include <stdio.h>

@interface NSApplication (ReopenProbe)
- (void)_reopen;
@end

@interface ProbeDelegate : NSObject {
@public
    unsigned calls;
    BOOL mainThread, visible, answer, completed;
}
- (BOOL)applicationShouldHandleReopen:(NSApplication *)app hasVisibleWindows:(BOOL)flag;
- (void)invoke:(id)unused;
@end

@implementation ProbeDelegate
- (BOOL)applicationShouldHandleReopen:(NSApplication *)app hasVisibleWindows:(BOOL)flag {
    calls++;
    mainThread = [NSThread isMainThread];
    visible = flag;
    printf("REOPEN_CALLBACK call=%u main_thread=%d visible=%d answer=%d\n",
           calls, mainThread, visible, answer);
    return answer;
}
- (void)invoke:(id)unused {
    if (![NSThread isMainThread]) { completed = YES; return; }
    [[NSApplication sharedApplication] _reopen];
    completed = YES;
}
@end

int main(void) {
    setbuf(stdout, NULL);
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        if (![NSThread isMainThread] || ![app respondsToSelector:@selector(_reopen)]) {
            puts("REOPEN_UNAVAILABLE main_thread_or_selector=0");
            return 2;
        }
        ProbeDelegate *delegate = [[ProbeDelegate alloc] init];
        [app setDelegate:delegate];
        for (unsigned i = 0; i < 2; i++) {
            delegate->answer = i != 0;
            delegate->completed = NO;
            [delegate performSelector:@selector(invoke:) withObject:nil afterDelay:0];
            NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
            while (!delegate->completed && [deadline timeIntervalSinceNow] > 0)
                [[NSRunLoop mainRunLoop] runMode:NSDefaultRunLoopMode
                    beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            if (!delegate->completed || delegate->calls != i + 1 || !delegate->mainThread) {
                printf("REOPEN_FAIL iteration=%u calls=%u completed=%d main_thread=%d\n",
                       i, delegate->calls, delegate->completed, delegate->mainThread);
                [app setDelegate:nil];
                [delegate release];
                return 1;
            }
        }
        [app setDelegate:nil];
        [delegate release];
        puts("REOPEN_PASS callbacks=2 answers=0,1 main_thread=1 windows_created=0");
    }
    return 0;
}
