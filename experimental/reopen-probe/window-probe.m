/* SPDX-License-Identifier: GPL-3.0-only
 * Opt-in owned-window experiment; no client or synthesized input. */
#import <AppKit/AppKit.h>
#include <stdio.h>

@interface NSApplication (ReopenWindowProbe)
- (void)_reopen;
@end
@interface NSWindow (ReopenWindowProbe)
- (id)platformWindow;
@end
@interface NSObject (ReopenWindowHandle)
- (unsigned long)windowHandle;
@end

@interface WindowProbeDelegate : NSObject {
@public
    NSWindow *eligible;
    BOOL restore;
    unsigned calls;
    BOOL mainThread;
}
@end
@implementation WindowProbeDelegate
- (BOOL)applicationShouldHandleReopen:(NSApplication *)app hasVisibleWindows:(BOOL)visible {
    calls++;
    mainThread = [NSThread isMainThread];
    printf("WINDOW_REOPEN_CALLBACK call=%u visible=%d restore=%d main_thread=%d\n",
           calls, visible, restore, mainThread);
    if (restore) [eligible orderFront:nil];
    /* The probe owns the policy; suppress the implementation's default action. */
    return NO;
}
@end

static unsigned long xid(NSWindow *window) {
    id platform = [window platformWindow];
    if (![platform respondsToSelector:@selector(windowHandle)]) return 0;
    return [platform windowHandle];
}

int main(void) {
    setbuf(stdout, NULL);
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        if (![NSThread isMainThread] || ![app respondsToSelector:@selector(_reopen)]) {
            puts("WINDOW_REOPEN_UNAVAILABLE selector_or_thread"); return 2;
        }
        NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,320,180)
            styleMask:NSTitledWindowMask | NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
        NSWindow *ineligible = [[NSWindow alloc] initWithContentRect:NSMakeRect(50,50,160,100)
            styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
        [window setReleasedWhenClosed:NO];
        [ineligible setReleasedWhenClosed:NO];
        WindowProbeDelegate *delegate = [[WindowProbeDelegate alloc] init];
        delegate->eligible = window;
        [app setDelegate:delegate];
        [window orderFront:nil];
        unsigned long before = xid(window);
        [window orderOut:nil];
        unsigned long hidden = xid(window);
        BOOL initial = [window isVisible] == NO && [ineligible isVisible] == NO;
        [app _reopen]; /* veto: no owned-window restoration */
        BOOL veto = ![window isVisible] && ![ineligible isVisible] && delegate->calls == 1 && delegate->mainThread;
        delegate->restore = YES;
        [app _reopen]; /* delegate explicitly restores only the eligible window */
        unsigned long after = xid(window);
        BOOL restored = [window isVisible] && ![ineligible isVisible] && delegate->calls == 2 && delegate->mainThread;
        BOOL same = before && before == hidden && before == after;
        printf("WINDOW_REOPEN_RESULT before=%lu hidden=%lu after=%lu initial=%d veto=%d restored=%d same_xid=%d\n",
               before, hidden, after, initial, veto, restored, same);
        [app setDelegate:nil];
        [window orderOut:nil];
        [ineligible orderOut:nil];
        [window release];
        [ineligible release];
        [delegate release];
        return initial && veto && restored && same ? 0 : 1;
    }
}
