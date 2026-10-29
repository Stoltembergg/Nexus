/* SPDX-License-Identifier: GPL-3.0-only
 * Owned AppKit close regression. Never maps a window or touches client processes.
 */
#import <AppKit/AppKit.h>
#include <assert.h>
#include <stdio.h>

@interface CloseProbeDelegate : NSObject <NSWindowDelegate> {
@public
    BOOL allowClose;
    unsigned shouldCloseCount;
    unsigned willCloseCount;
}
@end

@implementation CloseProbeDelegate
- (BOOL) windowShouldClose: (id) sender {
    assert([NSThread isMainThread]);
    shouldCloseCount++;
    return allowClose;
}
- (void) windowWillClose: (NSNotification *) notification {
    assert([NSThread isMainThread]);
    willCloseCount++;
}
@end

@interface CloseProbeView : NSView {
@public
    unsigned downs, ups;
}
@end

@implementation CloseProbeView
- (BOOL) mouseDownCanMoveWindow { return NO; }
- (void) mouseDown: (NSEvent *) event { downs++; }
- (void) mouseUp: (NSEvent *) event {
    ups++;
    [[self window] performClose:self];
}
@end

/* Model Electron's documented drag-region arrangement: the underlying view is
 * draggable, while a transparent overlay rejects hit-testing but marks the
 * window-control rectangle as non-draggable. This is our own test view, not
 * Electron code or an inspection of the client. */
@interface CloseProbeDraggableView : CloseProbeView
@end
@implementation CloseProbeDraggableView
- (BOOL) mouseDownCanMoveWindow { return YES; }
@end

@interface CloseProbePassthroughOverlay : NSView
@end
@implementation CloseProbePassthroughOverlay
- (BOOL) mouseDownCanMoveWindow { return NO; }
- (NSView *) hitTest: (NSPoint) point { return nil; }
@end

static void checkPassthroughControl(void) {
    NSWindow *window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(20, 20, 320, 180)
                  styleMask:NSBorderlessWindowMask
                    backing:NSBackingStoreBuffered defer:NO];
    [window setReleasedWhenClosed:NO];
    [window setMovable:YES];
    [window setMovableByWindowBackground:YES];
    CloseProbeDelegate *delegate = [[CloseProbeDelegate alloc] init];
    delegate->allowClose = YES;
    [window setDelegate:delegate];
    CloseProbeDraggableView *web = [[CloseProbeDraggableView alloc]
        initWithFrame:NSMakeRect(0, 0, 320, 180)];
    CloseProbePassthroughOverlay *overlay = [[CloseProbePassthroughOverlay alloc]
        initWithFrame:NSMakeRect(250, 130, 40, 40)];
    [[window contentView] addSubview:web];
    [web addSubview:overlay];
    NSPoint point = [overlay convertPoint:NSMakePoint(20, 20) toView:nil];
    NSEvent *down = [NSEvent mouseEventWithType:NSLeftMouseDown location:point
        modifierFlags:0 window:window clickCount:1 deltaX:0 deltaY:0];
    NSEvent *up = [NSEvent mouseEventWithType:NSLeftMouseUp location:point
        modifierFlags:0 window:window clickCount:1 deltaX:0 deltaY:0];
    [window sendEvent:down];
    [window sendEvent:up];
    assert(web->downs == 1 && web->ups == 1);
    assert(delegate->shouldCloseCount == 1 && delegate->willCloseCount == 1);
    [window setDelegate:nil];
    [overlay release];
    [web release];
    [window release];
    [delegate release];
}

static void checkCustomControl(BOOL movableBackground) {
    NSWindow *window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(20, 20, 320, 180)
                  styleMask:NSBorderlessWindowMask
                    backing:NSBackingStoreBuffered defer:NO];
    [window setReleasedWhenClosed:NO];
    [window setMovable:YES];
    [window setMovableByWindowBackground:movableBackground];
    CloseProbeDelegate *delegate = [[CloseProbeDelegate alloc] init];
    delegate->allowClose = YES;
    [window setDelegate:delegate];
    CloseProbeView *control = [[CloseProbeView alloc] initWithFrame:NSMakeRect(250, 130, 40, 40)];
    [[window contentView] addSubview:control];
    NSPoint point = [control convertPoint:NSMakePoint(20, 20) toView:nil];
    NSEvent *down = [NSEvent mouseEventWithType:NSLeftMouseDown location:point
        modifierFlags:0 window:window clickCount:1 deltaX:0 deltaY:0];
    NSEvent *up = [NSEvent mouseEventWithType:NSLeftMouseUp location:point
        modifierFlags:0 window:window clickCount:1 deltaX:0 deltaY:0];
    // Direct dispatch to this owned window only; no global input or mapped UI.
    [window sendEvent:down];
    [window sendEvent:up];
    assert(control->downs == 1 && control->ups == 1);
    assert(delegate->shouldCloseCount == 1 && delegate->willCloseCount == 1);
    [window setDelegate:nil];
    [control release];
    [window release];
    [delegate release];
}

int main(void) {
    setbuf(stdout, NULL);
    @autoreleasepool {
        [NSApplication sharedApplication];
        NSWindow *window = [[NSWindow alloc]
            initWithContentRect:NSMakeRect(20, 20, 320, 180)
                      styleMask:NSTitledWindowMask | NSClosableWindowMask
                        backing:NSBackingStoreBuffered defer:NO];
        [window setReleasedWhenClosed:NO];
        CloseProbeDelegate *delegate = [[CloseProbeDelegate alloc] init];
        [window setDelegate:delegate];
        [window performClose:nil];
        assert(delegate->shouldCloseCount == 1);
        assert(delegate->willCloseCount == 0);
        delegate->allowClose = YES;
        [window performClose:nil];
        assert(delegate->shouldCloseCount == 2);
        assert(delegate->willCloseCount == 1);
        [window setDelegate:nil];
        [window release];
        [delegate release];
        checkCustomControl(NO);
        checkCustomControl(YES);
        checkPassthroughControl();
        puts("WINDOW_CLOSE_SEMANTICS veto=1 allowed=1 notification=1 main_thread=1");
        puts("WINDOW_CLOSE_CONTROL down=1 up=1 close=1 background_drag_off_on=1");
        puts("WINDOW_CLOSE_PASSTHROUGH overlay=1 draggable_parent=1 action=1");
    }
    return 0;
}
