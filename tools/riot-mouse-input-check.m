#import <AppKit/AppKit.h>
#import <CoreGraphics/CGEvent.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
@interface NSEvent (MouseCheck)
- (CGEventRef)CGEvent;
@end
@interface MouseCheckWindow : NSWindow
@end
@implementation MouseCheckWindow
- (BOOL)canBecomeKeyWindow { return YES; }
- (BOOL)canBecomeMainWindow { return YES; }
@end
@interface MouseCheckView : NSView
@end
@implementation MouseCheckView
- (void)otherMouseDown:(NSEvent *)e { printf("DISPATCH down %ld\n",(long)[e buttonNumber]); fflush(stdout); }
- (void)otherMouseUp:(NSEvent *)e { printf("DISPATCH up %ld\n",(long)[e buttonNumber]); fflush(stdout); }
- (void)otherMouseDragged:(NSEvent *)e { printf("DISPATCH drag %ld\n",(long)[e buttonNumber]); fflush(stdout); }
- (void)scrollWheel:(NSEvent *)e { printf("DISPATCH scroll %.0f %.0f\n",[e deltaX],[e deltaY]); fflush(stdout); }
@end
int main(int argc,char **argv) {
 @autoreleasepool {
  [NSApplication sharedApplication];
  BOOL fullscreen=argc>1 && !strcmp(argv[1],"--fullscreen");
  NSRect frame=fullscreen ? [[NSScreen mainScreen] frame] : NSMakeRect(250,250,480,300);
  NSWindow *w=[[MouseCheckWindow alloc] initWithContentRect:frame styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [w setTitle:@"Darling Mouse Check"];
  [w setContentView:[[[MouseCheckView alloc] initWithFrame:NSMakeRect(0,0,frame.size.width,frame.size.height)] autorelease]];
  [w setAcceptsMouseMovedEvents:YES];
  [w makeKeyAndOrderFront:nil];
  printf("READY fullscreen=%d window=%ld\n",fullscreen,(long)[w windowNumber]); fflush(stdout);
  NSDate *end=[NSDate dateWithTimeIntervalSinceNow:35];
  while ([end timeIntervalSinceNow]>0) {
   NSEvent *e=[NSApp nextEventMatchingMask:NSAnyEventMask untilDate:[NSDate dateWithTimeIntervalSinceNow:.05] inMode:NSDefaultRunLoopMode dequeue:YES];
   if (!e) continue;
   NSUInteger t=[e type];
   if (t==NSOtherMouseDown || t==NSOtherMouseUp || t==NSOtherMouseDragged) {
    CGEventRef cg=[e CGEvent];
    assert(cg && CGEventGetType(cg)==t);
    assert(CGEventGetIntegerValueField(cg,kCGMouseEventButtonNumber)==[e buttonNumber]);
    printf("EVENT type=%lu button=%ld\n",(unsigned long)t,(long)[e buttonNumber]); fflush(stdout);
   }
   [NSApp sendEvent:e];
  }
  [w orderOut:nil]; [w release];
  puts("DONE");
 }
 return 0;
}
